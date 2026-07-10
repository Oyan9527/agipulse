"""生成 Atom feed（docs/feed.xml），让读者能用 RSS 阅读器订阅精选流。

对标产品都提供订阅入口，一个新闻聚合站没有 RSS 是说不过去的——读者只能靠自己记得来看。

条目正文来自第三方源，含 & < > 引号等字符。一律交给 ElementTree 做转义，不手拼字符串：
手拼 XML 迟早会因为某条标题里的 `&` 生成非法文档，让所有订阅者的阅读器直接报错。
"""
from xml.etree import ElementTree as ET

from .util import get_logger, now_utc, safe_http_url

log = get_logger(__name__)

ATOM_NS = "http://www.w3.org/2005/Atom"
SITE_URL = "https://oyan9527.github.io/agipulse/"
FEED_URL = SITE_URL + "feed.xml"
FEED_TITLE = "硅基脉动 · AGI Pulse"
FEED_SUBTITLE = "300+ 信源聚合，多源确认与 AI 打分后的 AI 行业精选"
MAX_ENTRIES = 50


def _entry_title(item):
    """中文读者优先看译题；没有译题（原本就是中文）时用原标题。"""
    title_zh = (item.get("title_zh") or "").strip()
    title = (item.get("title") or "").strip()
    return title_zh or title


def _entry_summary(item):
    summary = (item.get("summary_zh") or "").strip()
    reason = (item.get("reason_zh") or "").strip()
    if reason.startswith("[mock]"):
        reason = ""
    text = summary or reason
    count = item.get("multi_source_count") or 1
    if count > 1:
        text = f"[{count} 源确认] {text}".strip()
    return text


def _sub(parent, tag, **attrs):
    """子元素一律带上 Atom 命名空间。若只写 tag 名，元素在内存里就没有命名空间，
    序列化时只是恰好落进默认命名空间——findall 会找不到它，严格的解析器也未必买账。"""
    return ET.SubElement(parent, f"{{{ATOM_NS}}}{tag}", **attrs)


def build_feed(curated_items, max_entries=MAX_ENTRIES):
    """按发布时间倒序取最新若干条精选，生成 Atom XML 字符串。"""
    ET.register_namespace("", ATOM_NS)
    feed = ET.Element(f"{{{ATOM_NS}}}feed")

    _sub(feed, "title").text = FEED_TITLE
    _sub(feed, "subtitle").text = FEED_SUBTITLE
    _sub(feed, "link", href=SITE_URL)
    _sub(feed, "link", rel="self", href=FEED_URL, type="application/atom+xml")
    _sub(feed, "id").text = SITE_URL
    _sub(feed, "updated").text = now_utc().isoformat()

    entries = sorted(curated_items, key=lambda x: x["published_at"], reverse=True)[:max_entries]
    kept = 0
    for item in entries:
        url = safe_http_url(item.get("url"))
        if not url:
            continue  # 与前端同样的协议白名单：不把 javascript: 链接塞进订阅者的阅读器

        entry = _sub(feed, "entry")
        _sub(entry, "title").text = _entry_title(item)
        _sub(entry, "link", href=url)
        # id 必须全局唯一且稳定：用条目 id（url 的 sha1），而不是 url 本身——
        # url 可能带跟踪参数、也可能被源站改写，那样阅读器会把同一条当成新条目重复推送。
        _sub(entry, "id").text = f"urn:agi-pulse:{item['id']}"
        _sub(entry, "updated").text = item["published_at"]
        summary = _entry_summary(item)
        if summary:
            _sub(entry, "summary").text = summary
        if item.get("category"):
            _sub(entry, "category", term=item["category"])
        if item.get("source_id"):
            author = _sub(entry, "author")
            _sub(author, "name").text = item["source_id"]
        kept += 1

    log.info("feed: %d entries", kept)
    return ET.tostring(feed, encoding="unicode", xml_declaration=True)
