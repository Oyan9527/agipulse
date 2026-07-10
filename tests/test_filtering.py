"""AI 相关性分层过滤 + 深度推荐筛选 + LLM 缓存 schema 迁移的回归测试。

三处都踩过坑：
- 对所有源一刀切做关键词过滤，误杀了 43% 的真 AI 内容（官方博客/arXiv 标题不写"AI"）。
- 深度推荐一度用正文字数当判据，被 arXiv 摘要刷屏。
- 缓存新增字段后，旧条目会带着 None 混进展示流。
"""
from datetime import datetime, timedelta, timezone

from scripts.daily_brief import build_daily_brief
from scripts.llm_cache import split_by_cache
from scripts.run_pipeline import filter_ai_relevance

AI_CFG = {"ai_relevance": {"strict_source_prefixes": ["zh-"], "strict_sources": ["36kr", "ifanr"]}}
NOW = datetime.now(timezone.utc)


# --- AI 相关性：只对通用源过滤，天然 AI 源一律放行 ---

def test_natural_ai_sources_never_filtered():
    # 这些标题不含任何 AI 关键词，但源本身就是 AI 专属，必须全部保留
    items = [
        {"id": "1", "source_id": "openai-blog", "title": "Introducing GeneBench-Pro"},
        {"id": "2", "source_id": "deepmind-blog", "title": "DiffusionGemma: 4x faster"},
        {"id": "3", "source_id": "arxiv-cs-lg", "title": "Architecture Generalization with MetaNCA"},
        {"id": "4", "source_id": "gh-vllm", "title": "vllm v0.9.0"},
    ]
    assert len(filter_ai_relevance(items, AI_CFG)) == 4


def test_general_sources_drop_non_ai_content():
    items = [
        {"id": "1", "source_id": "zh-ithome", "title": "小米澎程首款 SUV 命名揭晓"},
        {"id": "2", "source_id": "36kr", "title": "恒指午间休盘涨1.86%"},
        {"id": "3", "source_id": "ifanr", "title": "6 月汽车出口首破百万辆"},
    ]
    assert filter_ai_relevance(items, AI_CFG) == []


def test_general_sources_keep_real_ai_content():
    items = [
        {"id": "1", "source_id": "zh-cnbeta", "title": "OpenAI正式推出GPT-5.6系列模型"},
        {"id": "2", "source_id": "zh-ithome", "title": "美国拟禁止纯视觉自动驾驶汽车"},
    ]
    assert len(filter_ai_relevance(items, AI_CFG)) == 2


# --- 今日深度推荐：靠 LLM 判定的内容属性，不靠字数；且不能排除论文 ---

BRIEF_CFG = {"daily_brief": {
    "top_n": 12, "min_depth_score": 0.6,
    "exclude_content_types": ["资讯快讯", "产品发布", "营销推广"],
    "max_per_category": 4,
}}


def _scored(iid, title, ctype, depth, score=0.7, cat="论文研究"):
    return {"id": iid, "title": title, "content_type": ctype, "depth_score": depth,
            "weighted_score": score, "category": cat,
            "published_at": (NOW - timedelta(hours=2)).isoformat()}


def test_deep_brief_keeps_research_and_analysis_drops_news():
    items = [
        _scored("paper", "Anthropic: 大模型内部的思考空间", "研究论文", 0.92),
        _scored("deep", "Loop engineering 实践复盘", "深度分析", 0.90, cat="技巧与观点"),
        _scored("launch", "OpenAI 发布 GPT-5.6", "产品发布", 0.20, score=0.98, cat="模型发布"),
        _scored("news", "某公司完成 A 轮融资", "资讯快讯", 0.10, cat="行业动态"),
        _scored("ad", "AI 测评小程序上新", "营销推广", 0.05, cat="行业动态"),
        _scored("shallow", "一篇泛泛的评论", "观点评论", 0.45, cat="技巧与观点"),
    ]
    ids = [i["id"] for i in build_daily_brief(items, BRIEF_CFG)["items"]]
    assert ids == ["paper", "deep"]   # 按 depth 降序；资讯/营销/浅文全部排除


def test_deep_brief_caps_one_category_so_papers_dont_flood():
    items = [_scored(f"p{i}", f"论文{i}", "研究论文", 0.85) for i in range(6)]
    items.append(_scored("deep", "工程复盘", "深度分析", 0.80, cat="技巧与观点"))
    result = build_daily_brief(items, BRIEF_CFG)["items"]
    papers = [i for i in result if i["category"] == "论文研究"]
    assert len(papers) == 4          # max_per_category
    assert "deep" in [i["id"] for i in result]


def test_deep_brief_returns_empty_rather_than_padding_with_news():
    items = [_scored("news", "融资快讯", "资讯快讯", 0.1, cat="行业动态")]
    assert build_daily_brief(items, BRIEF_CFG)["items"] == []


# --- LLM 缓存：新增打分字段后，旧条目必须重新打分而不是带着 None 混进来 ---

def _entry(**kw):
    base = {"status": "scored", "category": "x", "reason_zh": "r", "title_zh": None,
            "weighted_score": 0.8, "score_breakdown": {}}
    base.update(kw)
    return base


def test_cache_entry_missing_new_field_is_rescored():
    cache = {"old": _entry(depth_score=0.9)}          # 缺 summary_zh（后加的字段）
    scored, rejected, uncached = split_by_cache([{"id": "old"}], cache)
    assert scored == [] and [i["id"] for i in uncached] == ["old"]


def test_cache_entry_with_all_fields_is_reused():
    cache = {"ok": _entry(depth_score=0.9, summary_zh="中文摘要")}
    scored, _, uncached = split_by_cache([{"id": "ok"}], cache)
    assert [i["id"] for i in scored] == ["ok"] and uncached == []


def test_cache_null_value_still_counts_as_present():
    # summary_zh 合法地为 None（模型没给），键存在就不该触发重打分
    cache = {"ok": _entry(depth_score=0.9, summary_zh=None)}
    scored, _, uncached = split_by_cache([{"id": "ok"}], cache)
    assert [i["id"] for i in scored] == ["ok"] and uncached == []


def test_cache_rejected_items_excluded_without_llm_call():
    cache = {"bad": {"status": "rejected"}}
    scored, rejected, uncached = split_by_cache([{"id": "bad"}], cache)
    assert rejected == {"bad"} and scored == [] and uncached == []
