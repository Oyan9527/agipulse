"""每日聚合归档：为周/月维度的趋势分析积累历史。

每次运行把"当天(UTC)发布的条目"聚合成一个紧凑的日档文件：
  docs/data/archive/day-YYYY-MM-DD.json
  { date, total, by_category: {分类: 数量}, keyword_counts: {关键词: 次数} }

- 当天的文件每轮运行整体重算覆盖（当天数据随时间增长，最后一轮即全天定稿）
- 历史文件不再改动；保留最近 RETENTION_DAYS 天，更旧的自动清理
- 周/月趋势 = 聚合最近 N 个日档，部署后从第一天开始积累，历史不足时前端标注"新"
"""
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .util import get_logger

log = get_logger(__name__)

RETENTION_DAYS = 62  # 月环比需要 60 天，留 2 天余量

_DAY_FILE_RE = re.compile(r"^day-(\d{4}-\d{2}-\d{2})\.json$")


def _parse_iso(s):
    return datetime.fromisoformat(s)


def update_daily_archive(items, extract_keywords, out_dir):
    """items: 处理窗口内全部已归类条目; extract_keywords: 标题→关键词集合 的函数。"""
    archive_dir = Path(out_dir) / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now(timezone.utc).date()
    todays = [it for it in items if _parse_iso(it["published_at"]).date() == today]

    by_category = Counter(it.get("category") for it in todays if it.get("category"))
    keyword_counts = Counter()
    for it in todays:
        for kw in extract_keywords(it["title"]):
            keyword_counts[kw] += 1

    day_file = archive_dir / f"day-{today.isoformat()}.json"
    payload = {
        "date": today.isoformat(),
        "total": len(todays),
        "by_category": dict(by_category),
        "keyword_counts": dict(keyword_counts.most_common(200)),
    }
    with open(day_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)

    # 清理过期日档
    cutoff = today - timedelta(days=RETENTION_DAYS)
    removed = 0
    for p in archive_dir.glob("day-*.json"):
        m = _DAY_FILE_RE.match(p.name)
        if m and datetime.fromisoformat(m.group(1)).date() < cutoff:
            p.unlink()
            removed += 1

    log.info("archive: day-%s updated (%d items today), %d expired files removed",
             today.isoformat(), len(todays), removed)


def load_daily_archives(out_dir, days=62):
    """读取最近 N 天的日档，返回 {date_str: payload}，按日期升序。"""
    archive_dir = Path(out_dir) / "archive"
    if not archive_dir.exists():
        return {}
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=days)
    result = {}
    for p in sorted(archive_dir.glob("day-*.json")):
        m = _DAY_FILE_RE.match(p.name)
        if not m:
            continue
        if datetime.fromisoformat(m.group(1)).date() < cutoff:
            continue
        try:
            with open(p, encoding="utf-8") as f:
                result[m.group(1)] = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            log.warning("archive: skip unreadable %s (%s)", p.name, e)
    return result
