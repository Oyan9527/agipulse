"""给"信源不提供发布时间"的条目钉住一个稳定的首次发现时间。

背景：部分 RSS 源（如美团技术团队博客）压根不提供 <pubDate>/<updated> 字段，
normalize.py 只能在缺失时兜底成 now_utc()。若什么都不做，同一条内容（url 不变、
id 因此不变）每次被重新抓到，published_at 都会被重新盖成"当前时间"——这条内容
就永远不会滑出48h处理窗口/24h展示窗口，一直占着高分位置，把当天真正的新内容
挤下去（实测：一篇6月30日的旧文，跑了两周仍在每轮头条候选里，因为它的
published_at 永远等于"刚刚"）。

修复：按 id 把"第一次观测到这条内容"的时间戳持久化到 docs/data 下、随数据一起
提交（做法与 llm_cache.py 一致）。同一条目下一轮再被抓到时，直接复用这个钉住的
时间而不是重新盖今天，让它像正常内容一样按真实的"首次发现时间"自然老化、按时
滑出窗口。只淘汰仍在 48h 窗口内的 id——真正过期后不再追踪；若很久以后同一 url
又重新出现在源里，会被当作一次新的首次发现，这是有意为之的合理简化（我们没有
办法区分"源里一直没变过"和"真的又更新了"，给它一次新的可见窗口比永久拉黑更安全）。
"""
import json
from pathlib import Path

from .util import get_logger

log = get_logger(__name__)

CACHE_FILENAME = "first-seen-cache.json"


def load_first_seen(output_dir):
    path = Path(output_dir) / CACHE_FILENAME
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        log.warning("first-seen cache unreadable, starting fresh")
        return {}


def save_first_seen(output_dir, cache, retain_ids):
    """只保留仍在当前处理窗口内的id，其余（已自然过期的旧内容）随之清理。"""
    pruned = {k: v for k, v in cache.items() if k in retain_ids}
    path = Path(output_dir) / CACHE_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(pruned, f, ensure_ascii=False)
    tmp.replace(path)
    log.info("first_seen: saved %d entries (pruned from %d)", len(pruned), len(cache))


def pin_fallback_timestamps(items, cache):
    """就地修正：published_at 是兜底值(_published_at_is_fallback=True)的条目，
    复用缓存里已记录的首次发现时间；缓存里没有则记为此刻，并写回缓存供下轮复用。
    非兜底(信源本身给了真实日期)的条目原样不动，也不进缓存——它们没有这个问题。
    """
    pinned = 0
    for it in items:
        if not it.pop("_published_at_is_fallback", False):
            continue
        iid = it["id"]
        if iid in cache:
            it["published_at"] = cache[iid]
        else:
            cache[iid] = it["published_at"]  # 已是 to_iso(now_utc()) 格式，直接复用
        pinned += 1
    if pinned:
        log.info("first_seen: %d items lacked a real publish date, pinned to first-seen time", pinned)
