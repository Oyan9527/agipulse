"""质量门控：多源确认或高分才能进入精选流；冷清日不硬凑，直接输出空数组。

分类配额（config/weights.yaml 的 category_quotas）：
- max：该分类精选上限。超出时按加权分从高到低保留（如 论文研究 最多 10 条，避免 arXiv 刷屏）。
- min：该分类保底数量。过门槛数量不足时，从该分类未过门槛的已打分条目里按分数补足
  （如 开源项目 至少 5 条）。补足条目同样标记 curated=True，但 gate_backfill=True 以便追溯。
"""
from .util import get_logger

log = get_logger(__name__)


def apply_gate(items, weights_config):
    min_score = weights_config["quality_gate"]["min_weighted_score"]
    min_sources = weights_config["quality_gate"]["min_multi_source_count"]
    quotas = weights_config.get("category_quotas") or {}

    passed = []
    rejected_scored = []  # 已打分但未过门槛的，作为 min 配额的补足池
    for it in items:
        score = it.get("weighted_score")
        sources = it.get("multi_source_count", 1)
        if score is None:
            continue  # 未打分条目不参与精选
        if sources >= min_sources or score >= min_score:
            passed.append(it)
        else:
            rejected_scored.append(it)

    # max 配额：超限分类按分数截断
    curated = []
    per_category = {}
    passed_sorted = sorted(passed, key=lambda x: x["weighted_score"], reverse=True)
    for it in passed_sorted:
        cat = it.get("category")
        cap = quotas.get(cat, {}).get("max")
        count = per_category.get(cat, 0)
        if cap is not None and count >= cap:
            continue
        per_category[cat] = count + 1
        curated.append(dict(it, curated=True))

    # min 配额：不足的分类从补足池按分数补齐
    for cat, rule in quotas.items():
        floor = rule.get("min")
        if not floor:
            continue
        have = per_category.get(cat, 0)
        if have >= floor:
            continue
        pool = sorted(
            (it for it in rejected_scored if it.get("category") == cat),
            key=lambda x: x["weighted_score"],
            reverse=True,
        )
        need = floor - have
        for it in pool[:need]:
            curated.append(dict(it, curated=True, gate_backfill=True))
            per_category[cat] = per_category.get(cat, 0) + 1
        if per_category.get(cat, 0) < floor:
            log.info("quota: category %s below floor (%d/%d), source data too quiet",
                     cat, per_category.get(cat, 0), floor)

    log.info(
        "quality_gate: %d curated (%d passed gate, %d backfilled) out of %d scored",
        len(curated), len(passed_sorted), sum(1 for c in curated if c.get("gate_backfill")), len(items),
    )
    return curated
