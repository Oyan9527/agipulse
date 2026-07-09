"""流水线编排入口。
用法：
  python -m scripts.run_pipeline --output-dir data                 # 生产：真实 DeepSeek 打分（需 DEEPSEEK_API_KEY）
  python -m scripts.run_pipeline --skip-llm                        # 只跑抓取/归一化/去重，验证数据源，不调用LLM
  python -m scripts.run_pipeline --mock-llm --output-dir data      # 本地开发：确定性启发式打分代替真实LLM，用于前端联调
"""
import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .util import load_yaml, get_logger, now_utc
from .fetch import fetch_source
from .normalize import normalize_items
from .dedupe import dedupe
from .llm_prefilter import prefilter
from .llm_score import score_items
from .mock_llm import mock_prefilter, mock_score_items
from .story_merge import merge_stories
from .quality_gate import apply_gate
from .daily_brief import build_daily_brief
from .source_health import build_source_status
from .trends import build_trends, _extract_keywords
from .archive import update_daily_archive, load_daily_archives
from .ai_relevance import is_ai_related

log = get_logger(__name__)

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def load_config():
    sources_cfg = load_yaml(CONFIG_DIR / "sources.yaml")["sources"]
    categories_cfg = load_yaml(CONFIG_DIR / "categories.yaml")["categories"]
    weights_cfg = load_yaml(CONFIG_DIR / "weights.yaml")
    return sources_cfg, categories_cfg, weights_cfg


FETCH_WORKERS = 10


def fetch_and_normalize(sources_cfg):
    fetch_results = {}
    normalized_by_source = {}
    all_items = []

    active = [
        s for s in sources_cfg
        if s.get("status") != "broken"
        and not str(s.get("url", "")).startswith("PLACEHOLDER")
        and s.get("role", "ai_pipeline") == "ai_pipeline"
    ]

    def worker(source):
        raw_items, error = fetch_source(source)
        return source, raw_items, error

    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
        for source, raw_items, error in pool.map(worker, active):
            fetch_results[source["id"]] = error
            if error:
                log.warning("source %s failed: %s", source["id"], error)
                normalized_by_source[source["id"]] = []
                continue
            normalized = normalize_items(raw_items, source)
            normalized_by_source[source["id"]] = normalized
            all_items.extend(normalized)
            log.info("source %s: %d items", source["id"], len(normalized))

    return fetch_results, normalized_by_source, all_items


def filter_processing_window(items, hours=48):
    now = now_utc()
    window = timedelta(hours=hours)
    return [
        it for it in items
        if now - datetime.fromisoformat(it["published_at"]) <= window
    ]


def filter_output_window(items, hours=24):
    now = now_utc()
    window = timedelta(hours=hours)
    return [
        it for it in items
        if now - datetime.fromisoformat(it["published_at"]) <= window
    ]


def atomic_write_json(path, data):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def build_social_hot(sources_cfg):
    """社媒热点：百度/B站/知乎热搜 + HN前台。独立于AI主流程，不打分，
    但只保留 AI 相关话题（关键词过滤，见 ai_relevance.is_ai_related）。
    单平台抓取失败或无AI话题时该平台 items 为空数组，前端对应区块直接隐藏。
    """
    platforms = []
    for source in sources_cfg:
        if source.get("role") != "social_hot":
            continue
        raw_items, error = fetch_source(source)
        if error:
            log.warning("social_hot source %s failed: %s", source["id"], error)
            items = []
        else:
            items = [
                {"title": it["title"], "url": it["url"]}
                for it in raw_items
                if it.get("title") and it.get("url") and is_ai_related(it["title"])
            ][:10]
        platforms.append(
            {
                "platform": source.get("platform", source["id"]),
                "source_id": source["id"],
                "items": items,
            }
        )
        log.info("social_hot %s: %d AI items kept", source["id"], len(items))
    return {"generated_at": now_utc().isoformat(), "platforms": platforms}


