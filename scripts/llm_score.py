"""第二级：DeepSeek 四维度打分 + 分类 + 一句话中文推荐理由。
单批失败 -> 该批条目标记为未打分（score=None），仅进入"全部"流，不进入精选/日报。
"""
from .deepseek_client import call_json, batched
from .util import get_logger

log = get_logger(__name__)

CONTENT_TYPES = [
    "深度分析", "研究论文", "教程方法", "观点评论", "资讯快讯", "产品发布", "营销推广",
]

SYSTEM_PROMPT_TMPL = """你是一个 AI 行业信息评分助手。可选分类只能从以下列表中选择：{categories}。
对每条输入（id/title/snippet/source_id），从四个维度打分（0.0-1.0 浮点数）：
- source_authority: 信息来源的权威程度
- novelty: 内容的新颖度/首发程度
- impact: 对 AI 行业的影响力大小
- practical_value: 对读者的实用价值

同时给出：
- category：必须是给定列表之一
- content_type：必须是以下之一：{content_types}
- depth_score（0.0-1.0 浮点数）：内容的思想深度与启发性。
  判断依据是"读完能否获得可迁移的认知"，而不是篇幅长短。
  高分(0.7-1.0)：揭示模型内部机制的可解释性研究；提出新方法/新架构并给出实验证据的论文；
    工程师复盘真实系统的设计取舍与踩坑（如 agent loop / context engineering 的实践总结）；
    有论证、有反直觉洞察的深度技术剖析或长篇评论。
  低分(0.0-0.3)：模型/产品发布公告与更新日志；融资、人事、财报、榜单、政策快讯；
    营销通稿与推广软文；单纯转述他人消息的二手资讯。
    篇幅很长但只是罗列事实或堆砌通稿辞藻的，同样给低分。
- reason_zh：中文推荐理由，不超过80字，说明这条为什么值得读
- summary_zh：中文内容摘要，150-220字，客观转述正文要点（不是推荐语）。
  头条位要用它填满5行，字数不足会留白，务必写够；但也不要为凑字数复述标题或空话。
  正文是英文时必须用中文表达，不要照抄英文原文；保留模型名/公司名/产品名等专有名词的英文原文。
  正文本身已是中文时，据其概括即可。
- title_zh：标题的中文翻译（准确、简洁、保留专有名词原文如模型名/公司名）；若标题本身已是中文则返回 null

返回 JSON: {{"results": [{{"id": "...", "source_authority": 0.0, "novelty": 0.0, "impact": 0.0, "practical_value": 0.0, "category": "...", "content_type": "...", "depth_score": 0.0, "reason_zh": "...", "summary_zh": "...", "title_zh": "..."}}]}}
必须覆盖所有输入的 id。"""


def _clamp01(value, default=0.0):
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return default


def score_items(items, categories, weights, batch_size=10):
    category_ids = [c["id"] for c in categories]
    system_prompt = SYSTEM_PROMPT_TMPL.format(
        categories="、".join(category_ids),
        content_types="、".join(CONTENT_TYPES),
    )

    scored = []
    unscored = []

    for batch in batched(items, batch_size):
        payload = [
            {
                "id": it["id"],
                "title": it["title"],
                # 400字符：要够模型写出120-200字的 summary_zh，300字符对英文正文偏短
                "snippet": it["raw_text"][:400],
                "source_id": it["source_id"],
            }
            for it in batch
        ]
        result = call_json(system_prompt, {"items": payload}, max_tokens=4500)

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
            content_type = r.get("content_type")
            if content_type not in CONTENT_TYPES:
                content_type = None  # 模型给了枚举外的值，宁可留空也不误判成深度内容

            enriched = dict(it)
            enriched.update(
                {
                    "category": r["category"],
                    "content_type": content_type,
                    "depth_score": round(_clamp01(r.get("depth_score")), 4),
                    "reason_zh": r.get("reason_zh", ""),
                    "summary_zh": r.get("summary_zh") or None,
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
