"""DeepSeek Chat Completions 客户端封装（OpenAI 兼容接口），带批量调用、重试与JSON解析。"""
import json
import time

from .util import get_session, env, get_logger

log = get_logger(__name__)

API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"
MAX_RETRIES = 2


def call_json(system_prompt, user_payload, max_tokens=2000):
    """调用 DeepSeek，要求返回 JSON。失败重试 MAX_RETRIES 次，仍失败返回 None（调用方需降级处理）。"""
    api_key = env("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY not set")

    session = get_session()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }

    last_err = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = session.post(API_URL, headers=headers, json=body, timeout=60)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return json.loads(content)
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)
    log.error("DeepSeek call failed after retries: %s", last_err)
    return None


def batched(iterable, size):
    batch = []
    for x in iterable:
        batch.append(x)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch
