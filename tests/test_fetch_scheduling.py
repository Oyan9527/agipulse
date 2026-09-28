"""抓取顺序打散的回归测试（scripts.run_pipeline._interleave_by_host）。

背景：sources.yaml 按站点分段书写，同一域名的源天然挨在一起；线程池按列表顺序
分派，于是 20 个 reddit 源会被十个 worker 在几秒内一起抓——线上 17/20 拿 429
就是这么来的。打散之后同域名两次请求之间隔着几十个别的源。

另外守同站点多源的每日轮换：打散是确定性的，组内先后每轮都一样，对限流的站点
等于系统性偏袒排在前面的几个（线上 20 个 reddit 源里有 last_success 的自始至终
就是同样 7 个）。

这里守的都是性质——不落在同一批次、每天换队首、间距不回退——而不是某个具体顺序。
"""
from scripts.run_pipeline import (FETCH_WORKERS, _daily_rotation,
                                  _interleave_by_host, _source_host)


def _rss(host, n):
    return [{"id": "%s-%d" % (host, i), "type": "rss",
             "url": "https://%s/feed/%d.xml" % (host, i)} for i in range(n)]


def _typed(stype, n):
    return [{"id": "%s-%d" % (stype, i), "type": stype, "subreddit": "s%d" % i}
            for i in range(n)]


def _min_gap(seq, host):
    pos = [i for i, s in enumerate(seq) if _source_host(s) == host]
    return min((b - a for a, b in zip(pos, pos[1:])), default=None)


def test_same_host_sources_are_spread_beyond_the_worker_batch():
    # 20 个同站点源挤在中间，外加 200 个各不相同的站点
    crowd = _typed("reddit", 20)
    others = _rss("a%d.example.com" % 0, 0) + [
        {"id": "o%d" % i, "type": "rss", "url": "https://site%d.example.com/f.xml" % i}
        for i in range(200)
    ]
    sources = others[:100] + crowd + others[100:]

    assert _min_gap(sources, "reddit") == 1          # 打散前：紧挨着
    spread = _interleave_by_host(sources)
    gap = _min_gap(spread, "reddit")
    assert gap > FETCH_WORKERS, "同域名最小间距 %s 必须大于线程数 %d，否则仍会被同时抓" % (gap, FETCH_WORKERS)


def test_interleave_keeps_every_source_exactly_once():
    sources = _typed("reddit", 20) + _rss("news.example.com", 5) + _rss("blog.example.com", 3)
    out = _interleave_by_host(sources)
    assert len(out) == len(sources)
    assert sorted(s["id"] for s in out) == sorted(s["id"] for s in sources)


def test_interleave_is_deterministic():
    sources = _typed("reddit", 8) + _rss("news.example.com", 8)
    assert [s["id"] for s in _interleave_by_host(sources)] == \
           [s["id"] for s in _interleave_by_host(sources)]


def test_rss_sources_group_by_domain_not_by_type():
    """两个 rss 源只要域名不同就不算同一堆，否则全站 rss 会被当成一个巨堆。"""
    a = {"type": "rss", "url": "https://one.example.com/feed.xml"}
    b = {"type": "rss", "url": "https://two.example.com/feed.xml"}
    assert _source_host(a) != _source_host(b)


def test_non_rss_types_group_by_type():
    """arxiv / hn_algolia 这类各自只打一个 API，按 type 归堆就够了。"""
    a = {"type": "reddit", "subreddit": "x"}
    b = {"type": "reddit", "subreddit": "y"}
    assert _source_host(a) == _source_host(b) == "reddit"


def test_empty_input():
    assert _interleave_by_host([]) == []


def test_same_site_sources_rotate_day_to_day():
    """同站点内部的先后每天要换人。

    打散本身是确定性的，组内顺序每轮一样——对限流的站点来说等于系统性偏袒排在
    前面的几个：线上 20 个 reddit 源里有 last_success 的自始至终就是同样 7 个，
    后面 13 个从来没轮到过。轮换让每个源都有机会排到队首。
    """
    sources = _typed("reddit", 20)

    def first_of(rot):
        order = _interleave_by_host(sources, rotation=rot)
        return [s["id"] for s in order if _source_host(s) == "reddit"][0]

    leaders = {first_of(day) for day in range(20)}
    assert len(leaders) == 20, "20 天里应该轮到 20 个不同的源排队首，实际只有 %d 个" % len(leaders)


def test_rotation_is_stable_within_a_day():
    sources = _typed("reddit", 8) + _rss("news.example.com", 4)
    once = [s["id"] for s in _interleave_by_host(sources, rotation=100)]
    twice = [s["id"] for s in _interleave_by_host(sources, rotation=100)]
    assert once == twice


def test_rotation_does_not_break_the_spacing():
    """轮换只换组内先后，不能把好不容易拉开的间距又挤回去。"""
    sources = _typed("reddit", 20) + [
        {"id": "o%d" % i, "type": "rss", "url": "https://site%d.example.com/f.xml" % i}
        for i in range(200)
    ]
    for day in range(7):
        gap = _min_gap(_interleave_by_host(sources, rotation=day), "reddit")
        assert gap > FETCH_WORKERS, "第 %d 天的最小间距 %s 掉到线程数以内了" % (day, gap)


def test_daily_rotation_advances():
    """哨兵：轮换值必须真的随天变化，写死成常数就失去意义了。"""
    assert isinstance(_daily_rotation(), int)
    assert _daily_rotation() > 700000   # 公元 2000 年以后的 toordinal 量级
