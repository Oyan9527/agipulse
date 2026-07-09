"""按 source.type 分发到对应抓取器。每个抓取器返回原始 item 列表（未归一化）。"""
from . import (
    rss_fetcher,
    github_fetcher,
    arxiv_fetcher,
    hn_algolia_fetcher,
    reddit_fetcher,
    generic_json_fetcher,
    social_hot_fetcher,
    gh_trending_fetcher,
)

DISPATCH = {
    "rss": rss_fetcher.fetch,
    "github_releases": github_fetcher.fetch,
    "arxiv": arxiv_fetcher.fetch,
    "hn_algolia": hn_algolia_fetcher.fetch,
    "reddit": reddit_fetcher.fetch,
    "generic_json": generic_json_fetcher.fetch,
    "baidu_hot": social_hot_fetcher.fetch_baidu,
    "bili_hot": social_hot_fetcher.fetch_bili,
    "bili_search": social_hot_fetcher.fetch_bili_search,
    "zhihu_top_search": social_hot_fetcher.fetch_zhihu,
    "gh_star_trending": gh_trending_fetcher.fetch,
}


def fetch_source(source):
    """source: dict from sources.yaml. 返回 (raw_items, error) 二元组；error 为 None 表示成功。"""
    fetch_fn = DISPATCH.get(source.get("type"))
    if fetch_fn is None:
        return [], f"unknown source type: {source.get('type')}"
    try:
        items = fetch_fn(source)
        return items, None
    except Exception as e:  # noqa: BLE001 - 单源失败不应影响整体流水线
        return [], f"{type(e).__name__}: {e}"
