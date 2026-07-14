"""x_syndication_fetcher 新鲜度过滤的回归测试。

踩过的坑：`if created and max_age_hours and (now - created) > ...` 在 created_at
解析失败(created=None)时，整个条件短路成 False，新鲜度检查被完全跳过——不管这条
推文实际发了多久，只要时间戳解析不了就会被无条件放行，这跟"验证不了新鲜度就该
保守丢弃"的意图正好相反。同时这类账号会绕过 seen_any_tweet 那条"疑似历史快照
账号"的日志兜底，因为 items 不会因此变空。
"""
import json
from datetime import datetime, timedelta, timezone

from scripts.fetch import x_syndication_fetcher as mod


class _FakeResponse:
    def __init__(self, text):
        self.text = text
        self.status_code = 200

    def raise_for_status(self):
        pass


class _FakeSession:
    def __init__(self, text):
        self._text = text

    def get(self, url, headers=None, timeout=None):
        return _FakeResponse(self._text)


def _tweet(text="hello", created_at="not-a-real-date", permalink="/user/status/1", heat=0):
    return {
        "full_text": text,
        "created_at": created_at,
        "permalink": permalink,
        "favorite_count": heat,
        "retweet_count": 0,
    }


def _page(*tweets):
    entries = [{"type": "tweet", "content": {"tweet": t}} for t in tweets]
    payload = {"props": {"pageProps": {"timeline": {"entries": entries}}}}
    return (
        '<script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(payload)
        + "</script>"
    )


def test_unparseable_created_at_is_dropped_when_freshness_filter_active():
    session = _FakeSession(_page(_tweet(created_at="not-a-real-date")))
    items = mod._fetch_account(session, "someacct", max_age_hours=72)
    assert items == []


def test_unparseable_created_at_kept_when_freshness_filter_disabled():
    session = _FakeSession(_page(_tweet(created_at="not-a-real-date")))
    items = mod._fetch_account(session, "someacct", max_age_hours=0)
    assert len(items) == 1


def test_valid_recent_tweet_kept():
    recent = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%a %b %d %H:%M:%S +0000 %Y")
    session = _FakeSession(_page(_tweet(created_at=recent)))
    items = mod._fetch_account(session, "someacct", max_age_hours=72)
    assert len(items) == 1


def test_valid_but_stale_tweet_dropped():
    stale = (datetime.now(timezone.utc) - timedelta(hours=200)).strftime("%a %b %d %H:%M:%S +0000 %Y")
    session = _FakeSession(_page(_tweet(created_at=stale)))
    items = mod._fetch_account(session, "someacct", max_age_hours=72)
    assert items == []


def test_mixed_batch_only_drops_unparseable_and_stale():
    recent = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%a %b %d %H:%M:%S +0000 %Y")
    stale = (datetime.now(timezone.utc) - timedelta(hours=200)).strftime("%a %b %d %H:%M:%S +0000 %Y")
    session = _FakeSession(_page(
        _tweet(text="good one", created_at=recent, permalink="/u/status/1"),
        _tweet(text="too old", created_at=stale, permalink="/u/status/2"),
        _tweet(text="bad date", created_at="garbage", permalink="/u/status/3"),
    ))
    items = mod._fetch_account(session, "someacct", max_age_hours=72)
    assert [it["title"] for it in items] == ["good one"]
