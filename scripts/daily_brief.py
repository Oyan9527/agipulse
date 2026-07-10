"""今日深度推荐：24小时内挑"读完能获得可迁移认知"的内容——可解释性研究、
提出新方法的论文、工程师复盘真实系统的实践总结、有论证的深度剖析。

深度由 DeepSeek 在打分阶段判定（content_type + depth_score，见 llm_score.py），
不是用正文字数衡量：长篇通稿一样可以毫无深度，而一篇精炼的机制发现可以很短。

输入是全部已打分条目而非精选流：精选流门槛是"多源确认或高加权分"，而一篇优秀的
工程实践复盘往往是单源、加权分不突出，正是深度推荐最该收录的内容。深度推荐用
depth_score + content_type 自成一套更严的筛选，与精选流是两个独立视角。

宁缺毋滥：深度内容不足 top_n 时就少给几条，不用资讯快讯/产品发布凑数
（与 quality_gate 的"冷清日不硬凑"一致）；一条都没有时前端区块收起。
"""
from datetime import datetime, timedelta, timezone

from .util import get_logger

log = get_logger(__name__)


def build_daily_brief(scored_items, weights_config):
    cfg = weights_config["daily_brief"]
    top_n = cfg["top_n"]
    min_depth = cfg.get("min_depth_score", 0.0)
    excluded_types = set(cfg.get("exclude_content_types") or ())
    max_per_category = cfg.get("max_per_category")
    now = datetime.now(timezone.utc)
    window = timedelta(hours=24)

    recent = [
        it
        for it in scored_items
        if now - datetime.fromisoformat(it["published_at"]) <= window
    ]

    deep = [
        it
        for it in recent
        if it.get("content_type") not in excluded_types
        and (it.get("depth_score") or 0) >= min_depth
    ]
    # 按深度排序（而非加权分）——加权分偏向权威源与新鲜度，会把发布公告顶上来
    deep.sort(key=lambda x: (x["depth_score"], x["weighted_score"]), reverse=True)

    ranked = []
    per_category = {}
    for it in deep:
        if len(ranked) >= top_n:
            break
        cat = it.get("category")
        if max_per_category is not None and per_category.get(cat, 0) >= max_per_category:
            continue
        per_category[cat] = per_category.get(cat, 0) + 1
        ranked.append(it)

    log.info(
        "daily_brief: %d deep items selected (of %d scored in 24h, %d passed depth>=%.2f; excluded types: %s)",
        len(ranked), len(recent), len(deep), min_depth, "/".join(sorted(excluded_types)) or "none",
    )
    return {
        "date": now.date().isoformat(),
        "generated_at": now.isoformat(),
        "items": ranked,
    }
