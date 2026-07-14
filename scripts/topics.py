"""话题追踪：把每日归档里的热门关键词，聚合成"某个话题过去 N 天的提及曲线"。

数据全部来自 archive/day-*.json 的 keyword_counts（每天已经算好的关键词及提及次数，
{关键词: 次数} 的扁平字典，见 archive.py），纯聚合、零 DeepSeek 成本。
前端数据版据此画迷你曲线，展示热点话题的升温/降温。
"""
from datetime import datetime, timezone

from .util import get_logger

log = get_logger(__name__)

WINDOW_DAYS = 14        # 追踪窗口：近 14 天
TOP_TOPICS = 8          # 展示最热的 8 个话题
MIN_TOTAL_MENTIONS = 3  # 窗口内总提及少于此值的话题不展示（噪声）


def build_topics(daily_archives, window_days=WINDOW_DAYS, top_n=TOP_TOPICS):
    """daily_archives：既接受 load_daily_archives 返回的 {date: payload} 字典，
    也接受 [{date, top_keywords, ...}] 列表（后者便于测试）。
    返回 {generated_at, window_days, dates:[...], topics:[{term, total, series:[...], trend}]}。
    series 与 dates 一一对应，某天没提及则为 0。
    """
    if isinstance(daily_archives, dict):
        payloads = [daily_archives[k] for k in sorted(daily_archives)]
    else:
        payloads = sorted(daily_archives, key=lambda a: a["date"])
    archives = payloads[-window_days:]
    dates = [a["date"] for a in archives]

    # 按小写归并同一话题的不同拼写（"GPT"/"Gpt" 是同一个），
    # key -> {"dates": {date: 累计count}, "forms": {原始拼写: 总提及}} 以便挑规范显示形式
    by_key = {}
    for arch in archives:
        for term, count in (arch.get("keyword_counts") or {}).items():
            if not term:
                continue
            key = term.lower()
            slot = by_key.setdefault(key, {"dates": {}, "forms": {}})
            slot["dates"][arch["date"]] = slot["dates"].get(arch["date"], 0) + count
            slot["forms"][term] = slot["forms"].get(term, 0) + count

    topics = []
    for slot in by_key.values():
        counts = slot["dates"]
        term = max(slot["forms"], key=slot["forms"].get)  # 最高频拼写作规范显示
        series = [counts.get(d, 0) for d in dates]
        total = sum(series)
        if total < MIN_TOTAL_MENTIONS:
            continue
        topics.append({
            "term": term,
            "total": total,
            "series": series,
            "trend": _trend(series),   # 后半段 vs 前半段：上升/下降/持平
        })

    # 先按窗口内总热度排，取前 N
    topics.sort(key=lambda t: t["total"], reverse=True)
    topics = topics[:top_n]

    log.info("topics: %d 个话题，窗口 %d 天", len(topics), len(dates))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_days": len(dates),
        "dates": dates,
        "topics": topics,
    }


def _trend(series):
    """用后半段与前半段的提及总量对比判断走向。数据太短时按持平处理。"""
    n = len(series)
    if n < 4:
        return "flat"
    half = n // 2
    earlier = sum(series[:half])
    later = sum(series[half:])
    if later > earlier * 1.3:
        return "up"
    if later < earlier * 0.7:
        return "down"
    return "flat"
