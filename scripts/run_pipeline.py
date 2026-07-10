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

from .util import load_yaml, get_logger, now_utc, safe_http_url
from .fetch import fetch_source
from .normalize import normalize_items
from .dedupe import dedupe
from .llm_prefilter import prefilter
from .llm_score import score_items
from .mock_llm import mock_prefilter, mock_score_items
from .story_merge import merge_stories, collapse_stories
from .quality_gate import apply_gate
from .daily_brief import build_daily_brief
from .feed import build_feed
from .source_health import build_source_status
from .trends import build_trends, _extract_keywords
from .archive import update_daily_archive, load_daily_archives
from .ai_relevance import is_ai_related
from .social_translate import translate_titles, translate_field
from . import llm_cache

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


def filter_ai_relevance(items, weights_config):
    """严格AI相关性过滤：只对"通用源"(中文综合科技站/个人技术博客)按标题关键词过滤，
    天然AI源(官方AI博客/arXiv/AI媒体/AI项目仓库)直接放行。
    分层理由与"只查标题不查正文"的理由见 config/weights.yaml 的 ai_relevance 段。
    """
    cfg = weights_config.get("ai_relevance") or {}
    prefixes = tuple(cfg.get("strict_source_prefixes") or ())
    strict_ids = set(cfg.get("strict_sources") or ())
    if not prefixes and not strict_ids:
        return items

    def needs_filter(item):
        sid = item.get("source_id", "")
        return sid in strict_ids or (prefixes and sid.startswith(prefixes))

    kept = [it for it in items if not needs_filter(it) or is_ai_related(it.get("title", ""))]
    dropped = len(items) - len(kept)
    if dropped:
        log.info("ai_relevance: %d -> %d items (dropped %d non-AI from general sources)",
                 len(items), len(kept), dropped)
    return kept


def apply_intake_quotas(items, weights_config):
    """原始抓取配额：部分类别源特别多(如论文研究)，抓取量会远超其他类别，
    在进入去重后的处理流程前按新鲜度(published_at)截断，只保留最新的一批。
    影响"全部动态"展示体量，也顺带降低该类别的LLM调用量。
    """
    quotas = weights_config.get("intake_quotas") or {}
    if not quotas:
        return items

    others = []
    by_cat = {}
    for it in items:
        cat = (it.get("category_hint") or [None])[0]
        if cat not in quotas:
            others.append(it)
            continue
        by_cat.setdefault(cat, []).append(it)

    capped = others
    for cat, cat_items in by_cat.items():
        cap = quotas[cat].get("max")
        if cap is None:
            capped += cat_items
            continue
        cat_items.sort(key=lambda x: x["published_at"], reverse=True)
        kept, dropped = cat_items[:cap], cat_items[cap:]
        if dropped:
            log.info("intake_quota: category %s capped at %d (dropped %d oldest of %d)",
                     cat, cap, len(dropped), len(cat_items))
        capped += kept
    return capped


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


def atomic_write_text(path, text):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def build_social_hot(sources_cfg, skip_llm=False, mock_llm=False):
    """社媒热点：B站/微博/知乎/HN/Reddit/X。独立于AI主流程，不打分，
    但只保留 AI 相关话题（关键词过滤，见 ai_relevance.is_ai_related），
    并把英文标题翻译成中文（见 social_translate.translate_titles）。
    单平台抓取失败/无AI话题时该平台 items 为空数组，前端对应区块直接隐藏——
    微博/知乎是通用热榜，AI 话题是否上榜取决于当天热点，为空属正常现象。
    """
    platforms = []
    for source in sources_cfg:
        if source.get("role") != "social_hot":
            continue
        if str(source.get("url", "")).startswith("PLACEHOLDER"):
            log.info("social_hot %s: not configured yet (placeholder), skipped", source["id"])
            items = []
        else:
            raw_items, error = fetch_source(source)
            if error:
                log.warning("social_hot source %s failed: %s", source["id"], error)
                items = []
            else:
                # 判据用标题+正文摘要：知乎热榜的问题描述里常有 AI 线索，只看标题会漏。
                # 社媒条目正文都很短，不存在主流程里"资讯汇编夹带AI词"的假阳性问题。
                # 这一支不走 normalize，需自行做 URL 安全校验（见 util.safe_http_url）。
                items = [
                    {"title": it["title"], "url": safe_http_url(it.get("url"))}
                    for it in raw_items
                    if it.get("title") and safe_http_url(it.get("url"))
                    and is_ai_related(f"{it['title']} {(it.get('raw_text') or '')[:200]}")
                ][:10]
            if items and not skip_llm:
                translate_titles(items, mock=mock_llm)
        platforms.append(
            {
                "platform": source.get("platform", source["id"]),
                "source_id": source["id"],
                "items": items,
            }
        )
        log.info("social_hot %s: %d AI items kept", source["id"], len(items))
    return {"generated_at": now_utc().isoformat(), "platforms": platforms}


