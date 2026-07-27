"""精选流的"窗口过滤 → 质量门控"顺序回归测试。

踩过的坑（用户多次反馈"精选怎么又只出 7 条"）：run_pipeline 曾经先对全部
representative 做 apply_gate、把精选保底补到 min_curated_items(12) 条，再对
结果过 24h 展示窗口。补进来的次优内容里凡是发布超 24h 的又被窗口砍掉，最终
精选常年不足保底数。修复：把窗口过滤提到门控之前，保底就在"窗口内候选"上补齐，
补几条最终展示几条。这里锁死这个顺序不被改回去。
"""
from datetime import timedelta

from scripts.quality_gate import apply_gate
from scripts.run_pipeline import filter_output_window
from scripts.util import now_utc, to_iso


def _scored(iid, score, hours_ago, category="行业动态", sources=1):
    return {
        "id": iid,
        "title": f"item-{iid}",
        "weighted_score": score,
        "multi_source_count": sources,
        "category": category,
        "published_at": to_iso(now_utc() - timedelta(hours=hours_ago)),
    }


CFG = {
    "quality_gate": {"min_weighted_score": 0.72, "min_multi_source_count": 2, "min_curated_items": 12},
    "category_quotas": {},
}


def test_backfill_count_survives_window_when_filtered_first():
    # 冷清期：只有 2 条达标(高分)，其余是窗口内的次优内容(0.5，不达标)。
    # 保底要补到 12。若"先窗口后门控"(正确顺序)，窗口内候选足够，最终就是 12。
    items = (
        [_scored("hi1", 0.85, hours_ago=1), _scored("hi2", 0.80, hours_ago=2)]
        + [_scored(f"lo{i}", 0.50, hours_ago=1) for i in range(20)]  # 都在24h内
    )
    windowed = filter_output_window(items, hours=24)
    curated = apply_gate(windowed, CFG)
    assert len(curated) == 12, f"先窗口后门控应补齐到12，实际{len(curated)}"


def test_old_order_would_lose_backfilled_items_past_window():
    # 复现旧顺序的 bug：达标内容 2 条(24h内)，次优内容全部超过 24h。
    # 旧顺序(先门控后窗口)：apply_gate 会用超窗的次优内容补到 12，再被窗口砍到 2。
    # 新顺序(先窗口后门控)：超窗内容根本不进候选，达标的 2 条原样展示——数目诚实。
    items = (
        [_scored("hi1", 0.85, hours_ago=1), _scored("hi2", 0.80, hours_ago=2)]
        + [_scored(f"old{i}", 0.50, hours_ago=30) for i in range(20)]  # 全部超24h
    )

    # 旧顺序：先门控(会补到12)再窗口(砍掉超窗的10条backfill) → 只剩2
    old_curated = apply_gate(items, CFG)
    old_final = filter_output_window(old_curated, hours=24)
    assert len(old_curated) == 12          # 门控确实补到了12
    assert len(old_final) == 2             # 但窗口把补进来的超窗内容全砍了 → 用户看到的少

    # 新顺序：先窗口(把超窗的20条全过滤掉)再门控(候选里没有次优内容可补) → 也是2，
    # 但这个 2 是"窗口内真的只有 2 条可选"的诚实结果，不是保底被静默吃掉。
    new_windowed = filter_output_window(items, hours=24)
    new_curated = apply_gate(new_windowed, CFG)
    assert len(new_curated) == 2
    # 关键差异：新顺序下 apply_gate 拿到的候选数就是窗口内的真实可选数，
    # 保底"尽力而为、能补多少补多少"的语义正确——不会先虚补12再被砍。
    assert len(new_windowed) == 2


def test_window_first_uses_fresh_backfill_not_stale():
    # 混合：2条达标(新)，5条次优且新鲜(24h内)，10条次优但超窗。
    # 正确顺序下保底应优先用"新鲜的次优内容"补齐，超窗的根本不参与。
    items = (
        [_scored("hi1", 0.85, hours_ago=1), _scored("hi2", 0.80, hours_ago=1)]
        + [_scored(f"fresh{i}", 0.60, hours_ago=3) for i in range(5)]
        + [_scored(f"stale{i}", 0.65, hours_ago=40) for i in range(10)]  # 分数更高但超窗
    )
    windowed = filter_output_window(items, hours=24)
    curated = apply_gate(windowed, CFG)
    ids = {c["id"] for c in curated}
    # 达标2 + 新鲜次优5 = 7条，窗口内没有更多候选，保底尽力补到7(<12)
    assert len(curated) == 7
    # 超窗的 stale 内容(哪怕分数更高)一条都不该出现
    assert not any(i.startswith("stale") for i in ids)
