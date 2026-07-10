"""健康检查的回归测试。

这是"静默失效"的最后一道网：流水线成功退出、数据照常提交，但内容悄悄变空。
两个失败模式各自要能被抓到，同时冷清日（源正常、就是没什么可打分的）不能误报。
"""
from scripts.health_check import evaluate_health

CFG = {"min_active_source_ratio": 0.5, "min_scored_items": 1}


def _statuses(active, dead):
    return (
        [{"source_id": f"ok{i}", "last_error": None} for i in range(active)] +
        [{"source_id": f"bad{i}", "last_error": "timeout"} for i in range(dead)]
    )


def _items(scored, unscored):
    return (
        [{"id": f"s{i}", "weighted_score": 0.7} for i in range(scored)] +
        [{"id": f"u{i}", "weighted_score": None} for i in range(unscored)]
    )


def test_healthy_pipeline_passes():
    ok, problems, _ = evaluate_health(_statuses(9, 1), _items(20, 5), CFG)
    assert ok and problems == []


def test_mass_source_failure_flagged():
    # 只有 30% 源成功 -> 大面积抓取失败
    ok, problems, _ = evaluate_health(_statuses(3, 7), _items(5, 0), CFG)
    assert not ok
    assert any("抓取成功率" in p for p in problems)


def test_scoring_outage_flagged():
    # 源都正常，但没有一条被打分 -> DeepSeek 挂了
    ok, problems, _ = evaluate_health(_statuses(10, 0), _items(0, 40), CFG)
    assert not ok
    assert any("打分条目" in p for p in problems)


def test_empty_source_status_flagged():
    ok, problems, _ = evaluate_health([], [], CFG)
    assert not ok
    assert any("信源状态为空" in p for p in problems)


def test_both_failures_reported_together():
    ok, problems, _ = evaluate_health(_statuses(1, 9), _items(0, 3), CFG)
    assert not ok
    assert len(problems) == 2


def test_quiet_day_is_not_an_outage():
    # 源全正常、也确实打了分，只是数量少——这是合法的冷清日，不该报警
    ok, problems, _ = evaluate_health(_statuses(10, 0), _items(2, 1), CFG)
    assert ok and problems == []


def test_metrics_are_reported():
    _, _, metrics = evaluate_health(_statuses(8, 2), _items(15, 5), CFG)
    assert metrics["active_ratio"] == 0.8
    assert metrics["items_scored"] == 15
    assert metrics["sources_total"] == 10


def test_ratio_exactly_at_threshold_passes():
    # 恰好 50% 不算失败（阈值是"低于"才报警）
    ok, problems, _ = evaluate_health(_statuses(5, 5), _items(3, 0), CFG)
    assert ok and problems == []
