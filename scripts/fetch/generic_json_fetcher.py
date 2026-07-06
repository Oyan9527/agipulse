"""兜底的通用 JSON 抓取器，用于结构不固定的可选/补充源（如知乎热榜）。
尽力而为：无法识别的 JSON 结构直接返回空列表，不抛异常导致整个源被标记 broken。
"""
from ..util import get_session, get_logger

log = get_logger(__name__)


def fetch(source):
    url = source.get("url", "")
    if not url or url.startswith("PLACEHOLDER"):
        return []

    session = get_session()
    resp = session.get(url, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    items = []
    # 尝试几种常见结构；未知结构则放弃解析并返回空列表而非报错
    candidates = None
    if isinstance(data, dict):
        for key in ("data", "items", "list"):
            if isinstance(data.get(key), list):
                candidates = data[key]
                break
    elif isinstance(data, list):
        candidates = data

    if not candidates:
        log.warning("generic_json_fetcher: unrecognized JSON shape for %s", url)
        return []

    for entry in candidates:
        if not isinstance(entry, dict):
            continue
        title = entry.get("title") or entry.get("name") or ""
        link = entry.get("url") or entry.get("link") or ""
        if not title or not link:
            continue
        items.append(
            {
                "title": title,
                "url": link,
                "published_at": None,
                "raw_text": entry.get("excerpt") or entry.get("summary") or "",
            }
        )
    return items
