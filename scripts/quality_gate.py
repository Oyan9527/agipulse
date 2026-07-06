"""质量门控：多源确认或高分才能进入精选流；冷清日不硬凑，直接输出空数组。"""
from .util import get_logger

log = get_logger(__name__)


def apply_gate(items, weights_config):
    min_score = weights_config["quality_gate"]["min_weighted_score"]
    min_sources = weights_config["quality_gate"]["min_multi_source_count"]

    curated = []
    for it in items:
        score = it.get("weighted_score")
        sources = it.get("multi_source_count", 1)
        if score is None:
            continue  # 未打分条目不进入精选
        if sources >= min_sources or score >= min_score:
            curated.append(dict(it, curated=True))

    log.info("quality_gate: %d curated out of %d scored items", len(curated), len(items))
    return curated
