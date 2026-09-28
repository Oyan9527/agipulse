"""Reddit 抓取器限流的回归测试（scripts.fetch.reddit_fetcher）。

背景：真实线上数据显示全部 reddit 类型信源在同一轮里返回 429 Too Many
Requests。整条流水线用10个线程并发抓取全部信源，20 个 subreddit 很可能被分到
同一时间窗口、几秒内对 reddit.com 发起十几个并发请求——这正是限流最容易触发的
模式。第一版修复：全局锁 + 最小请求间隔，把 reddit 抓取强制串行。

第一版上线后线上仍然 17/20 吃 429（只有 3 个源活下来，说明不是 IP 段封禁而是
节奏问题）。第二版加了自适应退避和当轮预算，并在 rss_fetcher 里让 429 不再盲目
重试——原先每个失败的源会在锁内连打 3 次，真实密度是"3 秒 3 次"，等于火上浇油。

注意退避状态是模块级全局，测试之间会互相污染，所以下面用 autouse fixture 复位。
"""
import pytest
import requests

from scripts.fetch import reddit_fetcher, rss_fetcher


@pytest.fixture(autouse=True)
def _reset_backoff_state():
    reddit_fetcher._last_request_at = 0.0
    reddit_fetcher._interval = reddit_fetcher.MIN_INTERVAL_SECONDS
    reddit_fetcher._budget_start = None
    yield
    reddit_fetcher._last_request_at = 0.0
    reddit_fetcher._interval = reddit_fetcher.MIN_INTERVAL_SECONDS
    reddit_fetcher._budget_start = None


def _http_error(status):
    resp = requests.Response()
    resp.status_code = status
    return requests.HTTPError("%d" % status, response=resp)


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


def test_429_doubles_the_interval_so_we_back_off(monkeypatch):
    """吃到 429 就把间隔翻倍——继续按原节奏敲门只会让限流窗口更长。"""
    monkeypatch.setattr(reddit_fetcher.time, "monotonic", lambda: 1000.0)
    monkeypatch.setattr(reddit_fetcher.time, "sleep", lambda s: None)

    def rate_limited(_source):
        raise _http_error(429)

    monkeypatch.setattr(reddit_fetcher.rss_fetcher, "fetch", rate_limited)

    # 只验翻倍段：再往上会撞到 MAX_INTERVAL_SECONDS 的上限，那个由下一个用例管
    base = reddit_fetcher.MIN_INTERVAL_SECONDS
    for expected in (base * 2, base * 4):
        with pytest.raises(requests.HTTPError):
            reddit_fetcher.fetch({"subreddit": "x"})
        assert reddit_fetcher._interval == expected
    assert base * 4 < reddit_fetcher.MAX_INTERVAL_SECONDS


def test_interval_is_capped(monkeypatch):
    """退避有上限，否则一轮里后面的源会被前面的失败拖到无限等。"""
    monkeypatch.setattr(reddit_fetcher.time, "monotonic", lambda: 1000.0)
    monkeypatch.setattr(reddit_fetcher.time, "sleep", lambda s: None)
    monkeypatch.setattr(reddit_fetcher.rss_fetcher, "fetch",
                        lambda s: (_ for _ in ()).throw(_http_error(429)))

    for _ in range(20):
        with pytest.raises(requests.HTTPError):
            reddit_fetcher.fetch({"subreddit": "x"})

    assert reddit_fetcher._interval == reddit_fetcher.MAX_INTERVAL_SECONDS


def test_success_walks_the_interval_back_down(monkeypatch):
    """对方缓过来之后要把间隔收回去，不然剩下的源白等。"""
    monkeypatch.setattr(reddit_fetcher.time, "monotonic", lambda: 1000.0)
    monkeypatch.setattr(reddit_fetcher.time, "sleep", lambda s: None)
    reddit_fetcher._interval = reddit_fetcher.MAX_INTERVAL_SECONDS
    monkeypatch.setattr(reddit_fetcher.rss_fetcher, "fetch", lambda s: [])

    reddit_fetcher.fetch({"subreddit": "x"})
    assert reddit_fetcher._interval < reddit_fetcher.MAX_INTERVAL_SECONDS

    for _ in range(50):
        reddit_fetcher.fetch({"subreddit": "x"})
    assert reddit_fetcher._interval == reddit_fetcher.MIN_INTERVAL_SECONDS


def test_non_429_errors_do_not_trigger_backoff(monkeypatch):
    """超时/500 是这个源自己的事，不该让整个 reddit 域名跟着退避。"""
    monkeypatch.setattr(reddit_fetcher.time, "monotonic", lambda: 1000.0)
    monkeypatch.setattr(reddit_fetcher.time, "sleep", lambda s: None)
    monkeypatch.setattr(reddit_fetcher.rss_fetcher, "fetch",
                        lambda s: (_ for _ in ()).throw(_http_error(500)))

    with pytest.raises(requests.HTTPError):
        reddit_fetcher.fetch({"subreddit": "x"})
    assert reddit_fetcher._interval == reddit_fetcher.MIN_INTERVAL_SECONDS


# sources.yaml 里 reddit 类型源的数量级；参数关系按这个规模校准
TYPICAL_REDDIT_SOURCES = 20


