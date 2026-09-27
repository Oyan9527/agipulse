"""AI 每日总结的回归测试（不触真实 DeepSeek，只测选材、mock 路径与空态）。"""
from datetime import datetime, timedelta, timezone

from scripts.daily_digest import BEIJING_TZ, build_daily_digest, _todays_top

NOW = datetime.now(timezone.utc)
# _todays_top() 筛的是"北京时间的今天"，而这里的基准是 UTC 当下。北京 00:00-01:00
# 这一小时里，NOW-1h 会掉回北京的昨天，本文件里所有 hours_ago=1 的条目全被过滤掉，
# 四个用例无关代码改动地集体变红（踩过一次）。定时流水线跑在 UTC 17:00 = 北京 01:00，
# 距这个窗口只差一小时，排队稍有延迟就会撞上——测试不能挂在"现在几点"上。
_BJ_TODAY_START = NOW.astimezone(BEIJING_TZ).replace(hour=0, minute=0, second=0, microsecond=0)


def _item(iid, title, hours_ago=1, score=0.5, msc=1, title_zh=None):
    published = NOW - timedelta(hours=hours_ago)
    # 24 小时内的条目语义上是"今天的新闻"，真跨回昨天就钳到今天刚开始那会儿。
    # hours_ago=48 这类"旧闻"用例不受影响，它们本来就该落在今天之外。
    if hours_ago < 24 and published.astimezone(BEIJING_TZ) < _BJ_TODAY_START:
        published = (_BJ_TODAY_START + timedelta(minutes=30)).astimezone(timezone.utc)
    return {
        "id": iid, "title": title, "title_zh": title_zh,
        "weighted_score": score, "multi_source_count": msc,
        "published_at": published.isoformat(),
    }


def test_empty_when_no_stories_today():
    old = [_item("a", "旧闻", hours_ago=48)]
    assert build_daily_digest(old, mock=True)["summary"] == ""


def test_mock_summary_is_chinese_placeholder_not_llm():
    items = [_item("a", "GPT-5.6 发布", title_zh="GPT-5.6 发布", msc=5)]
    out = build_daily_digest(items, mock=True)
    assert "〔示例总结〕" in out["summary"]
    assert "date" in out and "generated_at" in out


def test_top_ranks_by_multisource_then_score():
    items = [
        _item("hi", "高分单源", score=0.99, msc=1),
        _item("multi", "多源确认", score=0.70, msc=4),
    ]
    top = _todays_top(items)
    assert top[0]["id"] == "multi"   # 多源优先于高分


def test_top_prefers_translated_title_in_payload():
    items = [_item("a", "English Title", title_zh="中文译题", msc=3)]
    out = build_daily_digest(items, mock=True)
    assert "中文译题" in out["summary"]


def test_top_capped_at_max_input():
    items = [_item(str(i), f"t{i}", msc=1, score=i / 100) for i in range(30)]
    assert len(_todays_top(items)) == 12   # MAX_INPUT_STORIES


def test_top_includes_beijing_early_morning_item_with_yesterday_utc_date():
    """北京时间凌晨(0-8点)发布的条目，其 UTC 日期仍是"昨天"，但北京日历上属于"今天"，
    不应被"今日头条"漏掉（回归：曾经按 UTC 日期比对导致这类条目被排除）。"""
    now_bj = datetime.now(BEIJING_TZ)
    published_bj = now_bj.replace(hour=2, minute=0, second=0, microsecond=0)
    published_at = published_bj.astimezone(timezone.utc).isoformat()

    # 确认这条目确实落在"UTC 日期属于昨天"的场景，否则这个回归测试没有意义
    assert published_at[:10] != now_bj.date().isoformat()

    item = _item("early-bj", "凌晨新闻", msc=1)
    item["published_at"] = published_at
    top = _todays_top([item])
    assert top and top[0]["id"] == "early-bj"
