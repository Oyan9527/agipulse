"""共享工具函数：配置加载、去重ID生成、URL 安全校验、HTTP会话、日志。"""
import hashlib
import logging
import os
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
import yaml

# 之前指向占位根域名 https://github.com（不是具体仓库），部分信源(尤其 Reddit)的
# 反爬规则会把这种看起来通用/身份不明的 UA 当成可疑爬虫处理。改成指向真实仓库地址，
# 是一个真实、可核实的身份标识，符合大多数站点"请求方要能被追溯"的期望。
USER_AGENT = "agi-pulse-news-aggregator/1.0 (+https://github.com/Oyan9527/agipulse)"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def get_logger(name):
    return logging.getLogger(name)


def load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def make_id(*parts):
    raw = "|".join(str(p) for p in parts if p is not None)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


_SAFE_SCHEMES = ("http", "https")


def safe_http_url(url):
    """只放行 http/https 链接，其余（javascript:、data:、file: 等）返回 None。

    条目的 url / image_url 直接来自第三方 RSS 与 API，会被前端写进 <a href> 和 <img src>。
    javascript: 链接一旦被点击就是 XSS。在入库时就丢弃，前端另有兜底（docs/js/safe.js）。
    """
    if not isinstance(url, str):
        return None
    url = url.strip()
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if parsed.scheme.lower() not in _SAFE_SCHEMES or not parsed.netloc:
        return None
    return url


def now_utc():
    return datetime.now(timezone.utc)


def to_iso(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


_local = __import__("threading").local()


def get_session():
    # 每线程一个 Session：requests.Session 并非严格线程安全，抓取器在线程池里并发运行
    if getattr(_local, "session", None) is None:
        _local.session = requests.Session()
        _local.session.headers.update({"User-Agent": USER_AGENT})
    return _local.session


def env(name, default=None):
    return os.environ.get(name, default)
