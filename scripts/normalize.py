"""把各抓取器的原始 item 统一成标准 schema：
{id, source_id, title, url, published_at(iso str), raw_text, category_hint}
"""
from .util import make_id, to_iso, now_utc, safe_http_url


def normalize_items(raw_items, source):
    source_id = source["id"]
    category_hint = source.get("category_hint", [])
    normalized = []
    for raw in raw_items:
        title = (raw.get("title") or "").strip()
        # url/image_url 来自第三方 RSS 与 API，前端会写进 <a href>/<img src>。
        # javascript: 之类的链接在入库时就丢弃（前端另有兜底，见 docs/js/safe.js）。
        url = safe_http_url(raw.get("url"))
        if not title or not url:
            continue
        raw_published = raw.get("published_at")
        published_at = raw_published or now_utc()
        normalized.append(
            {
                "id": make_id(url),
                "source_id": source_id,
                "title": title,
                "url": url,
                "published_at": to_iso(published_at),
                # 信源没给真实发布时间时才为 True——first_seen.pin_fallback_timestamps
                # 会用它把 published_at 钉在"首次发现时间"，而不是每轮都重新盖成当前时间
                # （否则这条内容永远滑不出处理窗口，见 scripts/first_seen.py 顶部说明）。
                # 该字段是内部实现细节，pin_fallback_timestamps 处理完会 pop 掉，不进入输出 schema。
                "_published_at_is_fallback": raw_published is None,
                "raw_text": (raw.get("raw_text") or "")[:1000],
                "category_hint": category_hint,
                "image_url": safe_http_url(raw.get("image_url")),
            }
        )
    return normalized
