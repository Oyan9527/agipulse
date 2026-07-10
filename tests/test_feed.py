"""Atom feed 的回归测试。

最关键的是转义：条目标题/摘要来自第三方源，含 & < > 引号是常态。
一旦生成非法 XML，所有订阅者的阅读器都会报错——而站点本身看起来毫无异常。
"""
from xml.etree import ElementTree as ET

from scripts.feed import ATOM_NS, build_feed

NS = {"a": ATOM_NS}


def _item(iid="1", **kw):
    base = {
        "id": iid,
        "title": "Some Title",
        "url": f"https://example.com/{iid}",
        "published_at": "2026-07-09T19:46:38+00:00",
        "category": "模型发布",
        "source_id": "openai-blog",
    }
    base.update(kw)
    return base


def _parse(xml):
    return ET.fromstring(xml)


def test_feed_is_well_formed_and_has_entries():
    root = _parse(build_feed([_item("1"), _item("2")]))
    assert root.tag == f"{{{ATOM_NS}}}feed"
    assert len(root.findall("a:entry", NS)) == 2


def test_special_characters_are_escaped_not_breaking_xml():
    nasty = 'Tom & Jerry <script>alert("x")</script> — 引号"和\'撇号'
    xml = build_feed([_item("1", title=nasty, summary_zh=nasty)])
    root = _parse(xml)   # 解析不抛异常即证明转义正确
    title = root.find("a:entry/a:title", NS).text
    assert title == nasty                 # 内容原样还原
    assert "<script>" not in xml          # 原始尖括号不得出现在序列化结果里


def test_entry_prefers_chinese_title():
    root = _parse(build_feed([_item("1", title="English Title", title_zh="中文译题")]))
    assert root.find("a:entry/a:title", NS).text == "中文译题"


def test_entry_falls_back_to_original_title_when_no_translation():
    root = _parse(build_feed([_item("1", title="纯中文标题", title_zh=None)]))
    assert root.find("a:entry/a:title", NS).text == "纯中文标题"


def test_summary_prefers_summary_zh_over_reason_zh():
    root = _parse(build_feed([_item("1", summary_zh="内容摘要", reason_zh="推荐理由")]))
    assert root.find("a:entry/a:summary", NS).text == "内容摘要"


def test_mock_reason_never_leaks_into_feed():
    root = _parse(build_feed([_item("1", reason_zh="[mock] 本地调试文本")]))
    assert root.find("a:entry/a:summary", NS) is None


def test_multi_source_count_is_surfaced():
    root = _parse(build_feed([_item("1", summary_zh="摘要", multi_source_count=11)]))
    assert root.find("a:entry/a:summary", NS).text.startswith("[11 源确认]")


def test_dangerous_url_entry_is_dropped():
    entries = _parse(build_feed([_item("1", url="javascript:alert(1)"), _item("2")]))
    ids = [e.find("a:id", NS).text for e in entries.findall("a:entry", NS)]
    assert ids == ["urn:agi-pulse:2"]


def test_entry_id_is_stable_and_not_the_url():
    # 用 url 当 id 的话，源站给 url 加跟踪参数就会被阅读器当成新条目重复推送
    root = _parse(build_feed([_item("abc123")]))
    assert root.find("a:entry/a:id", NS).text == "urn:agi-pulse:abc123"


def test_entries_sorted_newest_first_and_capped():
    items = [_item(str(i), published_at=f"2026-07-{i:02d}T00:00:00+00:00") for i in range(1, 6)]
    root = _parse(build_feed(items, max_entries=3))
    ids = [e.find("a:id", NS).text for e in root.findall("a:entry", NS)]
    assert ids == ["urn:agi-pulse:5", "urn:agi-pulse:4", "urn:agi-pulse:3"]


def test_empty_feed_still_valid():
    root = _parse(build_feed([]))
    assert root.findall("a:entry", NS) == []
    assert root.find("a:title", NS) is not None
