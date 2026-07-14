"""llm_prefilter.prefilter 对畸形 DeepSeek 返回值的健壮性回归测试。

踩过的坑：`{r["id"] for r in result["results"] ...}` 直接假设每条结果都有 id。
真实 LLM 输出偶尔会漏掉某个字段（JSON 本身合法，但 schema 不完整），
一条缺 id 就 KeyError，崩掉整批甚至整条流水线，而不是像文档承诺的"保守放行"。
"""
from scripts import llm_prefilter


def _item(iid, title="t"):
    return {"id": iid, "title": title, "raw_text": ""}


def test_missing_id_in_one_result_does_not_crash_and_keeps_the_item(monkeypatch):
    # b 缺 id：不该 KeyError，且 a/b 都应该被保留（a 正常判定 keep=True；
    # b 因为判定结果关联不回具体条目，走"漏判保守放行"）
    monkeypatch.setattr(llm_prefilter, "call_json", lambda *a, **k: {
        "results": [{"id": "a", "keep": True}, {"keep": False}]  # 第二条没有 id
    })
    kept = llm_prefilter.prefilter([_item("a"), _item("b")])
    assert {it["id"] for it in kept} == {"a", "b"}


def test_non_dict_entry_in_results_does_not_crash(monkeypatch):
    monkeypatch.setattr(llm_prefilter, "call_json", lambda *a, **k: {
        "results": [{"id": "a", "keep": True}, "not-a-dict", None]
    })
    kept = llm_prefilter.prefilter([_item("a")])
    assert {it["id"] for it in kept} == {"a"}


def test_results_not_a_list_falls_back_to_keep_all(monkeypatch):
    monkeypatch.setattr(llm_prefilter, "call_json", lambda *a, **k: {"results": "oops"})
    kept = llm_prefilter.prefilter([_item("a"), _item("b")])
    assert {it["id"] for it in kept} == {"a", "b"}


def test_normal_keep_false_still_drops_the_item(monkeypatch):
    # 确认修复没有连带削弱正常的 keep=False 丢弃逻辑
    monkeypatch.setattr(llm_prefilter, "call_json", lambda *a, **k: {
        "results": [{"id": "a", "keep": True}, {"id": "b", "keep": False}]
    })
    kept = llm_prefilter.prefilter([_item("a"), _item("b")])
    assert {it["id"] for it in kept} == {"a"}
