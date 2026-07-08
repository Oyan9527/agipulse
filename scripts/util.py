"""共享工具函数：配置加载、去重ID生成、HTTP会话、日志。"""
import hashlib
import logging
import os
from datetime import datetime, timezone

import requests
import yaml

USER_AGENT = "ai-signal-field/1.0 (+https://github.com; contact: repo-owner)"

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
