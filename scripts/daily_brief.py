"""今日简报：24小时内精选流按加权分取 Top N；冷清日 items 为空数组，前端对应区块收起。"""
from datetime import datetime, timedelta, timezone

from .util import get_logger

log = get_logger(__name__)


def build_daily_brief(curated_items, weights_config):
    top_n = weights_config["daily_brief"]["top_n"]
    now = datetime.now(timezone.utc)
    window = timedelta(hours=24)

    recent = [
        it
        for it in curated_items
        if now - datetime.fromisoformat(it["published_at"]) <= window
    ]
    ranked = sorted(recent, key=lambda x: x["weighted_score"], reverse=True)[:top_n]

    log.info("daily_brief: %d items selected", len(ranked))
    return {
        "date": now.date().isoformat(),
        "generated_at": now.isoformat(),
        "items": ranked,
    }
