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
    "min_scored_items": 1,            # 全部动态里"有打分"的条目数低于此值 -> 打分层挂了
}


def evaluate_health(statuses, all_items, cfg):
    """纯函数：给定信源状态与全部条目，返回 (ok, problems, metrics)。

    problems 是人类可读的问题描述列表；ok 为空即 True。metrics 供日志展示。
    """
    total_sources = len(statuses)
    active = sum(1 for s in statuses if s.get("last_error") is None)
    active_ratio = round(active / total_sources, 3) if total_sources else 0.0

    # "有打分"而非"精选"：精选受质量门槛影响，冷清日合法为空；
    # 而只要 DeepSeek 正常工作，all 流里就一定有 weighted_score 非空的条目。
    # DeepSeek 全挂时，all 流里全是未打分条目（weighted_score=None）。
    scored = sum(1 for it in all_items if it.get("weighted_score") is not None)

    metrics = {
        "sources_total": total_sources,
        "sources_active": active,
        "active_ratio": active_ratio,
        "items_total": len(all_items),
        "items_scored": scored,
    }

    problems = []
    if total_sources == 0:
        problems.append("信源状态为空：抓取阶段可能整体失败")
    elif active_ratio < cfg["min_active_source_ratio"]:
        problems.append(
            f"抓取成功率过低：{active}/{total_sources} = {active_ratio:.0%}"
            f"（阈值 {cfg['min_active_source_ratio']:.0%}），疑似大面积源失效或网络异常"
        )

    if scored < cfg["min_scored_items"]:
        problems.append(
            f"打分条目过少：{scored} 条（阈值 {cfg['min_scored_items']}），"
            f"疑似 DeepSeek API 失效（key 欠费 / 限流 / 服务中断）"
        )

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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="docs/data")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    statuses = _load_json(data_dir / "source-status.json", [])
    all_items = _load_json(data_dir / "latest-24h-all.json", [])
    cfg = load_thresholds()

    ok, problems, metrics = evaluate_health(statuses, all_items, cfg)

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
