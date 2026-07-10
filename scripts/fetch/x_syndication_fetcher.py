"""X（Twitter）AI 高信号账号推文抓取器。

X 官方免费 API 已取消搜索/趋势权限，公共 RSSHub 实例的 /twitter/* 路由需要登录 Cookie
（实测 rsshub.app 404、其余实例 503），Nitter 实例 403。因此无法做"平台内 AI 关键词检索"。

改走 syndication.twitter.com —— X 官方给第三方网站嵌入时间线用的公开端点，无需 Key，
返回一个内嵌 __NEXT_DATA__ 的页面，其中含指定账号最近的推文（正文/时间/永久链接/互动数）。
于是把 X 这一栏做成"追踪 AI 高信号账号"（对齐 AGI Hunt 的思路）：合并多个账号的推文，
按互动量排序，再由 build_social_hot 走 ai_relevance 过滤掉闲聊，只留 AI 话题。

单账号失败不影响其他账号（各自 try/except），全部失败才算该源失败。
"""
import json
import re
import time
from datetime import datetime, timezone

from ..util import get_session, get_logger

log = get_logger(__name__)

# 该端点按 IP 限流：单轮抓十个账号没问题，但短时间内反复抓会累积触发 429。
# 流水线 4 小时才跑一轮，账号间留间隔 + 429 退避重试即可。
REQUEST_GAP_SECONDS = 2.5
MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = 10

ENDPOINT = "https://syndication.twitter.com/srv/timeline-profile/screen-name/{}"
_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S
)
_TCO_RE = re.compile(r"https?://t\.co/\w+")
_WS_RE = re.compile(r"\s+")

# 非浏览器 UA 会被挡；这个端点本就是给网页嵌入用的
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _clean_text(text):
    """推文正文里嵌的 t.co 短链是图片/引用的占位，展示时没有意义，去掉；换行压成空格。"""
    return _WS_RE.sub(" ", _TCO_RE.sub("", text or "")).strip()


def _parse_created_at(value):
    # X 的格式："Thu Jul 09 17:41:57 +0000 2026"
    try:
        return datetime.strptime(value, "%a %b %d %H:%M:%S %z %Y")
    except (TypeError, ValueError):
        return None


def _get_with_retry(session, url):
    """429 是这个端点最常见的失败：退避后重试，仍失败则交由上层跳过该账号。"""
    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        resp = session.get(url, headers={"User-Agent": _BROWSER_UA}, timeout=20)
        if resp.status_code != 429:
            resp.raise_for_status()
            return resp
        last_error = f"429 rate limited (attempt {attempt + 1})"
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
    raise RuntimeError(last_error)


def _fetch_account(session, screen_name, max_age_hours):
    resp = _get_with_retry(session, ENDPOINT.format(screen_name))
    match = _NEXT_DATA_RE.search(resp.text)
    if not match:
        raise ValueError("__NEXT_DATA__ not found (page structure changed?)")
    payload = json.loads(match.group(1))
    entries = payload["props"]["pageProps"]["timeline"]["entries"]

    now = datetime.now(timezone.utc)
    items = []
    seen_any_tweet = False
    for entry in entries:
        if entry.get("type") != "tweet":
            continue
        tweet = (entry.get("content") or {}).get("tweet")
        if not tweet:
            continue
        seen_any_tweet = True
        text = tweet.get("full_text") or tweet.get("text") or ""
        if text.startswith("RT @"):
            continue  # 转推不算该账号的信号
        created = _parse_created_at(tweet.get("created_at"))
        if created and max_age_hours and (now - created).total_seconds() > max_age_hours * 3600:
            continue
        permalink = tweet.get("permalink") or ""
        cleaned = _clean_text(text)
        if not cleaned or not permalink:
            continue
        items.append(
            {
                "title": cleaned,
                "url": f"https://x.com{permalink}",
                "raw_text": "",
                "_heat": (tweet.get("favorite_count") or 0) + (tweet.get("retweet_count") or 0) * 2,
            }
        )

    if seen_any_tweet and not items:
        # 该端点对部分账号只返回一份乱序的历史快照（最新一条常在数月前），
        # 表现就是抓到了推文却一条都不在时间窗内。这类账号不产内容却照占限流配额，
        # 见到这条日志就该把它从 sources.yaml 的 accounts 里删掉。
        log.warning(
            "x_syndication %s: 抓到推文但无一条在 %dh 内，疑似历史快照账号，建议移除",
            screen_name, max_age_hours,
        )
    return items


def fetch(source):
    accounts = source.get("accounts") or []
    max_age_hours = source.get("max_age_hours", 72)
    session = get_session()

    items, failures = [], 0
    for idx, name in enumerate(accounts):
        if idx:
            time.sleep(REQUEST_GAP_SECONDS)  # 节流，否则连打十个账号会被 429
        try:
            items.extend(_fetch_account(session, name, max_age_hours))
        except Exception as e:  # noqa: BLE001 - 单账号失败不影响其他账号
            failures += 1
            log.warning("x_syndication account %s failed: %s", name, e)

    if accounts and failures == len(accounts):
        raise RuntimeError(f"all {failures} X accounts failed")

    # 按互动量排序：面板只展示前若干条，优先给热度高的
    items.sort(key=lambda it: it["_heat"], reverse=True)
    for it in items:
        it.pop("_heat", None)
    log.info(
        "x_syndication: %d tweets from %d/%d accounts",
        len(items), len(accounts) - failures, len(accounts),
    )
    return items
