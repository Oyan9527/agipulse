"""Reddit .rss 端点抓取器。

真实线上数据显示：全部已配置的 reddit 类型信源(19个)在同一轮里 100% 返回
429 Too Many Requests，且 last_success 始终是 None——不是偶发限流，是结构性的。
整条流水线用 FETCH_WORKERS=10 的线程池并发抓取 300+ 信源，这些 subreddit 若
恰好被分到同一时间窗口，会在几秒内向 reddit.com 发起十几个并发请求——这正是
Reddit 未认证限流最容易触发的模式，比 User-Agent 字符串本身更关键(UA 已经在
util.py 里改成指向真实仓库地址，作为一并的低成本改善，但主因更可能是并发)。

用一把跨线程的全局锁 + 最小请求间隔，把所有 reddit 抓取强制串行、彼此至少间隔
MIN_INTERVAL_SECONDS 秒，不管被调度到哪个工作线程。19 个源 × 间隔顶多一分钟，
在4小时一轮的周期里完全不是问题。
"""
import threading
import time

from . import rss_fetcher

MIN_INTERVAL_SECONDS = 3.0

_lock = threading.Lock()
_last_request_at = 0.0


def fetch(source):
    global _last_request_at
    subreddit = source["subreddit"]
    pseudo_source = {"url": f"https://www.reddit.com/r/{subreddit}/.rss"}
    with _lock:
        wait = MIN_INTERVAL_SECONDS - (time.monotonic() - _last_request_at)
        if wait > 0:
            time.sleep(wait)
        try:
            return rss_fetcher.fetch(pseudo_source)
        finally:
            _last_request_at = time.monotonic()
