"""同事件合并与折叠的回归测试。

背景：GPT-5.6 发布当天有 15 条跨源报道，信息流里出现了 15 张卡片。两个原因——
词袋相似度抓不住措辞差异极大的同一事件；合并结果算出来了却没被用来去重。
这里锁住修复后的行为，避免以后调参把它改回去。
"""
from datetime import datetime, timedelta, timezone

from scripts.story_merge import _strong_entities, collapse_stories, merge_stories

WEIGHTS = {"story_merge": {"window_hours": 36, "similarity_threshold": 0.55, "merge_by_entity": True}}
NOW = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)


def _item(iid, title, hours_ago=0, score=0.5, source=None, raw=""):
    return {
        "id": iid,
        "title": title,
        "raw_text": raw,
        "url": f"https://example.com/{iid}",
        "source_id": source or f"src-{iid}",
        "published_at": (NOW - timedelta(hours=hours_ago)).isoformat(),
        "weighted_score": score,
    }


# --- 强实体提取：模型名要认出来，通用的"名词+数字"不能误判成产品名 ---

def test_extracts_model_identifiers():
    assert _strong_entities("The new GPT-5.6 family: Luna, Terra, Sol") == {"gpt5.6"}
    assert _strong_entities("OpenAI says GPT 5.6 is preferred") == {"gpt5.6"}       # 空格分隔
    assert _strong_entities("美团 LongCat-2.0 正式发布") == {"longcat2.0"}          # 中文标题里的英文名
    assert _strong_entities("Introducing Gemini 3.5 Flash") == {"gemini3.5"}


def test_ignores_generic_noun_number_pairs():
    # 这些若被当成产品名，会把毫无关系的文章并到一起
    assert _strong_entities("PRX Part 4: Our Data Strategy") == set()
    assert _strong_entities("Top 10 prompt tricks") == set()
    assert _strong_entities("step 2 of the pipeline") == set()      # 小写不算产品名
    assert _strong_entities("AMD 锐龙 AI 9 HX 470 游戏本") == set()   # AI 9 是型号噪声


# --- 合并：措辞不同但谈同一个模型的报道要并成一个故事 ---

def test_merges_same_event_across_wildly_different_wording():
    items = [
        _item("a", "The new GPT-5.6 family: Luna, Terra, Sol", hours_ago=10, source="s1"),
        _item("b", "OpenAI发布GPT-5.6系列模型：性能全面超越竞品", hours_ago=8, source="s2"),
        _item("c", "[AINews] OpenAI launches GPT 5.6 Sol/Terra/Luna", hours_ago=2, source="s3"),
    ]
    _, stories = merge_stories(items, WEIGHTS)
    assert len(stories) == 1
    assert stories[0]["source_count"] == 3


def test_time_window_anchors_on_latest_member_not_seed():
    # 单链接：a→b 相隔 30h、b→c 相隔 30h，都在 36h 窗内，应连成一条链。
    # 若锚点固定在种子 a，c 距 a 有 60h 会被踢出去，同一事件就被拆成两个故事。
    items = [
        _item("a", "GPT-5.6 launches", hours_ago=60, source="s1"),
        _item("b", "GPT-5.6 rolls out", hours_ago=30, source="s2"),
        _item("c", "GPT-5.6 now available", hours_ago=0, source="s3"),
    ]
    _, stories = merge_stories(items, WEIGHTS)
    assert len(stories) == 1


def test_unrelated_items_stay_separate():
    items = [
        _item("a", "GPT-5.6 launches", source="s1"),
        _item("b", "宇树 G1 完成机器人外科手术", source="s2"),
    ]
    _, stories = merge_stories(items, WEIGHTS)
    assert len(stories) == 2


def test_entity_merge_can_be_disabled():
    cfg = {"story_merge": {**WEIGHTS["story_merge"], "merge_by_entity": False}}
    items = [
        _item("a", "The new GPT-5.6 family: Luna, Terra, Sol", source="s1"),
        _item("b", "OpenAI发布GPT-5.6系列模型", source="s2"),
    ]
    _, stories = merge_stories(items, cfg)
    assert len(stories) == 2   # 关掉实体判据后，仅靠词袋相似度合不到一起


# --- 折叠：每个故事只出一条卡片，代表要挑分最高的 ---

def test_collapse_keeps_one_representative_per_story():
    items = [
        dict(_item("a", "早的那条", hours_ago=5, score=0.60), story_id="s"),
        dict(_item("b", "分最高的那条", hours_ago=1, score=0.90), story_id="s"),
        dict(_item("c", "另一个故事", score=0.30), story_id="t"),
    ]
    kept = collapse_stories(items)
    assert sorted(i["id"] for i in kept) == ["b", "c"]


def test_collapse_breaks_score_tie_by_earliest():
    items = [
        dict(_item("late", "晚", hours_ago=1, score=0.8), story_id="s"),
        dict(_item("early", "早", hours_ago=9, score=0.8), story_id="s"),
    ]
    assert collapse_stories(items)[0]["id"] == "early"


def test_collapse_passes_through_items_without_story_id():
    # 未打分条目没有 story_id，不能被互相当成同一故事而误删
    items = [_item("a", "x"), _item("b", "y")]
    assert len(collapse_stories(items)) == 2
