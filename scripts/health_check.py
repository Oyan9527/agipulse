"""流水线健康检查：检测"静默失效"——流水线成功退出、数据照常提交，但内容悄悄变空。

两类最危险的静默失效：
1. 大批源同时挂掉（网络异常 / IP 被封 / 多个源同时改版）——抓取成功率骤降。
2. DeepSeek key 欠费或 API 挂掉——打分全线失败，但流水线不会崩，只是所有条目都没打分。

这个检查读已经写出的数据文件（source-status.json / latest-24h-all.json）判断，
不参与抓取流程。它作为流水线之后的独立一步运行：数据永远先落盘、先提交，
检查不通过只让 GitHub Actions 的 job 标红并给仓库 owner 发失败邮件，不会丢数据。

用法：python -m scripts.health_check --data-dir docs/data
退出码 0 = 健康，1 = 有问题（触发 Actions 失败告警）。
"""
import argparse
import json
import sys
from pathlib import Path

from .util import load_yaml, get_logger

log = get_logger(__name__)

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

DEFAULTS = {
    "min_active_source_ratio": 0.5,   # 抓取成功的源占比低于此值 -> 大面积抓取失败
    # 原先用绝对数 min_scored_items=1：200 条里打对 1 条就能通过，对"DeepSeek 大面积
    # 限流/key 欠费导致 99% 批次失败"毫无区分度。改成比例——正常情况下 DeepSeek 只要
    # 在工作，all 流里绝大多数条目都会被打分（个别批次偶发失败不影响整体），
    # 跌破 0.5 说明多数条目根本没打上分，与 min_active_source_ratio 取相同量级，
    # 两者含义类比："这一层大部分单元是否在正常工作"。
    "min_scored_ratio": 0.5,
    # 单一全局 active_ratio 会被"大类型稀释"：rss 约占源总数一半、github_releases
    # 约占三分之一，若其中整类源同时失效（parser 改版/上游站点改版），全局占比仍能
    # 维持在 min_active_source_ratio 之上，看不出这一整类源已经全灭。
    # 因此额外按 source type 分组：只要某类型占全部源比例达到 min_type_share，
    # 就单独检查该类型内部的活跃占比是否跌破 min_type_active_ratio。
    "min_type_share": 0.2,
    "min_type_active_ratio": 0.5,
}


