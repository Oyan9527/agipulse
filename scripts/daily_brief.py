"""今日简报：深度长文推荐——24小时内精选流里优先选正文足够长的深度文章按加权分排序，
不足 top_n 时从其余条目按分数补齐（避免长文不够时简报过短）；冷清日 items 为空数组，前端对应区块收起。
"""
import re
from datetime import datetime, timedelta, timezone

from .util import get_logger

log = get_logger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")


def _plain_text_len(raw_text):
    return len(_TAG_RE.sub("", raw_text or ""))


def build_daily_brief(curated_items, weights_config):
    cfg = weights_config["daily_brief"]
    top_n = cfg["top_n"]
    min_len = cfg.get("min_raw_text_length", 0)
    exclude_categories = set(cfg.get("exclude_categories") or [])
    now = datetime.now(timezone.utc)
    window = timedelta(hours=24)

    recent = [
        it
        for it in curated_items
        if now - datetime.fromisoformat(it["published_at"]) <= window
    ]

    # 论文摘要/仓库changelog天然是长段落，长度门槛对它们没有区分度，需按分类显式排除
    deep = [
        it for it in recent
        if it.get("category") not in exclude_categories
        and _plain_text_len(it.get("raw_text")) >= min_len
    ]
    ranked = sorted(deep, key=lambda x: x["weighted_score"], reverse=True)[:top_n]

    if len(ranked) < top_n:
        chosen_ids = {it["id"] for it in ranked}
        backfill = sorted(
            (it for it in recent if it["id"] not in chosen_ids and it.get("category") not in exclude_categories),
            key=lambda x: x["weighted_score"],
            reverse=True,
        )
        ranked += backfill[: top_n - len(ranked)]

    log.info("daily_brief: %d items selected (%d deep long-form, %d backfilled)",
             len(ranked), min(len(ranked), len(deep)), max(0, len(ranked) - len(deep)))
    return {
        "date": now.date().isoformat(),
        "generated_at": now.isoformat(),
        "items": ranked,
    }
