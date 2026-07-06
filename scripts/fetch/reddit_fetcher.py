"""Reddit .rss 端点抓取器。需要真实 User-Agent 避免 429（复用 util.get_session 的 UA）。"""
from . import rss_fetcher


def fetch(source):
    subreddit = source["subreddit"]
    pseudo_source = {"url": f"https://www.reddit.com/r/{subreddit}/.rss"}
    return rss_fetcher.fetch(pseudo_source)
