"""GitHub 涨星榜：日/周/月走 OSSInsight 官方趋势 API（按周期内新增 star 数排序，无需 Key）。

OSSInsight 的 period 只支持 past_24_hours/past_week/past_month/past_3_months，
不支持年度或总榜，因此"年"与"总榜"改走 GitHub Search API，按总 star 数排序：
- all_time：不限创建时间，即经典的"历史最多star仓库"总榜
- past_year：仅限近1年内创建的仓库，即"年度新锐"榜（GitHub官方trending本身也无年度维度）
这两档的数字含义是"总star数"而非"新增star数"，通过 stars_metric 字段区分，供前端选择 "+" 前缀。
"""
import time
from datetime import timedelta

from ..util import get_session, get_logger, env, now_utc

log = get_logger(__name__)

OSSINSIGHT_URL = "https://api.ossinsight.io/v1/trends/repos/"
SEARCH_URL = "https://api.github.com/search/repositories"
MAX_RETRIES = 2


def _fetch_period(session, period):
    """OSSInsight：周期内新增 star 数排序（日/周/月）。"""
    last_err = None
    resp = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = session.get(OSSINSIGHT_URL, params={"period": period}, timeout=20)
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
                "stars_metric": "gained",
                "language": row.get("primary_language") or "",
            }
        )
    return items


def _fetch_search(session, query):
    """GitHub Search API：总 star 数排序，供"年"/"总榜"使用。"""
    headers = {"Accept": "application/vnd.github+json"}
    token = env("GH_PAT")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = session.get(
        SEARCH_URL,
        headers=headers,
        params={"q": query, "sort": "stars", "order": "desc", "per_page": 10},
        timeout=20,
    )
    resp.raise_for_status()
    rows = resp.json().get("items", [])
    items = []
    for row in rows:
        name = row.get("full_name")
        if not name:
            continue
        items.append(
            {
                "title": name,
                "url": row.get("html_url") or f"https://github.com/{name}",
                "raw_text": row.get("description") or "",
                "stars_gained": int(row.get("stargazers_count") or 0),
                "stars_metric": "total",
                "language": row.get("language") or "",
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
            if period == "all_time":
                result[period] = _fetch_search(session, "stars:>1")
            elif period == "past_year":
                one_year_ago = (now_utc() - timedelta(days=365)).strftime("%Y-%m-%d")
                result[period] = _fetch_search(session, f"created:>={one_year_ago}")
            else:
                result[period] = _fetch_period(session, period)
        except Exception as e:  # noqa: BLE001 - 单周期失败不影响其他周期
            log.warning("gh_trending period %s failed: %s", period, e)
            result[period] = []
    return result
