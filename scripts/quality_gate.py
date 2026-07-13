"""质量门控：多源确认或高分才能进入精选流。

分类配额（config/weights.yaml 的 category_quotas）：
- max：该分类精选上限。超出时按加权分从高到低保留（如 论文研究 最多 10 条，避免 arXiv 刷屏）。
- min：该分类保底数量。过门槛数量不足时，从该分类未过门槛的已打分条目里按分数补足
  （如 开源项目 至少 5 条）。补足条目同样标记 curated=True，但 gate_backfill=True 以便追溯。

全局保底（quality_gate.min_curated_items）：
- DeepSeek 冷清期打分普遍偏低时，达标条目可能只有个位数，首页近乎空白。精选总数不足
  该值时，从"已打分但未过门槛"的次优内容里按分数从高到低跨分类补齐（仍尊重各分类 max），
  同样标记 gate_backfill。忙碌日达标内容超过此值，保底为空操作。设为 0 即关闭该行为。
"""
from .util import get_logger

log = get_logger(__name__)


def apply_gate(items, weights_config):
    gate_cfg = weights_config["quality_gate"]
    min_score = gate_cfg["min_weighted_score"]
    min_sources = gate_cfg["min_multi_source_count"]
    min_curated = gate_cfg.get("min_curated_items", 0)
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

    # 全局保底：精选总数不足 min_curated 时，从次优池按分数跨分类补齐（仍尊重各分类 max）。
    if min_curated and len(curated) < min_curated:
        have_ids = {c.get("id") for c in curated}
        pool = sorted(
            (it for it in rejected_scored if it.get("id") not in have_ids),
            key=lambda x: x["weighted_score"],
            reverse=True,
        )
        for it in pool:
            if len(curated) >= min_curated:
                break
            cat = it.get("category")
            cap = quotas.get(cat, {}).get("max")
            if cap is not None and per_category.get(cat, 0) >= cap:
                continue
            curated.append(dict(it, curated=True, gate_backfill=True))
            per_category[cat] = per_category.get(cat, 0) + 1
        if len(curated) < min_curated:
            log.info("quality_gate: below global floor (%d/%d), scored pool exhausted",
                     len(curated), min_curated)

    log.info(
        "quality_gate: %d curated (%d passed gate, %d backfilled) out of %d scored",
        len(curated), len(passed_sorted), sum(1 for c in curated if c.get("gate_backfill")), len(items),
    )
    return curated
