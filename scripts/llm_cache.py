"""LLM 打分结果缓存：降低 DeepSeek 消耗的关键一环。

流水线每小时跑一次，处理窗口是 48 小时——同一条目在被淘汰出窗口前，
会被连续抓到最多 48 次。如果每次都重新调用 prefilter+score，
相当于给同一条内容打分 48 遍，是最大的隐性浪费。

这个缓存把每条内容的判定结果（prefilter 拒绝 / 打分完成）按 id 持久化，
随 site/data 一起提交进仓库、跨 GitHub Actions 的每次全新 checkout 生效。
下一轮遇到同一 id：拒绝的直接跳过、打分过的直接复用，不再调用 DeepSeek，
只有真正首次出现的新内容才会真正花钱调用两级判定。

缓存文件本身不含敏感信息（分数/分类/中文理由，latest-24h-all.json 里本来就有），
放在 output_dir 下随数据一起提交，无需改动 GitHub Actions workflow。
"""
import json
from pathlib import Path

from .util import get_logger

log = get_logger(__name__)

CACHE_FILENAME = "llm-cache.json"
SCORE_FIELDS = [
    "category", "content_type", "depth_score",
    "reason_zh", "summary_zh", "title_zh", "weighted_score", "score_breakdown",
]
# 打分schema新增字段时，旧缓存条目缺这些键。缺任意一个就当没缓存过、重新送去打分，
# 让缓存自然迁移到新schema（否则旧条目会带着 depth_score=None / summary_zh=None 混进来）。
# 新增会影响展示的打分字段时，把它加进这个元组。
_SCHEMA_REQUIRED_FIELDS = ("depth_score", "summary_zh")


def load_cache(output_dir):
    path = Path(output_dir) / CACHE_FILENAME
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        log.warning("llm cache unreadable, starting fresh")
        return {}


def save_cache(output_dir, cache, retain_ids):
    """只保留仍在当前48h处理窗口内的id，其余（已淘汰的旧内容）随之清理，缓存不会无限增长。"""
    pruned = {k: v for k, v in cache.items() if k in retain_ids}
    path = Path(output_dir) / CACHE_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(pruned, f, ensure_ascii=False)
    tmp.replace(path)
    log.info("llm_cache: saved %d entries (pruned from %d)", len(pruned), len(cache))


def split_by_cache(items, cache):
    """返回 (cached_scored, cached_rejected_ids, uncached)：
    - cached_scored：命中缓存且此前打分成功的条目，字段已合并回原 item，无需再调用LLM
    - cached_rejected_ids：命中缓存且此前被prefilter拒绝的id集合，直接排除
    - uncached：从未见过的新条目，需要走真正的 prefilter+score
    """
    cached_scored, cached_rejected_ids, uncached = [], set(), []
    for it in items:
        hit = cache.get(it["id"])
        if hit is None:
            uncached.append(it)
        elif hit.get("status") == "rejected":
            cached_rejected_ids.add(it["id"])
        elif hit.get("status") == "scored" and all(f in hit for f in _SCHEMA_REQUIRED_FIELDS):
            merged = dict(it)
            merged.update({k: hit.get(k) for k in SCORE_FIELDS})
            cached_scored.append(merged)
        else:
            uncached.append(it)  # 缓存条目格式异常，当新内容重新处理，宁可多算不可漏算
    return cached_scored, cached_rejected_ids, uncached


def record_rejected(cache, item_ids):
    for iid in item_ids:
        cache[iid] = {"status": "rejected"}


def record_scored(cache, scored_items):
    for it in scored_items:
        cache[it["id"]] = {"status": "scored", **{k: it.get(k) for k in SCORE_FIELDS}}
