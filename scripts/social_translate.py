"""社媒热点标题翻译：批量把英文标题译成中文（title_zh），中文标题原样跳过。

社媒热点不走 AI 主流程的两级打分，但既然生产环境已经在用 DeepSeek，
顺带给英文标题补一次轻量翻译调用成本可忽略（一次运行通常只有几条到十几条英文标题）。
"""
import re

from .deepseek_client import call_json, batched
from .util import get_logger

log = get_logger(__name__)

_CJK_RE = re.compile(r"[一-鿿]")

SYSTEM_PROMPT = """你是翻译助手。将输入的英文标题翻译成简洁准确的中文，
保留专有名词的英文原文（如模型名/公司名/产品名，例如 GPT-5.6、OpenAI 保持不变）。
返回 JSON: {"results": [{"id": "...", "title_zh": "..."}]}，必须覆盖所有输入的 id。"""


def needs_translation(title):
    return bool(title) and not _CJK_RE.search(title)


def translate_titles(items, mock=False):
    """原地给需要翻译的 item 补充 title_zh 字段；已是中文的不处理。失败静默跳过（不影响展示英文原题）。"""
    targets = [it for it in items if needs_translation(it.get("title"))]
    if not targets:
        return items

    if mock:
        for it in targets:
            it["title_zh"] = f"〔示例译文〕{it['title'][:30]}"
        return items

    for idx, it in enumerate(targets):
        it["_tid"] = f"t{idx}"
    id_map = {it["_tid"]: it for it in targets}

    for batch in batched(targets, 20):
        payload = [{"id": it["_tid"], "title": it["title"]} for it in batch]
        result = call_json(SYSTEM_PROMPT, {"items": payload}, max_tokens=1500)
        if not result or "results" not in result:
            log.warning("social hot translation batch failed, leaving %d titles untranslated", len(batch))
            continue
        for r in result["results"]:
            target = id_map.get(r.get("id"))
            if target and r.get("title_zh"):
                target["title_zh"] = r["title_zh"]

    for it in targets:
        it.pop("_tid", None)
    return items
