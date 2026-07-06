"""通用 RSS/Atom 抓取器，覆盖官方博客、更新日志等 type=rss 的源。"""
import time

import feedparser

from ..util import get_session, get_logger

log = get_logger(__name__)

MAX_RETRIES = 2


def _get_with_retry(session, url):
    last_err = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
            return resp
        except Exception as e:  # noqa: BLE001 - 瞬时网络/限流错误重试，非瞬时的交给上层记录
            last_err = e
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)
    raise last_err


def fetch(source):
    url = source["url"]
    session = get_session()
    resp = _get_with_retry(session, url)
    parsed = feedparser.parse(resp.content)

    if parsed.bozo and not parsed.entries:
        raise ValueError(f"feed parse failed for {url}: {parsed.bozo_exception}")

    items = []
    for entry in parsed.entries:
        published = None
        for key in ("published_parsed", "updated_parsed"):
            if entry.get(key):
                import calendar
                from datetime import datetime, timezone

                published = datetime.fromtimestamp(
                    calendar.timegm(entry[key]), tz=timezone.utc
                )
                break

        items.append(
            {
                "title": entry.get("title", "").strip(),
                "url": entry.get("link", ""),
                "published_at": published,
                "raw_text": (entry.get("summary") or entry.get("description") or "").strip(),
            }
        )
    return items
