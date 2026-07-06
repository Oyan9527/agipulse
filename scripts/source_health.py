"""信源健康度追踪：抓取成功/失败、24小时条目数、AI内容占比（粗筛通过率）。"""
from .util import now_utc, get_logger

log = get_logger(__name__)


def build_source_status(fetch_results, normalized_by_source, prefiltered_ids):
    """
    fetch_results: {source_id: error_or_None}
    normalized_by_source: {source_id: [normalized items]}
    prefiltered_ids: set of item ids that survived prefilter
    """
    now = now_utc().isoformat()
    statuses = []
    for source_id, error in fetch_results.items():
        items = normalized_by_source.get(source_id, [])
        total = len(items)
        kept = sum(1 for it in items if it["id"] in prefiltered_ids)
        ratio = round(kept / total, 3) if total else None

        statuses.append(
            {
                "source_id": source_id,
                "last_success": now if error is None else None,
                "last_error": error,
                "items_last_24h": total,
                "ai_content_ratio": ratio,
            }
        )
    return statuses
