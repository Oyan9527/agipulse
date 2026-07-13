"""质量门控（scripts.quality_gate.apply_gate）的回归测试。

覆盖三层逻辑：过门槛判据（高分或多源）、分类 max/min 配额、以及全局保底
（min_curated_items）——后者用于 DeepSeek 冷清期打分普遍偏低、达标条目个位数、
首页近乎空白的场景：从次优内容按分数跨分类补齐，但仍尊重各分类 max 上限。
"""
from scripts.quality_gate import apply_gate


def _item(iid, score, category="行业动态", sources=1):
    return {
        "id": iid,
        "title": f"item-{iid}",
        "weighted_score": score,
        "multi_source_count": sources,
        "category": category,
    }


# 全局保底关闭时（min_curated_items=0）只按门槛+分类配额，行为与旧版一致
BASE_CFG = {
    "quality_gate": {"min_weighted_score": 0.72, "min_multi_source_count": 2, "min_curated_items": 0},
    "category_quotas": {},
}


def _cfg(min_curated=0, quotas=None):
    return {
        "quality_gate": {
            "min_weighted_score": 0.72,
            "min_multi_source_count": 2,
            "min_curated_items": min_curated,
        },
        "category_quotas": quotas or {},
    }


# --- 过门槛判据 ---

def test_high_score_passes_and_low_score_rejected():
    items = [_item("a", 0.80), _item("b", 0.50), _item("c", 0.72)]
    curated = apply_gate(items, BASE_CFG)
    ids = {c["id"] for c in curated}
    assert ids == {"a", "c"}          # 0.72 是包含边界；0.50 不达标
    assert all(c["curated"] for c in curated)


def test_multi_source_passes_even_with_low_score():
    # 多源确认是独立的过门槛路径：分数不够但 >=2 源也算精选
    items = [_item("a", 0.40, sources=2), _item("b", 0.40, sources=1)]
    curated = apply_gate(items, BASE_CFG)
    assert {c["id"] for c in curated} == {"a"}


def test_unscored_items_never_curated():
    items = [_item("a", 0.90), {"id": "b", "title": "x", "weighted_score": None, "category": "行业动态"}]
    curated = apply_gate(items, BASE_CFG)
    assert {c["id"] for c in curated} == {"a"}


# --- 分类配额 ---

def test_max_quota_caps_a_flooding_category_by_score():
    # 论文研究 max=2：5 条都过门槛，只保留分数最高的 2 条
    items = [_item(f"p{i}", 0.75 + i * 0.01, category="论文研究") for i in range(5)]
    cfg = _cfg(quotas={"论文研究": {"max": 2}})
    curated = apply_gate(items, cfg)
    papers = [c for c in curated if c["category"] == "论文研究"]
    assert len(papers) == 2
    assert {c["id"] for c in papers} == {"p3", "p4"}   # 0.78 / 0.79 最高


def test_min_quota_backfills_from_rejected_pool():
    # 开源项目 min=3：只有 1 条过门槛，从未过门槛的已打分条目补 2 条
    items = [
        _item("ok", 0.80, category="开源项目"),
        _item("lo1", 0.60, category="开源项目"),
        _item("lo2", 0.55, category="开源项目"),
        _item("lo3", 0.30, category="开源项目"),
    ]
    cfg = _cfg(quotas={"开源项目": {"min": 3}})
    curated = apply_gate(items, cfg)
    oss = sorted((c for c in curated if c["category"] == "开源项目"), key=lambda x: -x["weighted_score"])
    assert [c["id"] for c in oss] == ["ok", "lo1", "lo2"]   # 按分数补最高的两条
    assert oss[0].get("gate_backfill") is None              # 过门槛的不标 backfill
    assert oss[1]["gate_backfill"] is True                  # 补足的标 backfill


# --- 全局保底 ---

def test_global_floor_backfills_when_curated_too_thin():
    # 冷清期：只有 2 条过门槛，min_curated_items=6 时从次优内容补到 6
    items = [_item("hi1", 0.85), _item("hi2", 0.75)] + [
        _item(f"lo{i}", 0.60 - i * 0.01) for i in range(10)
    ]
    cfg = _cfg(min_curated=6)
    curated = apply_gate(items, cfg)
    assert len(curated) == 6
    backfilled = [c for c in curated if c.get("gate_backfill")]
    assert len(backfilled) == 4
    # 补足的应是分数最高的次优条目（lo0=0.60, lo1=0.59, lo2=0.58, lo3=0.57）
    assert {c["id"] for c in backfilled} == {"lo0", "lo1", "lo2", "lo3"}


def test_global_floor_is_noop_when_enough_pass():
    # 忙碌日：8 条过门槛，min_curated_items=6 不触发任何补足
    items = [_item(f"hi{i}", 0.75 + i * 0.01) for i in range(8)]
    cfg = _cfg(min_curated=6)
    curated = apply_gate(items, cfg)
    assert len(curated) == 8
    assert not any(c.get("gate_backfill") for c in curated)


