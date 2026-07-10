"""GitHub 涨星榜：OSSInsight 官方趋势 API，按周期内新增 star 数排序。

OSSInsight（PingCAP 出品）是公开只读的开源生态分析服务，无需 Key。
"""
import time

from ..util import get_session, get_logger

log = get_logger(__name__)

API_URL = "https://api.ossinsight.io/v1/trends/repos/"
MAX_RETRIES = 2


def _fetch_period(session, period):
    last_err = None
    resp = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = session.get(API_URL, params={"period": period}, timeout=20)
            resp.raise_for_status()
            break
        except Exception as e:  # noqa: BLE001 - 偶发瞬时SSL错误，重试后通常恢复
            last_err = e
            resp = None
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)
    if resp is None:
        raise last_err
    data = resp.json()
    rows = data.get("data", {}).get("rows", [])

    def stars_of(row):
        try:
            return int(row.get("stars") or 0)
        except (TypeError, ValueError):
            return 0

    rows_sorted = sorted(rows, key=stars_of, reverse=True)
    items = []
    for row in rows_sorted:
        name = row.get("repo_name")
        if not name:
            continue
        items.append(
            {
                "title": name,
                "url": f"https://github.com/{name}",
                "raw_text": row.get("description") or "",
                "stars_gained": stars_of(row),
                "language": row.get("primary_language") or "",
            }
        )
    return items


def fetch(source):
    """按 source['periods']（默认日/周/月三档）分别抓取，返回 {period_key: [items]}。
    单个周期请求失败不影响其他周期（各自 try/except，交由上层记录）。
    """
    session = get_session()
    periods = source.get("periods") or [source.get("period", "past_24_hours")]
    result = {}
    for period in periods:
        try:
            result[period] = _fetch_period(session, period)
        except Exception as e:  # noqa: BLE001 - 单周期失败不影响其他周期
            log.warning("gh_trending period %s failed: %s", period, e)
            result[period] = []
    return result
