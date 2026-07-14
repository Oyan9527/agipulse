"""话题追踪聚合的回归测试。

关键逻辑：大小写归并（"GPT"/"Gpt" 是同一话题）、按天对齐成曲线、升降趋势判定、
窗口截断与噪声过滤。这些都是纯聚合，无外部依赖。
"""
from scripts.topics import build_topics


def _arch(date, keywords):
    # keyword_counts 是扁平 {关键词: 次数} 字典（真实 archive.py 的产出 schema，
    # 见其 update_daily_archive 里的 dict(keyword_counts.most_common(200))）。
    # 曾经这里错写成 top_keywords 列表，测试和生产代码"一起错"，谁都没发现
    # build_topics 其实一直在读一个不存在的字段、话题追踪功能一直是空的。
    counts = {}
    for t, c in keywords:
        counts[t] = counts.get(t, 0) + c
    return {"date": date, "keyword_counts": counts}


def test_aggregates_series_aligned_to_dates():
    archives = [
        _arch("2026-07-08", [("OpenAI", 5)]),
        _arch("2026-07-09", [("OpenAI", 8)]),
        _arch("2026-07-10", [("OpenAI", 3)]),
    ]
    out = build_topics(archives)
    t = next(x for x in out["topics"] if x["term"] == "OpenAI")
    assert t["series"] == [5, 8, 3]
    assert t["total"] == 16
    assert out["dates"] == ["2026-07-08", "2026-07-09", "2026-07-10"]


def test_missing_day_becomes_zero():
    archives = [
        _arch("2026-07-08", [("Claude", 4)]),
        _arch("2026-07-09", []),
        _arch("2026-07-10", [("Claude", 6)]),
    ]
    t = next(x for x in build_topics(archives)["topics"] if x["term"] == "Claude")
    assert t["series"] == [4, 0, 6]


def test_case_variants_are_merged():
    archives = [
        _arch("2026-07-09", [("GPT", 30), ("Gpt", 6)]),
        _arch("2026-07-10", [("gpt", 4)]),
    ]
    terms = [t["term"] for t in build_topics(archives)["topics"]]
    assert terms.count("GPT") == 1 and "Gpt" not in terms and "gpt" not in terms
    gpt = next(t for t in build_topics(archives)["topics"] if t["term"] == "GPT")
    assert gpt["total"] == 40          # 30+6+4 合并
    assert gpt["term"] == "GPT"        # 显示用最高频拼写


def test_trend_up_down_flat():
    assert _series_trend([0, 0, 5, 8]) == "up"
    assert _series_trend([8, 8, 1, 0]) == "down"
    assert _series_trend([5, 5, 5, 5]) == "flat"


def _series_trend(series):
    archives = [_arch(f"2026-07-{8+i:02d}", [("X", v)]) for i, v in enumerate(series)]
    return next(t for t in build_topics(archives)["topics"] if t["term"] == "X")["trend"]


def test_noise_below_threshold_dropped():
    archives = [_arch("2026-07-10", [("Rare", 1), ("Hot", 20)])]
    terms = [t["term"] for t in build_topics(archives)["topics"]]
    assert "Hot" in terms and "Rare" not in terms   # total 1 < MIN_TOTAL_MENTIONS


def test_window_truncates_to_recent_days():
    archives = [_arch(f"2026-06-{d:02d}", [("X", 5)]) for d in range(1, 21)]
    out = build_topics(archives, window_days=14)
    assert out["window_days"] == 14
    assert len(out["dates"]) == 14
    assert out["dates"][0] == "2026-06-07"   # 最近 14 天


def test_top_n_limits_topic_count():
    archives = [_arch("2026-07-10", [(f"T{i}", 20 - i) for i in range(15)])]
    out = build_topics(archives, top_n=8)
    assert len(out["topics"]) == 8
    assert out["topics"][0]["term"] == "T0"


def test_empty_archives_no_crash():
    out = build_topics([])
    assert out["topics"] == [] and out["dates"] == []
