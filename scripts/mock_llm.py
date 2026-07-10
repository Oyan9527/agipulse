"""确定性的启发式打分器，用于本地开发/测试（--mock-llm），不消耗真实 DeepSeek 额度。
不用于生产：生产环境应使用 llm_prefilter.py / llm_score.py 调用真实 DeepSeek API。
打分逻辑尽量贴近真实四维度含义，便于前端开发阶段拿到"形状真实、内容合理"的数据。
"""
import re
from datetime import datetime, timezone

from .util import get_logger

log = get_logger(__name__)

_CJK_RE = re.compile(r"[一-鿿]")

_NOISE_PATTERNS = re.compile(
    r"\b(sponsored|advertisement|hiring|discount code|giveaway)\b", re.IGNORECASE
)


def mock_prefilter(items):
    kept = [it for it in items if not _NOISE_PATTERNS.search(it["title"] + it["raw_text"])]
    log.info("mock_prefilter: %d -> %d items", len(items), len(kept))
    return kept


def _guess_category(item, categories):
    hint = item.get("category_hint") or []
    if hint:
        return hint[0]
    text = (item["title"] + " " + item["raw_text"]).lower()
    for cat in categories:
        for kw in cat.get("keywords_en", []):
            if kw.lower() in text:
                return cat["id"]
        for kw in cat.get("keywords_zh", []):
            if kw in text:
                return cat["id"]
    return categories[0]["id"] if categories else "行业动态"


# mock 的"深度"启发式：真实环境由 DeepSeek 判断 content_type/depth_score（见 llm_score.py），
# 这里只需产出形状真实、分布合理的数据供前端联调。
# 判定顺序：论文 → 营销 → 资讯 → 深度 → 观点。营销/资讯必须先于深度判定，
# 否则"AI测评小程序上新""[推广]…踩坑汇总"会因撞上"评测/踩坑"被误判成深度分析。
_MARKETING_RE = re.compile(r"推广|软文|上新|小程序|福利|活动报名|限时|优惠|抽奖", re.IGNORECASE)
_NEWSY_RE = re.compile(
    r"融资|收购|发布会|上线|涨|榜|财报|任命|裁员|快讯|晚报|早报|新品"
    r"|launches?|announces?|releases?|now available|introducing|raises",
    re.IGNORECASE,
)
_DEEP_RE = re.compile(
    r"为什么|原理|机制|复盘|实践|踩坑|架构|综述|解析|深度"
    r"|inside|deep dive|lessons|architecture|interpretab|understanding",
    re.IGNORECASE,
)


def _mock_content_type(item):
    title = item["title"]
    if (item.get("category_hint") or [None])[0] == "论文研究" or item["source_id"].startswith("arxiv-"):
        return "研究论文"
    if _MARKETING_RE.search(title):
        return "营销推广"
    if _NEWSY_RE.search(title):
        return "资讯快讯"
    if _DEEP_RE.search(title):
        return "深度分析"
    return "观点评论"


_TAG_RE = re.compile(r"<[^>]+>")


def _mock_summary_zh(item):
    """mock 的中文摘要占位：正文本就是中文的直接截断；英文正文给出固定中文占位，
    绝不回落到英文原文——否则前端看不出"摘要未翻译"的问题。
    长度对齐真实 prompt 的 150-220 字要求，头条位才能填满5行、画框高度才与线上一致。"""
    text = _TAG_RE.sub("", item["raw_text"] or "").strip()
    if _CJK_RE.search(text):
        return text[:220]
    return (
        f"〔示例摘要〕本文来自 {item['source_id']}，正文为英文，此处为本地联调用的中文占位文本。"
        "正式部署时，这段内容由 DeepSeek 在打分阶段生成：150-220 字的中文内容摘要，"
        "客观转述正文要点而非推荐语，英文正文一律用中文表达，"
        "同时保留模型名、公司名、产品名等专有名词的英文原文。"
        "头条位用它填满五行，因此长度必须写够，但也不会为凑字数复述标题或堆砌空话。"
    )


def _mock_depth_score(item, content_type):
    base = {"研究论文": 0.75, "深度分析": 0.8, "教程方法": 0.7, "观点评论": 0.5}.get(content_type, 0.15)
    # 正文越长略微加成，但上限受 content_type 主导——长通稿不会因此变成深度内容
    return round(min(1.0, base + min(len(item["raw_text"]), 2000) / 2000 * 0.15), 3)


def mock_score_items(items, categories, weights, source_authority_by_id):
    now = datetime.now(timezone.utc)
    scored = []
    for it in items:
        published = datetime.fromisoformat(it["published_at"])
        age_hours = max((now - published).total_seconds() / 3600, 0)
        novelty = max(0.0, 1.0 - age_hours / 48.0)

        authority = source_authority_by_id.get(it["source_id"], 0.5)
        text_len = len(it["raw_text"])
        practical_value = min(1.0, 0.3 + text_len / 2000)
        impact = min(1.0, (authority * 0.6) + (novelty * 0.4))

        weighted = (
            weights["source_authority"] * authority
            + weights["novelty"] * novelty
            + weights["impact"] * impact
            + weights["practical_value"] * practical_value
        )

        # 英文标题给占位译文演示版式；正式部署由 DeepSeek 在打分调用中一并生成真实翻译
        has_cjk = bool(_CJK_RE.search(it["title"]))
        title_zh = None if has_cjk else f"示例译文：{it['title'][:48]}"

        content_type = _mock_content_type(it)

        enriched = dict(it)
        enriched.update(
            {
                "category": _guess_category(it, categories),
                "content_type": content_type,
                "depth_score": _mock_depth_score(it, content_type),
                "title_zh": title_zh,
                "reason_zh": f"[mock] 来自 {it['source_id']}，发布于 {age_hours:.0f} 小时前",
                # 生产由 DeepSeek 生成真实中文摘要；这里只产出等长的中文占位文本，
                # 以便前端验证"摘要一定是中文"这条规则（英文原文不应再出现在摘要位）
                "summary_zh": _mock_summary_zh(it),
                "weighted_score": round(weighted, 4),
                "score_breakdown": {
                    "source_authority": round(authority, 3),
                    "novelty": round(novelty, 3),
                    "impact": round(impact, 3),
                    "practical_value": round(practical_value, 3),
                },
            }
        )
        scored.append(enriched)

    log.info("mock_score_items: %d items scored (heuristic, not real LLM)", len(scored))
    return scored, []
