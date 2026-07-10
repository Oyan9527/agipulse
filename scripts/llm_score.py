"""第二级：DeepSeek 四维度打分 + 分类 + 一句话中文推荐理由。
单批失败 -> 该批条目标记为未打分（score=None），仅进入"全部"流，不进入精选/日报。
"""
from .deepseek_client import call_json, batched
from .util import get_logger

log = get_logger(__name__)

SYSTEM_PROMPT_TMPL = """你是一个 AI 行业信息评分助手。可选分类只能从以下列表中选择：{categories}。
对每条输入（id/title/snippet/source_id），从四个维度打分（0.0-1.0 浮点数）：
- source_authority: 信息来源的权威程度
- novelty: 内容的新颖度/首发程度
- impact: 对 AI 行业的影响力大小
- practical_value: 对读者的实用价值

同时给出：
- category：必须是给定列表之一
- reason_zh：中文推荐理由/内容摘要，不超过80字
- title_zh：标题的中文翻译（准确、简洁、保留专有名词原文如模型名/公司名）；若标题本身已是中文则返回 null

返回 JSON: {{"results": [{{"id": "...", "source_authority": 0.0, "novelty": 0.0, "impact": 0.0, "practical_value": 0.0, "category": "...", "reason_zh": "...", "title_zh": "..."}}]}}
必须覆盖所有输入的 id。"""


def score_items(items, categories, weights, batch_size=10):
    category_ids = [c["id"] for c in categories]
    system_prompt = SYSTEM_PROMPT_TMPL.format(categories="、".join(category_ids))

    scored = []
    unscored = []

    for batch in batched(items, batch_size):
        payload = [
            {
                "id": it["id"],
                "title": it["title"],
                "snippet": it["raw_text"][:300],
                "source_id": it["source_id"],
            }
            for it in batch
        ]
        result = call_json(system_prompt, {"items": payload}, max_tokens=3000)

        if result is None or "results" not in result:
            log.warning("scoring batch failed, %d items left unscored", len(batch))
            unscored.extend(batch)
            continue

        by_id = {r["id"]: r for r in result["results"]}
        for it in batch:
            r = by_id.get(it["id"])
            if not r or r.get("category") not in category_ids:
                unscored.append(it)
                continue
            weighted = (
                weights["source_authority"] * float(r.get("source_authority", 0))
                + weights["novelty"] * float(r.get("novelty", 0))
                + weights["impact"] * float(r.get("impact", 0))
                + weights["practical_value"] * float(r.get("practical_value", 0))
            )
            enriched = dict(it)
            enriched.update(
                {
                    "category": r["category"],
                    "reason_zh": r.get("reason_zh", ""),
                    "title_zh": r.get("title_zh") or None,
                    "weighted_score": round(weighted, 4),
                    "score_breakdown": {
                        "source_authority": r.get("source_authority"),
                        "novelty": r.get("novelty"),
                        "impact": r.get("impact"),
                        "practical_value": r.get("practical_value"),
                    },
                }
            )
            scored.append(enriched)

    log.info("scoring: %d scored, %d unscored (fell through)", len(scored), len(unscored))
    return scored, unscored
