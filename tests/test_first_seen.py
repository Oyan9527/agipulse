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


# --- 整合场景：retain_ids 不能用 intake_quotas 筛完之后的 processable 计算 ---
# （复现 run_pipeline.run() 里实际发生的漏洞：配额把一条内容从这一轮的 processable
#  里挤出去，不代表它已经过期——它还在48h窗口内，缓存条目不该被清掉，否则下一轮
#  重新抓到会被当成"首次发现"重新盖成"现在"，first_seen 机制被 intake_quotas 绕过）

def test_quota_trimmed_item_keeps_its_pinned_timestamp_across_runs(tmp_path):
    from datetime import timedelta

    from scripts.dedupe import dedupe
    from scripts.run_pipeline import apply_intake_quotas, filter_ai_relevance, filter_processing_window
    from scripts.util import now_utc

    weights_cfg = {
        "dedupe": {"fuzzy_title_threshold": 90, "window_hours": 48},
        "ai_relevance": {},
        "intake_quotas": {"论文研究": {"max": 1}},  # 只给论文研究1个名额，两条会有一条被截掉
    }

    def make_items(stamp):
        # 两条标题完全不同（避免被 dedupe 当重复），都属于配额只给1个名额的类别，
        # 且都标记为"没有真实发布时间"（真实场景里就是信源本身不提供日期的情况）
        return [
            {"id": "paperA", "title": "Paper A about attention mechanisms", "source_id": "s1",
             "published_at": stamp, "category_hint": ["论文研究"], "raw_text": "",
             "_published_at_is_fallback": True},
            {"id": "paperB", "title": "Paper B about reward modeling", "source_id": "s2",
             "published_at": stamp, "category_hint": ["论文研究"], "raw_text": "",
             "_published_at_is_fallback": True},
        ]

    def run_once_and_save(fake_now_stamp):
        # 模拟 run_pipeline.run() 里真实的调用顺序：pin -> dedupe -> ai_relevance ->
        # (用截断前的窗口集合算 retain_ids，这是本次要验证的修复点) -> intake_quotas -> processable
        fs_cache = load_first_seen(tmp_path)
        items = make_items(fake_now_stamp)
        pin_fallback_timestamps(items, fs_cache)
        pre_quota_items = items  # 配额截断前的快照，供断言核实"两条都还在窗口内"
        items = dedupe(items, weights_cfg)
        items = filter_ai_relevance(items, weights_cfg)
        still_in_window_ids = {it["id"] for it in filter_processing_window(items, hours=48)}
        save_first_seen(tmp_path, fs_cache, retain_ids=still_in_window_ids)
        items = apply_intake_quotas(items, weights_cfg)
        processable = filter_processing_window(items, hours=48)
        return pre_quota_items, processable

    now = now_utc()
    # 第一轮：两条都是首次发现，都被 pin 到同一个时间戳；配额只给1个名额，
    # paperA 在输入列表里排前面，sort 是稳定排序，同分时 paperA 赢得名额，paperB 被截掉。
    stamp1 = now.isoformat()
    pre_quota1, processable1 = run_once_and_save(stamp1)
    assert {it["id"] for it in processable1} == {"paperA"}      # 验证 paperB 确实被配额截掉了
    assert {it["id"] for it in pre_quota1} == {"paperA", "paperB"}  # 但两条这一轮(截断前)都还在

    # 第二轮：4小时后同样两条被重新抓到（信源没日期，正常情况下会被 normalize.py
    # 重新盖成"现在"）——这里传入一个明显更晚的时间戳模拟"重新抓取时刻"
    stamp2 = (now + timedelta(hours=4)).isoformat()
    pre_quota2, _processable2 = run_once_and_save(stamp2)
    pinned_a = next(it for it in pre_quota2 if it["id"] == "paperA")["published_at"]
    pinned_b = next(it for it in pre_quota2 if it["id"] == "paperB")["published_at"]

    # 关键断言：paperB 虽然第一轮被配额挤出了 processable，但它仍在48h窗口内，
    # 第二轮应该复用第一轮钉住的时间戳，而不是被当成"首次发现"重新盖成 stamp2。
    assert pinned_a == stamp1
    assert pinned_b == stamp1
