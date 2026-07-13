"""发布时间缺失兜底的回归测试（scripts.normalize + scripts.first_seen）。

踩过的坑：美团技术团队博客等信源的 RSS 压根不提供 <pubDate>/<updated>，
normalize.py 只能兜底成 now_utc()。若不做任何处理，同一条旧内容(url不变、
id因此不变)每轮重新抓到都会被重新盖成"刚刚发布"，永远滑不出48h处理窗口，
实测一篇两周前的旧文靠这个漏洞连续两周霸占精选/头条。修复后应该只在
"首次发现"这一轮生效一次，之后复用钉住的时间、像正常内容一样自然老化。
"""
import io
import json

from scripts.first_seen import load_first_seen, pin_fallback_timestamps, save_first_seen
from scripts.normalize import normalize_items


def test_normalize_flags_missing_date_as_fallback():
    raw = [{"title": "t", "url": "https://ok.com/1", "published_at": None}]
    out = normalize_items(raw, {"id": "s", "category_hint": []})
    assert out[0]["_published_at_is_fallback"] is True


def test_normalize_does_not_flag_real_date():
    from datetime import datetime, timezone
    raw = [{"title": "t", "url": "https://ok.com/1", "published_at": datetime(2026, 6, 30, tzinfo=timezone.utc)}]
    out = normalize_items(raw, {"id": "s", "category_hint": []})
    assert out[0]["_published_at_is_fallback"] is False
    assert out[0]["published_at"].startswith("2026-06-30")


def _fallback_item(iid, stamped_now="2026-07-13T04:55:10+00:00"):
    return {"id": iid, "title": "t", "published_at": stamped_now, "_published_at_is_fallback": True}


def _real_date_item(iid, real="2026-06-30T00:00:00+00:00"):
    return {"id": iid, "title": "t", "published_at": real, "_published_at_is_fallback": False}


def test_pin_records_first_seen_time_when_not_cached():
    items = [_fallback_item("a", stamped_now="2026-07-13T04:55:10+00:00")]
    cache = {}
    pin_fallback_timestamps(items, cache)
    assert cache["a"] == "2026-07-13T04:55:10+00:00"
    assert items[0]["published_at"] == "2026-07-13T04:55:10+00:00"


def test_pin_reuses_cached_time_instead_of_todays_refetch():
    # 关键场景：这条内容两天前首次被发现(缓存里存的是两天前)，今天又被重新抓到，
    # normalize.py 会把它重新盖成"今天"——pin 必须把它拉回两天前的原始首见时间，
    # 而不是相信今天这次刷新出来的时间戳。
    items = [_fallback_item("a", stamped_now="2026-07-13T04:55:10+00:00")]
    cache = {"a": "2026-07-11T08:00:00+00:00"}
    pin_fallback_timestamps(items, cache)
    assert items[0]["published_at"] == "2026-07-11T08:00:00+00:00"
    assert cache["a"] == "2026-07-11T08:00:00+00:00"   # 缓存本身不会被今天的新时间覆盖


def test_pin_leaves_real_dated_items_untouched_and_uncached():
    items = [_real_date_item("b")]
    cache = {}
    pin_fallback_timestamps(items, cache)
    assert items[0]["published_at"] == "2026-06-30T00:00:00+00:00"
    assert "b" not in cache   # 有真实日期的条目不需要进这个缓存


def test_pin_strips_internal_flag_from_all_items():
    items = [_fallback_item("a"), _real_date_item("b")]
    pin_fallback_timestamps(items, {})
    assert "_published_at_is_fallback" not in items[0]
    assert "_published_at_is_fallback" not in items[1]


def test_save_prunes_ids_no_longer_in_window(tmp_path):
    cache = {"still-relevant": "2026-07-13T00:00:00+00:00", "expired": "2026-07-01T00:00:00+00:00"}
    save_first_seen(tmp_path, cache, retain_ids={"still-relevant"})
    reloaded = load_first_seen(tmp_path)
    assert reloaded == {"still-relevant": "2026-07-13T00:00:00+00:00"}


def test_load_first_seen_missing_file_returns_empty_dict(tmp_path):
    assert load_first_seen(tmp_path / "does-not-exist") == {}


def test_load_first_seen_corrupt_file_recovers_empty(tmp_path):
    path = tmp_path / "first-seen-cache.json"
    io.open(path, "w", encoding="utf-8").write("{not valid json")
    assert load_first_seen(tmp_path) == {}


def test_round_trip_save_then_load(tmp_path):
    cache = {"x": "2026-07-13T01:00:00+00:00"}
    save_first_seen(tmp_path, cache, retain_ids={"x"})
    assert load_first_seen(tmp_path) == cache
