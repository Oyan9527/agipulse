"""流水线编排入口。
用法：
  python -m scripts.run_pipeline --output-dir data                 # 生产：真实 DeepSeek 打分（需 DEEPSEEK_API_KEY）
  python -m scripts.run_pipeline --skip-llm                        # 只跑抓取/归一化/去重，验证数据源，不调用LLM
  python -m scripts.run_pipeline --mock-llm --output-dir data      # 本地开发：确定性启发式打分代替真实LLM，用于前端联调
"""
import argparse
import json
import os
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

log = get_logger(__name__)

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def load_config():
    sources_cfg = load_yaml(CONFIG_DIR / "sources.yaml")["sources"]
    categories_cfg = load_yaml(CONFIG_DIR / "categories.yaml")["categories"]
    weights_cfg = load_yaml(CONFIG_DIR / "weights.yaml")
    return sources_cfg, categories_cfg, weights_cfg


def fetch_and_normalize(sources_cfg):
    fetch_results = {}
    normalized_by_source = {}
    all_items = []

    for source in sources_cfg:
        if source.get("status") == "broken":
            continue
        if str(source.get("url", "")).startswith("PLACEHOLDER"):
            continue

        raw_items, error = fetch_source(source)
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


def run(output_dir, skip_llm=False, mock_llm=False, window_hours=48):
    sources_cfg, categories_cfg, weights_cfg = load_config()

    fetch_results, normalized_by_source, all_items = fetch_and_normalize(sources_cfg)
    all_items = dedupe(all_items, weights_cfg)
    processable = filter_processing_window(all_items, hours=window_hours)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

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

    atomic_write_json(out_dir / "latest-24h.json", latest_24h)
    atomic_write_json(out_dir / "latest-24h-all.json", all_24h)
    atomic_write_json(out_dir / "daily-brief.json", daily_brief)
    atomic_write_json(out_dir / "stories-merged.json", stories)
    atomic_write_json(out_dir / "source-status.json", status)

    log.info(
        "pipeline done: %d curated / %d all / %d stories",
        len(latest_24h), len(all_24h), len(stories),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="site/data")
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
