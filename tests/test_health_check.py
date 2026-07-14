"""健康检查的回归测试。

这是"静默失效"的最后一道网：流水线成功退出、数据照常提交，但内容悄悄变空。
两个失败模式各自要能被抓到，同时冷清日（源正常、就是没什么可打分的）不能误报。
"""
from scripts.health_check import evaluate_health

# 用真实读取的 key（min_scored_items 是已经删除的旧 key，配了也不会被读到，
# 之前这里一直配的是它——测试其实从没真正走过 min_scored_ratio 那条路径，
# 只是巧合地跟 DEFAULTS 里的 0.5 一样通过了）。
CFG = {"min_active_source_ratio": 0.5, "min_scored_ratio": 0.5}


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
    # items 总数要 >= min_scored_sample_size(10) 打分比例检查才会生效
    ok, problems, _ = evaluate_health(_statuses(1, 9), _items(0, 15), CFG)
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


# --- 按 source type 分组：份额不高但绝对数量不小的类型（Reddit 场景）---

def _typed_statuses(type_name, active, dead, other_active=0):
    entries = [{"source_id": f"{type_name}{i}", "last_error": None} for i in range(active)]
    entries += [{"source_id": f"{type_name}dead{i}", "last_error": "429"} for i in range(dead)]
    entries += [{"source_id": f"other{i}", "last_error": None} for i in range(other_active)]
    return entries


def test_type_outage_detected_by_absolute_count_even_with_low_share():
    # reddit 型：21个源全灭，但只占总数(21+279=300)的7%，远低于 min_type_share(20%)——
    # 绝对数量(21 >= min_type_absolute_count=10)这条路径应该单独把它抓出来
    statuses = _typed_statuses("reddit", active=0, dead=21, other_active=279)
    source_types = {s["source_id"]: ("reddit" if s["source_id"].startswith("reddit") else "rss") for s in statuses}
    ok, problems, metrics = evaluate_health(statuses, _items(50, 0), CFG, source_types)
    assert not ok
    assert any("reddit" in p and "大面积失效" in p for p in problems)
    assert metrics["type_stats"]["reddit"]["share"] < 0.2   # 确认份额确实低于份额阈值


def test_small_share_and_small_count_type_not_flagged():
    # 真正的小类型（比如只有5个源）两条路径都不该触发，避免对个位数信源的正常波动报警
    statuses = _typed_statuses("tiny", active=2, dead=3, other_active=100)
    source_types = {s["source_id"]: ("tiny" if s["source_id"].startswith("tiny") else "rss") for s in statuses}
    ok, problems, _ = evaluate_health(statuses, _items(50, 0), CFG, source_types)
    assert ok and problems == []


# --- 打分比例样本量下限：冷清期样本太少不该被判定成 DeepSeek 全挂 ---

def test_scored_ratio_ignored_below_sample_size_floor():
    # 只有2条进入打分池，2条都因为偶发瞬时超时没打上分——样本太小，不该报警
    ok, problems, _ = evaluate_health(_statuses(10, 0), _items(0, 2), CFG)
    assert ok and problems == []


def test_scored_ratio_still_enforced_once_sample_size_reached():
    # 样本量刚好达到下限(10)，比例检查应该照常生效
    ok, problems, _ = evaluate_health(_statuses(10, 0), _items(0, 10), CFG)
    assert not ok
    assert any("打分条目" in p for p in problems)
