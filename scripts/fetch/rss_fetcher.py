"""通用 RSS/Atom 抓取器，覆盖官方博客、更新日志等 type=rss 的源。"""
import re
import time

import feedparser

from ..util import get_session, get_logger

log = get_logger(__name__)

MAX_RETRIES = 2

_IMG_SRC_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)


def _extract_image(entry):
    """按优先级提取条目配图：media:thumbnail / media:content / enclosure / 正文首图。"""
    for key in ("media_thumbnail", "media_content"):
        for media in entry.get(key) or []:
            url = media.get("url", "")
            if url.startswith("http"):
                return url
    for enc in entry.get("enclosures") or []:
        if str(enc.get("type", "")).startswith("image/") and str(enc.get("href", "")).startswith("http"):
            return enc["href"]
    html = ""
    if entry.get("content"):
        html = entry["content"][0].get("value", "")
    html = html or entry.get("summary") or ""
    m = _IMG_SRC_RE.search(html)
    if m and m.group(1).startswith("http"):
        return m.group(1)
    return None


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
                "image_url": _extract_image(entry),
            }
        )
    return items
