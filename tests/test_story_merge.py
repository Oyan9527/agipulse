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
    assert _strong_entities("LongCat v2 released today") == {"longcat2"}           # "v" 前缀版本号


def test_ignores_generic_noun_number_pairs():
    # 这些若被当成产品名，会把毫无关系的文章并到一起
    assert _strong_entities("PRX Part 4: Our Data Strategy") == set()
    assert _strong_entities("Top 10 prompt tricks") == set()
    assert _strong_entities("step 2 of the pipeline") == set()      # 小写不算产品名
    assert _strong_entities("AMD 锐龙 AI 9 HX 470 游戏本") == set()   # AI 9 是型号噪声


def test_extracts_brand_plus_letter_model_identifiers():
    # 品牌名 + 独立型号(字母+数字，而非纯数字)——Kimi K3/DeepSeek R1/OpenAI o3 这类命名，
    # _ENTITY_RE 要求品牌名后面直接接纯数字，抓不住中间那个型号字母。
    # 真实踩过的坑：Kimi K3 发布当天 5 个不同信源报道，entities 全部是空集合，
    # 一个都没识别成同一实体，本该合并的多源头条被拆成了 5 个独立故事。
    assert _strong_entities("Kimi K3 正式发布") == {"kimik3"}
    assert _strong_entities("DeepSeek R1 亮相：推理能力对标 o1") == {"deepseekr1"}
    assert _strong_entities("OpenAI o3 发布") == {"openaio3"}


def test_brand_model_does_not_duplicate_v_prefix_entity():
    # "Name v2" 已经由 _ENTITY_RE 处理成 {"longcat2"}；新增的品牌+型号判据不该
    # 把同一个 "v2" 又提取成 "longcatv2"，产生两个指向同一件事的冗余实体。
    assert _strong_entities("LongCat v2 released today") == {"longcat2"}


def test_brand_model_still_ignores_stopword_sections():
    # 论文/文档里常见的"Section A1"/"Table B2"这类编号引用，不该被误判成产品型号——
    # 复用同一份 _ENTITY_STOPWORDS。
    assert _strong_entities("See Section A1 for details") == set()
    assert _strong_entities("Table B2 summarizes the results") == set()


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


def test_merges_kimi_k3_launch_across_five_real_sources():
    # 真实复现的漏合并案例：Kimi K3 发布当天 5 个不同信源分别报道，措辞差异很大
    # （中文解读/纯中文公告/英文技术简报/英文评测），此前 entities 全部提取为空集合，
    # 一个都没识别成同一实体，5 条本该合并的报道被拆成了 5 个独立故事、头条位置
    # 被别的内容占据。这里用真实标题锁定修复后的行为。
    items = [
        _item("a", "Kimi K3 全面解读：2.8 万亿参数、48 小时造芯片、以及一个正在被开源模型追上的 AI 竞争格局",
              hours_ago=20, source="zh-oschina"),
        _item("b", "Kimi K3 正式发布", hours_ago=18, source="zh-oschina-2"),
        _item("c", "月之暗面宣布首个 3 万亿参数开放权重模型 Kimi K3", hours_ago=16, source="zh-solidot"),
        _item("d", "[AINews] Kimi K3 2.8T-A50B: the largest open model ever released; Opus 4.8-class at Sonnet 5 pricing",
              hours_ago=10, source="latent-space"),
        _item("e", "Kimi K3, and what we can still learn from the pelican benchmark",
              hours_ago=2, source="simonwillison"),
    ]
    _, stories = merge_stories(items, WEIGHTS)
    assert len(stories) == 1
    assert stories[0]["source_count"] == 5


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


def test_same_entity_but_different_event_stays_separate():
    # 共享实体 {'model3'}，但讲的是两件不相关的事——仅凭实体交集不该合并，
    # 否则任何两条提到同一产品的无关新闻都会被并成一个故事。
    items = [
        _item("a", "Model 3 gets software update", hours_ago=18, source="s1"),
        _item("b", "Model 3 recall issued by regulators", source="s2"),
    ]
    _, stories = merge_stories(items, WEIGHTS)
    assert len(stories) == 2


def test_two_different_incident_types_stay_separate():
    # 曾经的漏洞：召回/诉讼/泄露 全塞进一个"incident"大类，两件都属于该大类但实际
    # 无关的不同事件（数据泄露 vs 版权诉讼）因为类别集合有交集被误判成可以合并。
    # 拆分子类后，security_incident 和 legal 应该是不相交的类别，正确拦截合并。
    items = [
        _item("a", "GPT-5.6 suffers data breach", hours_ago=10, source="s1"),
        _item("b", "OpenAI sued over GPT-5.6 copyright infringement", source="s2"),
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