def test_budget_covers_a_full_pass_with_room_for_backoff():
    """预算必须够按基线间隔走完一整轮，还要留出退避放大的余量。

    线上踩过：起步 6 秒 + 预算 360 秒，看着是"基线 120 秒的三倍"，可只要吃上
    几个 429、间隔翻到 24~45 秒，360 秒连一轮都走不完——20 个源里 7 个压根没
    轮到就被预算切掉，预算自己成了瓶颈（那一轮的 last_error 写着"预算已用尽"
    而不是 429，是这条守卫的由来）。

    这里守的是三个常量之间的关系，不是某个具体数值：改 MIN_INTERVAL_SECONDS
    而忘了同步 BUDGET_SECONDS 时必须红。
    """
    # 倍数取 4 不是 3：旧参数(6s/360s)恰好是 3.0 倍，卡在线上过关，可线上就是它
    # 把 7 个源挡在门外的。门槛要设在能把那组参数判红的位置，守卫才有意义。
    baseline = TYPICAL_REDDIT_SOURCES * reddit_fetcher.MIN_INTERVAL_SECONDS
    assert reddit_fetcher.BUDGET_SECONDS >= baseline * 4, (
        "预算 %.0fs 不够 %d 个源按 %.0fs 基线走完一轮(%.0fs)并留退避余量"
        % (reddit_fetcher.BUDGET_SECONDS, TYPICAL_REDDIT_SOURCES,
           reddit_fetcher.MIN_INTERVAL_SECONDS, baseline)
    )


def test_backoff_ceiling_stays_within_budget():
    """就算一路退到上限，也得能在预算里走完一轮——否则后半截源永远抓不到。"""
    worst = TYPICAL_REDDIT_SOURCES * reddit_fetcher.MAX_INTERVAL_SECONDS
    assert reddit_fetcher.MAX_INTERVAL_SECONDS > reddit_fetcher.MIN_INTERVAL_SECONDS
    # 全程顶着上限是极端情况（真到那一步说明对方铁了心限流），只要求别差一个数量级
    assert worst <= reddit_fetcher.BUDGET_SECONDS * 2


def test_budget_exhausted_skips_remaining_sources(monkeypatch):
    """预算用尽后直接跳过，别把整轮流水线拖在一个正在限流的域名上。"""
    clock = [1000.0]
    monkeypatch.setattr(reddit_fetcher.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(reddit_fetcher.time, "sleep", lambda s: None)
    monkeypatch.setattr(reddit_fetcher.rss_fetcher, "fetch", lambda s: [])

    reddit_fetcher.fetch({"subreddit": "first"})          # 起算预算
    clock[0] += reddit_fetcher.BUDGET_SECONDS + 1          # 时间烧光

    with pytest.raises(RuntimeError, match="预算"):
        reddit_fetcher.fetch({"subreddit": "later"})


def test_rss_fetcher_does_not_retry_bare_429(monkeypatch):
    """429 且对方没给 Retry-After：只请求一次就抛，不许在锁里连打三次。"""
    calls = []

    class FakeSession:
        def get(self, url, timeout=None):
            calls.append(url)
            resp = requests.Response()
            resp.status_code = 429
            resp.url = url
            return resp

    monkeypatch.setattr(rss_fetcher, "get_session", lambda: FakeSession())
    monkeypatch.setattr(rss_fetcher.time, "sleep", lambda s: None)

    with pytest.raises(requests.HTTPError):
        rss_fetcher.fetch({"url": "https://www.reddit.com/r/x/.rss"})

    assert len(calls) == 1


def test_rss_fetcher_honors_short_retry_after(monkeypatch):
    """对方明确说"等 N 秒"且等得起，就等一次再试——这是它允许的重试。"""
    calls = []
    slept = []

    class FakeSession:
        def get(self, url, timeout=None):
            calls.append(url)
            resp = requests.Response()
            resp.url = url
            if len(calls) == 1:
                resp.status_code = 429
                resp.headers["Retry-After"] = "5"
            else:
                resp.status_code = 200
                resp._content = b"<rss><channel></channel></rss>"
            return resp

    monkeypatch.setattr(rss_fetcher, "get_session", lambda: FakeSession())
    monkeypatch.setattr(rss_fetcher.time, "sleep", lambda s: slept.append(s))

    rss_fetcher.fetch({"url": "https://www.reddit.com/r/x/.rss"})
    assert len(calls) == 2
    assert slept == [5]


def test_rss_fetcher_gives_up_on_long_retry_after(monkeypatch):
    """要我们等太久就当轮放弃，别把一个源的惩罚摊到整轮抓取上。"""
    calls = []

    class FakeSession:
        def get(self, url, timeout=None):
            calls.append(url)
            resp = requests.Response()
            resp.url = url
            resp.status_code = 429
            resp.headers["Retry-After"] = str(rss_fetcher.MAX_RETRY_AFTER + 60)
            return resp

    monkeypatch.setattr(rss_fetcher, "get_session", lambda: FakeSession())
    monkeypatch.setattr(rss_fetcher.time, "sleep", lambda s: None)

    with pytest.raises(requests.HTTPError):
        rss_fetcher.fetch({"url": "https://www.reddit.com/r/x/.rss"})
    assert len(calls) == 1
