"""AI 每日总结的回归测试（不触真实 DeepSeek，只测选材、mock 路径与空态）。"""
from datetime import datetime, timedelta, timezone

from scripts.daily_digest import build_daily_digest, _todays_top

NOW = datetime.now(timezone.utc)


def _item(iid, title, hours_ago=1, score=0.5, msc=1, title_zh=None):
    return {
        "id": iid, "title": title, "title_zh": title_zh,
        "weighted_score": score, "multi_source_count": msc,
        "published_at": (NOW - timedelta(hours=hours_ago)).isoformat(),
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
