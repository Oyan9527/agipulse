"""社媒热点 / GitHub 涨星榜文案翻译：批量把英文文本译成中文，中文原文原样跳过。

这两块都不走 AI 主流程的两级打分，但既然生产环境已经在用 DeepSeek，
顺带补一次轻量翻译调用成本可忽略（一次运行通常只有几条到十几条英文文本）。
"""
import re

from .deepseek_client import call_json, batched
from .util import get_logger

log = get_logger(__name__)

_CJK_RE = re.compile(r"[一-鿿]")

SYSTEM_PROMPT = """你是翻译助手。将输入的英文文本翻译成简洁准确的中文，
保留专有名词的英文原文（如模型名/公司名/产品名/编程语言名，例如 GPT-5.6、OpenAI、Python 保持不变）。
返回 JSON: {"results": [{"id": "...", "zh": "..."}]}，必须覆盖所有输入的 id。"""


def needs_translation(text):
    return bool(text) and not _CJK_RE.search(text)


def translate_field(items, field, target_field, mock=False, mock_len=30):
    """原地给 items 里 field 是英文的补充 target_field 中文翻译；已是中文的不处理。
    失败静默跳过（不影响展示英文原文）。
    """
    targets = [it for it in items if needs_translation(it.get(field))]
    if not targets:
        return items

    if mock:
        for it in targets:
            it[target_field] = f"〔示例译文〕{it[field][:mock_len]}"
        return items

    for idx, it in enumerate(targets):
        it["_tid"] = f"t{idx}"
    id_map = {it["_tid"]: it for it in targets}

    for batch in batched(targets, 20):
        payload = [{"id": it["_tid"], "text": it[field]} for it in batch]
        result = call_json(SYSTEM_PROMPT, {"items": payload}, max_tokens=2000)
        if not result or "results" not in result:
            log.warning("translation batch failed for field=%s, leaving %d untranslated", field, len(batch))
            continue
        for r in result["results"]:
            target = id_map.get(r.get("id"))
            if target and r.get("zh"):
                target[target_field] = r["zh"]

    for it in targets:
        it.pop("_tid", None)
    return items


def translate_titles(items, mock=False):
    return translate_field(items, "title", "title_zh", mock=mock)