def build_github_trending(sources_cfg):
    """GitHub 涨星榜：独立于AI主流程，取当前周期内新增 star 数最多的仓库。"""
    source = next((s for s in sources_cfg if s.get("role") == "gh_trending"), None)
    if not source:
        return {"generated_at": now_utc().isoformat(), "period": None, "repos": []}

    raw_items, error = fetch_source(source)
    repos = []
    if error:
        log.warning("gh_trending source failed: %s", error)
    else:
        for it in raw_items[:10]:
            repos.append(
                {
                    "repo": it["title"],
                    "url": it["url"],
                    "description": it.get("raw_text", ""),
                    "stars_gained": it.get("stars_gained", 0),
                    "language": it.get("language", ""),
                }
            )
    return {
        "generated_at": now_utc().isoformat(),
        "period": source.get("period", "past_24_hours"),
        "repos": repos,
    }


def run(output_dir, skip_llm=False, mock_llm=False, window_hours=48):
    sources_cfg, categories_cfg, weights_cfg = load_config()

    fetch_results, normalized_by_source, all_items = fetch_and_normalize(sources_cfg)
    all_items = dedupe(all_items, weights_cfg)
    processable = filter_processing_window(all_items, hours=window_hours)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 社媒热点 / GitHub 涨星榜：独立分支，任何模式下都产出，不经过 AI 打分流程
    social_hot = build_social_hot(sources_cfg)
    github_trending = build_github_trending(sources_cfg)
    atomic_write_json(out_dir / "social-hot.json", social_hot)
    atomic_write_json(out_dir / "github-trending.json", github_trending)
    log.info(
        "social_hot: %d platforms; github_trending: %d repos",
        len(social_hot["platforms"]), len(github_trending["repos"]),
    )

    if skip_llm:
        log.info("skip-llm 模式：只输出归一化/去重后的原始条目，供本地验证")
        atomic_write_json(out_dir / "debug-normalized.json", processable)
        status = build_source_status(fetch_results, normalized_by_source, set())
        atomic_write_json(out_dir / "source-status.json", status)
        return

    if mock_llm:
        log.warning("mock-llm 模式：使用启发式打分代替真实 DeepSeek 调用，仅供本地前端联调使用")
        authority_by_id = {s["id"]: s.get("authority_weight", 0.5) for s in sources_cfg}
        kept = mock_prefilter(processable)
        kept_ids = {it["id"] for it in kept}
        scored, unscored = mock_score_items(
            kept, categories_cfg, weights_cfg["scoring_weights"], authority_by_id
        )
    else:
        kept = prefilter(processable)
        kept_ids = {it["id"] for it in kept}
        scored, unscored = score_items(kept, categories_cfg, weights_cfg["scoring_weights"])

    merged_items, stories = merge_stories(scored, weights_cfg)

    curated = apply_gate(merged_items, weights_cfg)

    # latest-24h-all.json：全部条目（含未打分的），做前端"全部动态"视图
    all_output_items = merged_items + [dict(it, weighted_score=None, category=it.get("category_hint", [None])[0]) for it in unscored]
    all_24h = filter_output_window(all_output_items, hours=24)

    latest_24h = filter_output_window(curated, hours=24)
    daily_brief = build_daily_brief(curated, weights_cfg)
    status = build_source_status(fetch_results, normalized_by_source, kept_ids)

    update_daily_archive(merged_items, _extract_keywords, out_dir)
    daily_archives = load_daily_archives(out_dir)
    trends = build_trends(merged_items, stories, weights_cfg, daily_archives)

    atomic_write_json(out_dir / "latest-24h.json", latest_24h)
    atomic_write_json(out_dir / "latest-24h-all.json", all_24h)
    atomic_write_json(out_dir / "daily-brief.json", daily_brief)
    atomic_write_json(out_dir / "stories-merged.json", stories)
    atomic_write_json(out_dir / "source-status.json", status)
    atomic_write_json(out_dir / "trends.json", trends)

    log.info(
        "pipeline done: %d curated / %d all / %d stories",
        len(latest_24h), len(all_24h), len(stories),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="docs/data")
    parser.add_argument("--skip-llm", action="store_true")
    parser.add_argument("--mock-llm", action="store_true")
    parser.add_argument("--window-hours", type=int, default=48)
    args = parser.parse_args()

    run(
        args.output_dir,
        skip_llm=args.skip_llm,
        mock_llm=args.mock_llm,
        window_hours=args.window_hours,
    )


if __name__ == "__main__":
    main()
