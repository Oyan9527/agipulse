"""同源/近重复条目去重：标题模糊匹配（rapidfuzz），48小时窗口内比对。
注意：这里只去"同一条目被重复抓到"的重复，不同源报道同一事件的合并交给 story_merge.py。
"""
from datetime import datetime, timedelta, timezone

from rapidfuzz import fuzz

from .story_merge import _strong_entities
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
            if score < threshold:
                continue
            # 模糊匹配对"只差一位版本号"不敏感：实测"OpenAI 发布 GPT-5"与"OpenAI 发布
            # GPT-6"相似度 93.3、"iPhone 16 发布"与"iPhone 17 发布"相似度 91.7，都超过
            # 90 的阈值，会把同源但真正不同的连续版本发布误判成重复而丢弃后一条。
            # 若两条标题都能提取出明确的版本化实体（复用 story_merge 的判据）且完全不
            # 重合，说明这是两条不同的具体发布，不该仅凭词形相似就当重复处理。
            existing_entities = _strong_entities(existing["title"])
            item_entities = _strong_entities(item["title"])
            if existing_entities and item_entities and not (existing_entities & item_entities):
                continue
            is_dup = True
            break
        if not is_dup:
            kept.append(item)

    log.info("dedupe: %d -> %d items", len(items), len(kept))
    return kept
