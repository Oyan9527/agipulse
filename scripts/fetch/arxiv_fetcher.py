"""arXiv 官方分类 RSS/Atom 抓取器。"""
from . import rss_fetcher


def fetch(source):
    category = source["category"]
    pseudo_source = {"url": f"http://export.arxiv.org/rss/{category}"}
    return rss_fetcher.fetch(pseudo_source)
