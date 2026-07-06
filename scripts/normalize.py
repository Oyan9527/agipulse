"""把各抓取器的原始 item 统一成标准 schema：
{id, source_id, title, url, published_at(iso str), raw_text, category_hint}
"""
from .util import make_id, to_iso, now_utc


def normalize_items(raw_items, source):
    source_id = source["id"]
    category_hint = source.get("category_hint", [])
    normalized = []
    for raw in raw_items:
        title = (raw.get("title") or "").strip()
        url = (raw.get("url") or "").strip()
        if not title or not url:
            continue
        published_at = raw.get("published_at") or now_utc()
        normalized.append(
            {
                "id": make_id(url),
                "source_id": source_id,
                "title": title,
                "url": url,
                "published_at": to_iso(published_at),
                "raw_text": (raw.get("raw_text") or "")[:1000],
                "category_hint": category_hint,
            }
        )
    return normalized
