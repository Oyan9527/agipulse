"""GitHub releases 抓取器：走 REST API，若配置了 GH_PAT 则提升限额到 5000/小时。"""
from datetime import datetime, timezone

from ..util import get_session, env, get_logger

log = get_logger(__name__)

API_BASE = "https://api.github.com"


def fetch(source):
    repo = source["repo"]
    session = get_session()
    headers = {"Accept": "application/vnd.github+json"}
    token = env("GH_PAT")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    resp = session.get(
        f"{API_BASE}/repos/{repo}/releases",
        headers=headers,
        params={"per_page": 10},
        timeout=20,
    )
    resp.raise_for_status()
    releases = resp.json()

    items = []
    for r in releases:
        if r.get("draft"):
            continue
        published_at = None
        ts = r.get("published_at") or r.get("created_at")
        if ts:
            published_at = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            )
        title = f"{repo} {r.get('tag_name') or r.get('name') or ''}".strip()
        items.append(
            {
                "title": title,
                "url": r.get("html_url", ""),
                "published_at": published_at,
                "raw_text": (r.get("body") or "")[:2000],
            }
        )
    return items
