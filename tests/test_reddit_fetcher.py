"""Reddit 抓取器限流的回归测试（scripts.fetch.reddit_fetcher）。

背景：真实线上数据显示全部 19 个 reddit 类型信源在同一轮里 100% 返回
429 Too Many Requests，last_success 始终是 None。整条流水线用10个线程并发
抓取全部信源，19 个 subreddit 很可能被分到同一时间窗口、几秒内对 reddit.com
发起十几个并发请求——这正是限流最容易触发的模式。修复：全局锁 + 最小请求
间隔，把 reddit 抓取强制串行、彼此间隔至少 MIN_INTERVAL_SECONDS 秒。
"""
from scripts.fetch import reddit_fetcher


def test_fetch_builds_correct_reddit_rss_url(monkeypatch):
    captured = {}

    def fake_fetch(pseudo_source):
        captured["url"] = pseudo_source["url"]
        return []

    monkeypatch.setattr(reddit_fetcher, "_last_request_at", 0.0)
    monkeypatch.setattr(reddit_fetcher.rss_fetcher, "fetch", fake_fetch)
    reddit_fetcher.fetch({"subreddit": "MachineLearning"})
    assert captured["url"] == "https://www.reddit.com/r/MachineLearning/.rss"


def test_fetch_returns_whatever_rss_fetcher_returns(monkeypatch):
    monkeypatch.setattr(reddit_fetcher, "_last_request_at", 0.0)
    monkeypatch.setattr(reddit_fetcher.rss_fetcher, "fetch", lambda s: [{"title": "x"}])
    assert reddit_fetcher.fetch({"subreddit": "OpenAI"}) == [{"title": "x"}]


def test_back_to_back_calls_are_serialized_with_minimum_interval(monkeypatch):
    # 假时钟：不真的等待，只验证 sleep 被要求等待了多久
    fake_time = [1000.0]

    def fake_monotonic():
        return fake_time[0]

    sleeps = []

    def fake_sleep(seconds):
        sleeps.append(seconds)
        fake_time[0] += seconds

    monkeypatch.setattr(reddit_fetcher, "_last_request_at", 0.0)
    monkeypatch.setattr(reddit_fetcher.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(reddit_fetcher.time, "sleep", fake_sleep)
    monkeypatch.setattr(reddit_fetcher.rss_fetcher, "fetch", lambda s: [])

    reddit_fetcher.fetch({"subreddit": "a"})   # 距上次请求"很久"（初始值0.0），不需要等
    reddit_fetcher.fetch({"subreddit": "b"})   # 紧接着调用，必须等满整个间隔
    reddit_fetcher.fetch({"subreddit": "c"})   # 同样紧接着，再等满一次

    assert sleeps == [reddit_fetcher.MIN_INTERVAL_SECONDS, reddit_fetcher.MIN_INTERVAL_SECONDS]


def test_enough_elapsed_time_skips_the_wait(monkeypatch):
    fake_time = [1000.0]
    monkeypatch.setattr(reddit_fetcher, "_last_request_at", 0.0)
    monkeypatch.setattr(reddit_fetcher.time, "monotonic", lambda: fake_time[0])
    slept = []
    monkeypatch.setattr(reddit_fetcher.time, "sleep", lambda s: slept.append(s))
    monkeypatch.setattr(reddit_fetcher.rss_fetcher, "fetch", lambda s: [])

    reddit_fetcher.fetch({"subreddit": "a"})
    fake_time[0] += reddit_fetcher.MIN_INTERVAL_SECONDS + 1  # 模拟两次调用之间已经过了足够久
    reddit_fetcher.fetch({"subreddit": "b"})

    assert slept == []   # 间隔已经够了，不该再额外等待
