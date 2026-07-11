"""AI 每日总结：把当天最受关注的几条故事交给 DeepSeek，生成一段串起全局的中文综述。

复用已有的 DeepSeek 调用（打分阶段之外仅此一次额外调用，成本可忽略）。冷清日综述为空，
前端对应区块收起。mock 模式产出确定性的占位文本，供本地联调，不消耗真实额度。
"""
from datetime import datetime, timedelta, timezone

from .deepseek_client import call_json
from .util import get_logger

log = get_logger(__name__)

MAX_INPUT_STORIES = 12
BEIJING_TZ = timezone(timedelta(hours=8))

SYSTEM_PROMPT = """你是 AI 行业日报的主编。你会收到今天最受关注的若干条 AI 新闻（标题/分类/多源确认数）。
请写一段 120-180 字的中文综述，串起当天最重要的动向：先点出最重磅的一两件事，再带过其余值得注意的方向。
要求：客观、连贯的一整段话，不要分点、不要标题、不要用"今天"以外的时间词，保留模型名/公司名的英文原文。
返回 JSON: {"summary": "..."}"""


def _todays_top(curated_items):
    today = datetime.now(BEIJING_TZ).date()
    todays = [
        it for it in curated_items
        if datetime.fromisoformat(it["published_at"]).astimezone(BEIJING_TZ).date() == today
    ]
    # 重要性：先多源确认、再加权分（与头条一致）
    todays.sort(
        key=lambda x: (x.get("multi_source_count") or 1, x.get("weighted_score") or 0),
        reverse=True,
    )
    return todays[:MAX_INPUT_STORIES]


def _envelope(summary):
    now = datetime.now(timezone.utc)
    return {"date": now.date().isoformat(), "generated_at": now.isoformat(), "summary": summary}


def build_daily_digest(curated_items, mock=False):
    top = _todays_top(curated_items)
    if not top:
        return _envelope("")  # 冷清日：前端区块收起

    if mock:
        lead = top[0].get("title_zh") or top[0]["title"]
        return _envelope(f"〔示例总结〕今天 AI 领域最受关注的是「{lead}」等 {len(top)} 条动态。"
                         "正式部署时此处由 DeepSeek 根据当天头部故事生成一段连贯的中文综述。")

    payload = [
        {
            "title": it.get("title_zh") or it["title"],
            "category": it.get("category"),
            "sources": it.get("multi_source_count") or 1,
        }
        for it in top
    ]
    result = call_json(SYSTEM_PROMPT, {"stories": payload}, max_tokens=800)
    summary = (result or {}).get("summary", "").strip()
    if not summary:
        log.warning("daily_digest: LLM 未返回综述，输出空")
    log.info("daily_digest: %d 字综述（基于 %d 条头部故事）", len(summary), len(top))
    return _envelope(summary)
