"""llm_score.score_items 对畸形 DeepSeek 返回值的健壮性回归测试。

踩过的坑：`{r["id"]: r for r in result["results"]}` 直接假设每条结果都有 id，
一条缺 id 就 KeyError，崩掉整批甚至整条流水线，而不是像文档承诺的"该批标记未打分"。
四个打分维度字段之前直接 float(r.get(...))，同一类风险（非数值时崩溃）却没有像
depth_score 那样用 _clamp01 兜底——这里一并修掉，两处属于同一类缺陷。
"""
from scripts import llm_score

WEIGHTS = {"source_authority": 0.3, "novelty": 0.25, "impact": 0.25, "practical_value": 0.2}
CATEGORIES = [{"id": "行业动态"}, {"id": "论文研究"}]


def _item(iid, title="t", source="src"):
    return {"id": iid, "title": title, "raw_text": "", "source_id": source}


def _good_result(iid):
    return {
        "id": iid, "source_authority": 0.8, "novelty": 0.7, "impact": 0.6, "practical_value": 0.5,
        "category": "行业动态", "content_type": "资讯快讯", "depth_score": 0.4,
        "reason_zh": "r", "summary_zh": "s", "title_zh": None,
    }


def test_missing_id_in_one_result_does_not_crash(monkeypatch):
    b_without_id = {k: v for k, v in _good_result("b").items() if k != "id"}  # 真正缺 id 这个 key
    monkeypatch.setattr(llm_score, "call_json", lambda *a, **k: {
        "results": [_good_result("a"), b_without_id]
    })
    scored, unscored = llm_score.score_items([_item("a"), _item("b")], CATEGORIES, WEIGHTS)
    # a 正常打分；b 的判定结果因为缺 id 被丢弃、关联不回具体条目，走"未打分"兜底，而不是崩溃
    assert {it["id"] for it in scored} == {"a"}
    assert {it["id"] for it in unscored} == {"b"}


def test_non_dict_entry_in_results_does_not_crash(monkeypatch):
    monkeypatch.setattr(llm_score, "call_json", lambda *a, **k: {
        "results": [_good_result("a"), "not-a-dict"]
    })
    scored, unscored = llm_score.score_items([_item("a")], CATEGORIES, WEIGHTS)
    assert {it["id"] for it in scored} == {"a"}


def test_results_not_a_list_falls_back_to_unscored(monkeypatch):
    monkeypatch.setattr(llm_score, "call_json", lambda *a, **k: {"results": "oops"})
    scored, unscored = llm_score.score_items([_item("a")], CATEGORIES, WEIGHTS)
    assert scored == []
    assert {it["id"] for it in unscored} == {"a"}


def test_non_numeric_score_field_does_not_crash(monkeypatch):
    # source_authority 是字符串而不是数字（真实发生过的畸形LLM输出）
    bad = {**_good_result("a"), "source_authority": "high"}
    monkeypatch.setattr(llm_score, "call_json", lambda *a, **k: {"results": [bad]})
    scored, unscored = llm_score.score_items([_item("a")], CATEGORIES, WEIGHTS)
    assert len(scored) == 1
    assert unscored == []
    assert scored[0]["weighted_score"] is not None   # 没崩，且能算出一个数（source_authority 按0兜底）


def test_normal_scoring_still_works(monkeypatch):
    monkeypatch.setattr(llm_score, "call_json", lambda *a, **k: {"results": [_good_result("a")]})
    scored, unscored = llm_score.score_items([_item("a")], CATEGORIES, WEIGHTS)
    assert unscored == []
    assert scored[0]["category"] == "行业动态"
    expected = 0.3 * 0.8 + 0.25 * 0.7 + 0.25 * 0.6 + 0.2 * 0.5
    assert scored[0]["weighted_score"] == round(expected, 4)
