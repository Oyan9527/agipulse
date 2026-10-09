"""定时流水线 workflow 的结构守卫（.github/workflows/pipeline.yml）。

这个文件改错了不会有任何测试变红——它只在每晚线上跑，错了也只是"悄悄多烧一轮
DeepSeek"或者"该补跑的没补"。两个真实踩过的坑都固化在这里：

1. 补跑的判据看的是步骤名字符串，改步骤名会让它静默失效；
2. 回看窗口要能覆盖两条 cron 的实际间隔——原先按"UTC 当天"筛，GitHub 延迟
   2.5~4 小时后，21:00 那条落到次日 01:0x，把几小时前的主运行漏在了昨天，
   每晚白跑一轮完整流水线。
"""
import io
import re

import yaml

WF_PATH = ".github/workflows/pipeline.yml"
RAW = io.open(WF_PATH, encoding="utf-8").read()
WF = yaml.safe_load(io.open(WF_PATH, encoding="utf-8"))
# PyYAML 把 YAML 1.1 的 on: 解析成布尔 True
TRIGGERS = WF.get("on") or WF.get(True)

DECIDE = WF["jobs"]["decide"]["steps"][0]["run"]
UPDATE_STEPS = [s["name"] for s in WF["jobs"]["update-data"]["steps"] if "name" in s]


def _cron_hours():
    return sorted(int(c["cron"].split()[1]) for c in TRIGGERS["schedule"])


def _lookback_hours():
    m = re.search(r'date -u -d "(\d+) hours ago"', DECIDE)
    assert m, "decide 里找不到回看窗口（date -u -d \"N hours ago\"）"
    return int(m.group(1))


def test_two_crons_main_and_fallback():
    hours = _cron_hours()
    assert len(hours) == 2, "应当正好两条 cron（主运行 + 兜底补跑），实际 %s" % hours


def test_lookback_window_covers_the_gap_between_crons():
    """窗口必须大于两条 cron 的间隔，否则补跑那轮看不见主运行。

    线上实测 GitHub 定时触发有 2.5~4 小时延迟，两条 cron 的实际间隔会在名义
    间隔附近浮动，所以要留出余量，不能卡着名义值。
    """
    a, b = _cron_hours()
    gap = b - a
    window = _lookback_hours()
    assert window > gap + 2, (
        "回看窗口 %dh 不够覆盖两条 cron 的间隔 %dh（还要留延迟余量）" % (window, gap))


def test_lookback_window_does_not_reach_yesterdays_run():
    """窗口也不能太长，碰到 24 小时前的上一轮——那会把昨天的成功当成今天的。"""
    window = _lookback_hours()
    assert window <= 18, "回看窗口 %dh 太长，可能把上一天的运行算进来" % window


def test_decide_checks_data_steps_that_actually_exist():
    """decide 按步骤名匹配，名字对不上就静默失效（永远判成"没跑出数据"）。"""
    referenced = re.findall(r'\.name == "([^"]+)"', DECIDE)
    data_steps = [n for n in referenced if n != "update-data"]
    assert data_steps, "decide 里没有引用任何步骤名？判据已经空了"
    missing = [n for n in data_steps if n not in UPDATE_STEPS]
    assert not missing, (
        "decide 引用的步骤在 update-data 里不存在: %s（现有步骤: %s）" % (missing, UPDATE_STEPS))


def test_decide_requires_both_data_steps():
    """两步都成功才算当天的活干完了：只跑出数据没提交上去，等于白跑。"""
    assert re.search(r'-ge 2', DECIDE), "decide 没有要求两个数据步骤都成功"


def test_health_check_runs_after_commit_and_does_not_gate_data():
    """体检必须排在提交之后：它只是报警，不能挡在数据落库前面。"""
    assert "Health check" in UPDATE_STEPS
    assert UPDATE_STEPS.index("Health check") > UPDATE_STEPS.index("Commit data if changed")


def test_workflow_can_read_its_own_runs():
    """decide 要查 Actions 运行记录，缺了这个权限整个判据会报错。"""
    assert WF["permissions"].get("actions") == "read"