def evaluate_health(statuses, all_items, cfg, source_types=None):
    """纯函数：给定信源状态与全部条目，返回 (ok, problems, metrics)。

    problems 是人类可读的问题描述列表；ok 为空即 True。metrics 供日志展示。
    source_types：可选的 {source_id: type} 映射，用于按类型细分活跃率检查；
    不传或查不到类型的 source_id 会被跳过（不计入任何类型分组，也不会误报）。
    """
    source_types = source_types or {}

    total_sources = len(statuses)
    active = sum(1 for s in statuses if s.get("last_error") is None)
    active_ratio = round(active / total_sources, 3) if total_sources else 0.0

    # "有打分"而非"精选"：精选受质量门槛影响，冷清日合法为空；
    # 而只要 DeepSeek 正常工作，all 流里就一定有 weighted_score 非空的条目。
    # DeepSeek 全挂时，all 流里全是未打分条目（weighted_score=None）。
    scored = sum(1 for it in all_items if it.get("weighted_score") is not None)
    total_items = len(all_items)
    # 没有条目可打分（真正的空窗）不算打分层故障，交给别处的抓取层检查判断；
    # 否则 0/0 会被误判成"全挂"。
    scored_ratio = round(scored / total_items, 3) if total_items else 1.0

    problems = []
    if total_sources == 0:
        problems.append("信源状态为空：抓取阶段可能整体失败")
    elif active_ratio < cfg.get("min_active_source_ratio", DEFAULTS["min_active_source_ratio"]):
        threshold = cfg.get("min_active_source_ratio", DEFAULTS["min_active_source_ratio"])
        problems.append(
            f"抓取成功率过低：{active}/{total_sources} = {active_ratio:.0%}"
            f"（阈值 {threshold:.0%}），疑似大面积源失效或网络异常"
        )

    # 按 source type 分组，检测"整类型静默失效"：全局占比达标、但占比重的某一类型全灭。
    min_type_share = cfg.get("min_type_share", DEFAULTS["min_type_share"])
    min_type_active_ratio = cfg.get("min_type_active_ratio", DEFAULTS["min_type_active_ratio"])
    type_stats = {}
    if total_sources:
        for s in statuses:
            t = source_types.get(s.get("source_id"))
            if not t:
                continue  # 查不到类型（如测试里的虚构 source_id）不归类，避免误报
            entry = type_stats.setdefault(t, {"total": 0, "active": 0})
            entry["total"] += 1
            if s.get("last_error") is None:
                entry["active"] += 1

    for t, entry in type_stats.items():
        t_total, t_active = entry["total"], entry["active"]
        share = round(t_total / total_sources, 3) if total_sources else 0.0
        t_ratio = round(t_active / t_total, 3) if t_total else 0.0
        entry["share"] = share
        entry["ratio"] = t_ratio
        if share >= min_type_share and t_ratio < min_type_active_ratio:
            problems.append(
                f"源类型「{t}」大面积失效：{t_active}/{t_total} = {t_ratio:.0%}"
                f"（占全部源 {share:.0%} ≥ {min_type_share:.0%}，阈值 {min_type_active_ratio:.0%}），"
                f"疑似该类型整体挂掉（parser 回归/上游改版）"
            )

    min_scored_ratio = cfg.get("min_scored_ratio", DEFAULTS["min_scored_ratio"])
    if scored_ratio < min_scored_ratio:
        problems.append(
            f"打分条目占比过低：{scored}/{total_items} = {scored_ratio:.0%}"
            f"（阈值 {min_scored_ratio:.0%}），疑似 DeepSeek API 失效（key 欠费 / 限流 / 服务中断）"
        )

    metrics = {
        "sources_total": total_sources,
        "sources_active": active,
        "active_ratio": active_ratio,
        "items_total": total_items,
        "items_scored": scored,
        "items_scored_ratio": scored_ratio,
        "type_stats": type_stats,
    }

    return (not problems), problems, metrics


def _load_json(path, fallback):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return fallback


def load_thresholds():
    cfg = dict(DEFAULTS)
    try:
        weights = load_yaml(CONFIG_DIR / "weights.yaml")
        cfg.update(weights.get("health_check") or {})
    except (FileNotFoundError, KeyError):
        pass
    return cfg


def load_source_types():
    """从 sources.yaml 建立 source_id -> type 映射，供按类型分组的活跃率检查使用。

    source-status.json 本身不带 type 字段（见 scripts/source_health.py），
    这里回读注册表做一次关联，不改动 source-status.json 的既有输出格式。
    """
    try:
        sources_cfg = load_yaml(CONFIG_DIR / "sources.yaml").get("sources") or []
    except (FileNotFoundError, KeyError):
        return {}
    return {s["id"]: s.get("type") for s in sources_cfg if s.get("id")}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="docs/data")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    statuses = _load_json(data_dir / "source-status.json", [])
    all_items = _load_json(data_dir / "latest-24h-all.json", [])
    cfg = load_thresholds()
    source_types = load_source_types()

    ok, problems, metrics = evaluate_health(statuses, all_items, cfg, source_types)

    log.info(
        "health: %d/%d 源活跃 (%.0f%%), %d/%d 条已打分",
        metrics["sources_active"], metrics["sources_total"], metrics["active_ratio"] * 100,
        metrics["items_scored"], metrics["items_total"],
    )
    if ok:
        log.info("health check passed")
        sys.exit(0)

    for p in problems:
        log.error("health check FAILED: %s", p)
    sys.exit(1)


if __name__ == "__main__":
    main()
