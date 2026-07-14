"""同源去重（scripts.dedupe.dedupe）的回归测试。

踩过的坑：标题模糊匹配对"只差一位版本号"不敏感——实测 rapidfuzz 给出
"OpenAI 发布 GPT-5" vs "OpenAI 发布 GPT-6" 相似度 93.3、"iPhone 16 发布" vs
"iPhone 17 发布" 相似度 91.7，都超过 90 的阈值，会把同源但真正不同的连续
版本发布误判成重复、静默丢弃后一条真实新闻。
"""
from datetime import datetime, timedelta, timezone

from scripts.dedupe import dedupe

CFG = {"dedupe": {"fuzzy_title_threshold": 90, "window_hours": 48}}
NOW = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)


def _item(iid, title, hours_ago=0, source="s1"):
    return {
        "id": iid,
        "title": title,
        "source_id": source,
        "published_at": (NOW - timedelta(hours=hours_ago)).isoformat(),
    }


def test_different_version_numbers_from_same_source_both_kept():
    items = [
        _item("a", "OpenAI 发布 GPT-5", hours_ago=2),
        _item("b", "OpenAI 发布 GPT-6", hours_ago=0),
    ]
    kept = dedupe(items, CFG)
    assert {it["id"] for it in kept} == {"a", "b"}


def test_different_version_numbers_other_product_both_kept():
    # 实测 fuzzy score 90.9，超过阈值90，但版本号不同(redmi13 vs redmi14)不该判重复
    items = [
        _item("a", "Redmi 13 发布", hours_ago=2),
        _item("b", "Redmi 14 发布", hours_ago=0),
    ]
    kept = dedupe(items, CFG)
    assert {it["id"] for it in kept} == {"a", "b"}


def test_lowercase_leading_product_name_not_covered_by_entity_check_but_documents_limit():
    # 已知局限：_strong_entities 沿用 story_merge 的"首字母大写才算实体"判据（避免
    # "AI 9"这类噪声被误判成型号），"iPhone"这类首字母小写的产品名提不出实体，
    # 版本号差异检测对这类标题不生效——退回原有的纯模糊匹配行为（可能仍会误判）。
    # 这里锁住"当前就是这样"的事实，不是期望行为，供以后决定是否要专门处理。
    items = [
        _item("a", "iPhone 16 发布", hours_ago=2),
        _item("b", "iPhone 17 发布", hours_ago=0),
    ]
    kept = dedupe(items, CFG)
    assert {it["id"] for it in kept} == {"a"}   # 仍会被误判成重复——已知局限，非本次修复范围


def test_genuine_near_duplicate_still_deduped():
    # 同一条内容被重复抓到，只是标点上有细微差异——这才是真正该去掉的重复
    items = [
        _item("a", "OpenAI launches GPT-5", hours_ago=2),
        _item("b", "OpenAI launches GPT-5.", hours_ago=0),
    ]
    kept = dedupe(items, CFG)
    assert {it["id"] for it in kept} == {"a"}


def test_entity_free_titles_still_deduped_by_fuzzy_match_alone():
    # 标题里提不出版本化实体的情况，行为不该变——高相似度依然按重复处理
    items = [
        _item("a", "国产大模型再迎重要进展", hours_ago=2),
        _item("b", "国产大模型再迎重要进展！", hours_ago=0),
    ]
    kept = dedupe(items, CFG)
    assert {it["id"] for it in kept} == {"a"}


def test_different_sources_never_deduped_regardless_of_similarity():
    items = [
        _item("a", "OpenAI 发布 GPT-5", hours_ago=2, source="s1"),
        _item("b", "OpenAI 发布 GPT-5", hours_ago=0, source="s2"),
    ]
    kept = dedupe(items, CFG)
    assert {it["id"] for it in kept} == {"a", "b"}


def test_outside_time_window_never_deduped():
    items = [
        _item("a", "OpenAI 发布 GPT-5", hours_ago=60),
        _item("b", "OpenAI 发布 GPT-5", hours_ago=0),
    ]
    kept = dedupe(items, CFG)
    assert {it["id"] for it in kept} == {"a", "b"}
