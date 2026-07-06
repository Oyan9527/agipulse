"""Hacker News (Algolia Search API) 抓取器，按关键词过滤最近的 story。"""
from datetime import datetime, timezone

from ..util import get_session

API_URL = "https://hn.algolia.com/api/v1/search_by_date"


def fetch(source):
    query = source["query"]
    session = get_session()
    resp = session.get(
        API_URL,
        params={"query": query, "tags": "story", "hitsPerPage": 40},
        timeout=20,
    )
    resp.raise_for_status()
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
