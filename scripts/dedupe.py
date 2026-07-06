"""同源/近重复条目去重：标题模糊匹配（rapidfuzz），48小时窗口内比对。
注意：这里只去"同一条目被重复抓到"的重复，不同源报道同一事件的合并交给 story_merge.py。
"""
from datetime import datetime, timedelta, timezone

from rapidfuzz import fuzz

from .util import load_yaml, get_logger

log = get_logger(__name__)


def _parse_iso(s):
    return datetime.fromisoformat(s)


def dedupe(items, weights_config):
    threshold = weights_config["dedupe"]["fuzzy_title_threshold"]
    window_hours = weights_config["dedupe"]["window_hours"]
    window = timedelta(hours=window_hours)

    items_sorted = sorted(items, key=lambda x: x["published_at"])
    kept = []
    seen_ids = set()

    for item in items_sorted:
        if item["id"] in seen_ids:
            continue
        seen_ids.add(item["id"])

        item_time = _parse_iso(item["published_at"])
        is_dup = False
        for existing in kept:
            existing_time = _parse_iso(existing["published_at"])
            if abs((item_time - existing_time)) > window:
                continue
            if existing["source_id"] != item["source_id"]:
                continue  # 跨源相似交给 story_merge 处理
            score = fuzz.token_sort_ratio(existing["title"], item["title"])
            if score >= threshold:
                is_dup = True
                break
        if not is_dup:
            kept.append(item)

    log.info("dedupe: %d -> %d items", len(items), len(kept))
    return kept