def build_github_trending(sources_cfg, skip_llm=False, mock_llm=False):
    """GitHub 涨星榜：独立于AI主流程，日/周/月三档周期各取新增 star 数最多的10个仓库。
    描述文案是英文时翻译成中文（description_zh，仓库名本身是标识符不翻译）。
    """
    source = next((s for s in sources_cfg if s.get("role") == "gh_trending"), None)
    periods = (source or {}).get("periods") or ["past_24_hours"]
    empty = {p: [] for p in periods}
    if not source:
        return {"generated_at": now_utc().isoformat(), "periods": empty}

    raw_by_period, error = fetch_source(source)
    dimensions = {}
    if error:
        log.warning("gh_trending source failed entirely: %s", error)
        dimensions = empty
    else:
        for period, raw_items in raw_by_period.items():
            # 同样不走 normalize，URL 需自行做安全校验
            repos = [
                {
                    "repo": it["title"],
                    "url": safe_http_url(it.get("url")),
                    "description": it.get("raw_text", ""),
                    "stars_gained": it.get("stars_gained", 0),
                    "stars_metric": it.get("stars_metric", "gained"),
                    "language": it.get("language", ""),
                }
                for it in raw_items[:10]
                if safe_http_url(it.get("url"))
            ]
            if repos and not skip_llm:
                translate_field(repos, "description", "description_zh", mock=mock_llm, mock_len=40)
            dimensions[period] = repos
    return {"generated_at": now_utc().isoformat(), "periods": dimensions}


def run(output_dir, skip_llm=False, mock_llm=False, window_hours=48):
    sources_cfg, categories_cfg, weights_cfg = load_config()

    fetch_results, normalized_by_source, all_items = fetch_and_normalize(sources_cfg)
    all_items = dedupe(all_items, weights_cfg)
    all_items = filter_ai_relevance(all_items, weights_cfg)
    all_items = apply_intake_quotas(all_items, weights_cfg)
    processable = filter_processing_window(all_items, hours=window_hours)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 社媒热点 / GitHub 涨星榜：独立分支，任何模式下都产出，不经过 AI 打分流程
    social_hot = build_social_hot(sources_cfg, skip_llm=skip_llm, mock_llm=mock_llm)
    github_trending = build_github_trending(sources_cfg, skip_llm=skip_llm, mock_llm=mock_llm)
    atomic_write_json(out_dir / "social-hot.json", social_hot)
    atomic_write_json(out_dir / "github-trending.json", github_trending)
    log.info(
        "social_hot: %d platforms; github_trending: %s",
        len(social_hot["platforms"]),
        {p: len(r) for p, r in github_trending["periods"].items()},
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
        # 结果缓存：同一条目在48h窗口内会被连续抓到多次，命中过的直接复用，
        # 只把从未见过的新内容真正送去 DeepSeek——大幅降低消耗（见 llm_cache.py 顶部说明）。
        cache = llm_cache.load_cache(out_dir)
        cached_scored, cached_rejected_ids, uncached = llm_cache.split_by_cache(processable, cache)

        kept = prefilter(uncached)
        newly_kept_ids = {it["id"] for it in kept}
        newly_rejected_ids = {it["id"] for it in uncached} - newly_kept_ids
        llm_cache.record_rejected(cache, newly_rejected_ids)

        newly_scored, unscored = score_items(kept, categories_cfg, weights_cfg["scoring_weights"])
        llm_cache.record_scored(cache, newly_scored)

        scored = cached_scored + newly_scored
        kept_ids = {it["id"] for it in cached_scored} | newly_kept_ids

        llm_cache.save_cache(out_dir, cache, retain_ids={it["id"] for it in processable})
        log.info(
            "llm_cache: %d cached-scored, %d cached-rejected, %d new (of %d processable)",
            len(cached_scored), len(cached_rejected_ids), len(uncached), len(processable),
        )

    merged_items, stories = merge_stories(scored, weights_cfg)

    # 展示流按故事折叠：同一事件被多家同时报道时(如"GPT-5.6 发布")只出一条卡片，
    # 其余来源收在卡片的 ×N 徽章里。趋势/归档仍用全量 merged_items 做统计。
    representative = collapse_stories(merged_items)

    curated = apply_gate(representative, weights_cfg)

    # latest-24h-all.json：全部条目（含未打分的），做前端"全部动态"视图。
    # 这里也折叠：同一事件重复出现同样会淹没信息流；未打分条目没有 story_id，原样保留。
    all_output_items = representative + [dict(it, weighted_score=None, category=it.get("category_hint", [None])[0]) for it in unscored]
    all_24h = filter_output_window(all_output_items, hours=24)

    latest_24h = filter_output_window(curated, hours=24)
    # 传全部已打分条目(而非精选流)：深度推荐自成一套筛选，见 daily_brief.py 顶部说明
    daily_brief = build_daily_brief(representative, weights_cfg)
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

    # Atom 订阅源：放在站点根目录（out_dir 是 docs/data，feed 要在 docs/feed.xml），
    # 否则 <link rel=alternate> 指不到。注意 workflow 提交时要一并 git add docs/feed.xml。
    atomic_write_text(out_dir.parent / "feed.xml", build_feed(latest_24h))

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
