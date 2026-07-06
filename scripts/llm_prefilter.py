"""第一级：DeepSeek 便宜粗筛。批量把明显不相关/纯营销/重复噪声的条目剔除。
单批失败时保守放行（keep=True），交给下一级打分和质量门控兜底，不因粗筛失败丢数据。
"""
from .deepseek_client import call_json, batched
from .util import get_logger

log = get_logger(__name__)

SYSTEM_PROMPT = """你是一个 AI 行业信息流的粗筛助手。你会收到一批条目（id/title/snippet）。
你的任务：判断每条是否与"AI/机器学习/大模型/AI产品/AI行业"相关，并且不是纯营销软文、招聘广告或与AI无关的内容。
返回 JSON: {"results": [{"id": "...", "keep": true|false}]}，必须覆盖所有输入的 id，不要遗漏。"""


def prefilter(items, batch_size=20):
    kept = []
    for batch in batched(items, batch_size):
        payload = [
            {"id": it["id"], "title": it["title"], "snippet": it["raw_text"][:200]}
            for it in batch
        ]
        result = call_json(SYSTEM_PROMPT, {"items": payload})

        if result is None or "results" not in result:
            log.warning("prefilter batch failed, keeping all %d items as fallback", len(batch))
            kept.extend(batch)
            continue

        keep_ids = {
            r["id"] for r in result["results"] if r.get("keep", True)
        }
        judged_ids = {r["id"] for r in result["results"]}
        for it in batch:
            if it["id"] in judged_ids:
                if it["id"] in keep_ids:
                    kept.append(it)
            else:
                # 模型漏判的条目保守放行
                kept.append(it)

    log.info("prefilter: %d -> %d items", len(items), len(kept))
    return kept