def test_global_floor_respects_max_cap_no_paper_flooding():
    # 全局保底不能突破分类 max：论文研究 max=1，保底补齐时也不该塞第 2 篇论文
    items = [
        _item("news", 0.80, category="行业动态"),
        _item("paper_hi", 0.78, category="论文研究"),   # 过门槛，占掉论文的唯一名额
        _item("paper_lo1", 0.60, category="论文研究"),   # 次优，但论文已满，保底不能选它
        _item("paper_lo2", 0.58, category="论文研究"),
        _item("blog_lo", 0.50, category="行业动态"),     # 次优的非论文，应被保底选中
    ]
    cfg = _cfg(min_curated=3, quotas={"论文研究": {"max": 1}})
    curated = apply_gate(items, cfg)
    papers = [c for c in curated if c["category"] == "论文研究"]
    assert len(papers) == 1                               # max=1 未被保底突破
    assert {c["id"] for c in curated} == {"news", "paper_hi", "blog_lo"}


def test_global_floor_stops_when_pool_exhausted():
    # 池子本身不足：只有 3 条已打分，min_curated_items=12 也只能给出 3 条，不报错
    items = [_item("a", 0.90), _item("b", 0.40), _item("c", 0.30)]
    cfg = _cfg(min_curated=12)
    curated = apply_gate(items, cfg)
    assert len(curated) == 3
    assert sum(1 for c in curated if c.get("gate_backfill")) == 2


# --- 比例配额（max_ratio）：占比而非固定数量的上限 ---

def test_ratio_quota_caps_category_share_of_total():
    # 8 篇论文 + 2 条资讯全部过门槛，另有 6 条未过门槛的资讯供补足池——
    # 论文占比上限 25%：int(10*0.25)=2，裁掉 6 篇，用补足池的资讯填满总量
    items = (
        [_item(f"p{i}", 0.72 + i * 0.01, category="论文研究") for i in range(8)]
        + [_item(f"news{i}", 0.90 - i * 0.01, category="行业动态") for i in range(2)]
        + [_item(f"lo{i}", 0.60 - i * 0.01, category="行业动态") for i in range(6)]
    )
    cfg = _cfg(quotas={"论文研究": {"max_ratio": 0.25}})
    curated = apply_gate(items, cfg)
    assert len(curated) == 10   # 补足池够用，总量不变，只调整分类构成
    papers = [c for c in curated if c["category"] == "论文研究"]
    assert len(papers) == 2
    assert {c["id"] for c in papers} == {"p6", "p7"}   # 分数最高的两篇 (0.78/0.79)


def test_ratio_quota_noop_when_already_under_limit():
    items = [_item("p0", 0.90, category="论文研究")] + [
        _item(f"news{i}", 0.80, category="行业动态") for i in range(5)
    ]
    cfg = _cfg(quotas={"论文研究": {"max_ratio": 0.25}})
    curated = apply_gate(items, cfg)
    assert len(curated) == 6
    papers = [c for c in curated if c["category"] == "论文研究"]
    assert len(papers) == 1   # 1/6 ≈ 16.7% < 25%，不触发裁剪
    assert not any(c.get("gate_backfill") for c in curated)


def test_ratio_quota_uses_whichever_cap_is_stricter():
    # 总量小(4条)时 max=10(绝对值)本身不会触发，但 max_ratio=0.25 应把论文限到 int(4*0.25)=1
    items = [_item(f"p{i}", 0.75 + i * 0.01, category="论文研究") for i in range(3)] + [
        _item("news", 0.90, category="行业动态")
    ]
    cfg = _cfg(quotas={"论文研究": {"max": 10, "max_ratio": 0.25}})
    curated = apply_gate(items, cfg)
    papers = [c for c in curated if c["category"] == "论文研究"]
    assert len(papers) == 1
    assert papers[0]["id"] == "p2"   # 0.77 最高


def test_ratio_quota_shrinks_total_when_backfill_pool_exhausted():
    # 8 篇论文全部过门槛，没有任何其它分类的候选可补——裁剪后补不满，总量应缩小而非报错
    items = [_item(f"p{i}", 0.72 + i * 0.01, category="论文研究") for i in range(8)]
    cfg = _cfg(quotas={"论文研究": {"max_ratio": 0.25}})
    curated = apply_gate(items, cfg)
    assert len(curated) == 2   # int(8*0.25)=2，补不满就接受总量缩小
    assert {c["id"] for c in curated} == {"p6", "p7"}


def test_ratio_quota_also_trims_global_floor_backfilled_papers():
    # 全局保底先把总量从1拉到4(补3篇未过门槛的论文)；比例配额再基于总量4把论文限到
    # int(4*0.25)=1，但没有其它分类的候选可补裁掉的名额，总量缩回2。
    items = [_item("news", 0.90, category="行业动态")] + [
        _item(f"paper{i}", 0.60 - i * 0.01, category="论文研究") for i in range(6)
    ]
    cfg = _cfg(min_curated=4, quotas={"论文研究": {"max_ratio": 0.25}})
    curated = apply_gate(items, cfg)
    assert len(curated) == 2
    assert {c["id"] for c in curated} == {"news", "paper0"}
