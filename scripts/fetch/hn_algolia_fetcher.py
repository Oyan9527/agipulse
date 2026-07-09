"""Hacker News (Algolia Search API) 抓取器。
默认按关键词过滤最近的 story；mode=front_page 时改为拉取当前 HN 前台热榜
（不做关键词过滤，用于"国际热点"社媒展示，与 AI 主流程的关键词源分开使用）。
"""
import time
from datetime import datetime, timezone

from ..util import get_session

SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"
FRONT_PAGE_URL = "https://hn.algolia.com/api/v1/search"
MAX_RETRIES = 2


def fetch(source):
    session = get_session()
    if source.get("mode") == "front_page":
        url, params = FRONT_PAGE_URL, {"tags": "front_page", "hitsPerPage": 15}
    else:
        url, params = SEARCH_URL, {"query": source["query"], "tags": "story", "hitsPerPage": 40}

    last_err = None
    resp = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = session.get(url, params=params, timeout=20)
            resp.raise_for_status()
            break
        except Exception as e:  # noqa: BLE001 - hn.algolia.com 偶发瞬时SSL错误，重试后通常恢复
            last_err = e
            resp = None
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)
    if resp is None:
        raise last_err
    data = resp.json()

    items = []
    for hit in data.get("hits", []):
        created_at = hit.get("created_at")
        published_at = None
        if created_at:
            published_at = datetime.fromisoformat(created_at.replace("Z", "+00:00")).astimezone(
                timezone.utc
            )
        url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
        items.append(
            {
                "title": hit.get("title") or "",
                "url": url,
                "published_at": published_at,
                "raw_text": hit.get("story_text") or "",
            }
        )
    return items
