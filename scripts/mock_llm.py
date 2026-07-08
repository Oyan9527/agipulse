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
        title_zh = None if has_cjk else f"〔示例译文〕{it['title'][:34]}（部署后由 DeepSeek 翻译）"

        enriched = dict(it)
        enriched.update(
            {
                "category": _guess_category(it, categories),
                "title_zh": title_zh,
                "reason_zh": f"[mock] 来自 {it['source_id']}，发布于 {age_hours:.0f} 小时前",
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
