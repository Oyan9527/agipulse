"""Reddit .rss 端点抓取器。

Reddit 对未认证请求的限流很紧，而整条流水线用 FETCH_WORKERS=10 的线程池并发抓
600+ 信源，这些 subreddit 会在几秒内向 reddit.com 打出十几个并发请求——正是最容易
触发限流的模式（UA 也已在 util.py 里改成指向真实仓库地址，那是一并的低成本改善，
但主因是节奏）。

第一版用"全局锁 + 固定 3 秒间隔"把 reddit 抓取强制串行。线上实测仍然 17/20 拿到
429，原因有两个：

1. 固定 3 秒对 Reddit 还是太密；
2. 更要命的是，失败后 rss_fetcher 会在锁内连打 2 次重试，真实密度其实是"3 秒 3 次"。
   对一个已经在限流的域名，重试等于火上浇油。(2) 已在 rss_fetcher 里修掉——429
   不再盲目重试。

这一版再加两件事：
- 间隔自适应：起步 MIN_INTERVAL_SECONDS，每吃一个 429 就翻倍（上限
  MAX_INTERVAL_SECONDS），连续成功则缓慢回落。比起把固定间隔一口气调到很大，
  这样在对方状态好的时候不会白等。
- 当轮预算：所有 reddit 源合计最多花 BUDGET_SECONDS；用尽就直接跳过剩下的，
  不再把整轮流水线拖在一个被限流的域名上（它们会照常记为失败，由体检去报警）。

参数是拿线上数据调出来的，别凭感觉改：
- 起步 6 秒 + 预算 360 秒那一版，20 个源里 7 个活、6 个吃 429、剩下 7 个压根
  没轮到就被预算切掉了——退避一放大，360 秒连一轮都走不完，预算反而成了瓶颈。
- 现在起步 10 秒（20 个源的基线 200 秒），预算 900 秒，够容纳几次翻倍退避后仍把
  20 个源走完；上限提到 60 秒，是给"对方真的在气头上"留的余地。

注意退避状态是进程级的，每轮流水线都是新进程，所以不需要跨轮持久化。
"""
import threading
import time

from . import rss_fetcher
from ..util import get_logger

log = get_logger(__name__)

MIN_INTERVAL_SECONDS = 10.0
MAX_INTERVAL_SECONDS = 60.0
BUDGET_SECONDS = 900.0      # 20 个源在 10 秒基线下约 200 秒，留四倍余量给退避

_lock = threading.Lock()
_last_request_at = 0.0
_interval = MIN_INTERVAL_SECONDS
_budget_start = None


def _is_rate_limited(exc):
    resp = getattr(exc, "response", None)
    return resp is not None and resp.status_code == 429


def fetch(source):
    global _last_request_at, _interval, _budget_start

    subreddit = source["subreddit"]
    pseudo_source = {"url": "https://www.reddit.com/r/%s/.rss" % subreddit}

    with _lock:
        now = time.monotonic()
        if _budget_start is None:
            _budget_start = now
        elif now - _budget_start > BUDGET_SECONDS:
            raise RuntimeError(
                "reddit 抓取预算(%ds)已用尽，跳过 r/%s——本轮该域名持续限流"
                % (int(BUDGET_SECONDS), subreddit)
            )

        wait = _interval - (now - _last_request_at)
        if wait > 0:
            time.sleep(wait)

        try:
            items = rss_fetcher.fetch(pseudo_source)
        except Exception as e:
            if _is_rate_limited(e):
                _interval = min(_interval * 2, MAX_INTERVAL_SECONDS)
                log.warning("reddit 429 on r/%s，间隔放大到 %.1fs", subreddit, _interval)
            raise
        else:
            # 顺利拿到就慢慢把间隔收回来，但不低于基线
            _interval = max(MIN_INTERVAL_SECONDS, _interval * 0.8)
            return items
        finally:
            _last_request_at = time.monotonic()
