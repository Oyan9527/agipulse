"""通用 RSS/Atom 抓取器，覆盖官方博客、更新日志等 type=rss 的源。"""
import re
import time

import feedparser
import requests

from ..util import get_session, get_logger

log = get_logger(__name__)

MAX_RETRIES = 2
# 被限流时最多愿意就地等多久（秒）。超过这个数说明对方要我们歇很久，
# 当轮没必要耗在这一个源上——抛给上层，让它整体退避。
MAX_RETRY_AFTER = 30

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


def _retry_after_seconds(resp):
    """解析 Retry-After 头（只认秒数形式，HTTP-date 形式少见且不值得为它引依赖）。"""
    raw = (resp.headers.get("Retry-After") or "").strip() if resp is not None else ""
    try:
        return max(0, int(raw))
    except ValueError:
        return None


def _get_with_retry(session, url):
    last_err = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
            return resp
        except requests.HTTPError as e:
            # 429 不能靠"立刻再试"解决，那只会把对方的限流窗口拉得更长。
            # 线上踩过：reddit 的 20 个源本已强制串行、每 3 秒一个，但每个源
            # 失败后还会在锁里连打 2 次重试，真实密度变成 3 秒 3 次请求，
            # 结果 17/20 全军覆没。这里只在对方明确给了 Retry-After 且等得起
            # 时才等一次，否则原样抛出，由调用方决定整体怎么退。
            status = e.response.status_code if e.response is not None else None
            if status == 429:
                wait = _retry_after_seconds(e.response)
                if wait is not None and wait <= MAX_RETRY_AFTER and attempt < MAX_RETRIES:
                    log.info("429 on %s, honoring Retry-After=%ss", url, wait)
                    time.sleep(wait)
                    last_err = e
                    continue
                raise
            last_err = e
            if attempt >= MAX_RETRIES:
                raise
            time.sleep(2 ** attempt)
        except Exception as e:  # noqa: BLE001 - 瞬时网络错误重试，非瞬时的交给上层记录
            last_err = e
            if attempt >= MAX_RETRIES:
                raise
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
