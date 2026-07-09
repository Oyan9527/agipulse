"""社媒 AI 热点抓取器：在各平台内检索 AI 话题（而非取通用热搜榜——
通用热榜里 AI 话题极少，见 run_pipeline.build_social_hot 的 AI 关键词过滤）。

- B站：关键词搜索按播放量排序，取 AI 相关热门视频
- 百度/知乎：保留通用热搜抓取器（当前配置未启用；通用榜无 AI 内容 + 接口受限）

独立于 AI 主流程：不进 dedupe / DeepSeek 打分，只走 build_social_hot 轻量分支。
"""
import re
from urllib.parse import quote

from ..util import get_session, get_logger

log = get_logger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")

# B站搜索接口有风控：非浏览器 UA 会返回 code:0 但 data 仅含 v_voucher、无结果。
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _strip(text):
    return _TAG_RE.sub("", text or "").strip()


def fetch_bili_search(source):
    """B站关键词搜索，按播放量排序，返回热门视频（供 AI 过滤后展示）。"""
    keyword = source.get("query", "AI 大模型")
    session = get_session()
    resp = session.get(
        "https://api.bilibili.com/x/web-interface/wbi/search/type",
        params={"search_type": "video", "keyword": keyword, "order": "click"},
        headers={"Referer": "https://www.bilibili.com/", "User-Agent": _BROWSER_UA},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise ValueError(f"bilibili search rejected: code={data.get('code')} {data.get('message')}")
    results = data.get("data", {}).get("result")
    if not results:
        raise ValueError("bilibili search returned no result (risk-control voucher?)")

    items = []
    for v in results:
        title = _strip(v.get("title"))
        bvid = v.get("bvid")
        if title and bvid:
            items.append(
                {
                    "title": title,
                    "url": f"https://www.bilibili.com/video/{bvid}",
                    "raw_text": "",
                }
            )
    return items


def fetch_weibo_hot(source):
    """微博热搜榜（实时榜）。需要 Referer: weibo.com，否则直接 403。
    这是通用热搜（非关键词搜索——微博搜索需要登录态访客系统JS指纹校验，实测无法绕过），
    AI 话题是否上榜取决于当天热点，经 ai_relevance 过滤后可能为空，属正常现象。
    """
    session = get_session()
    resp = session.get(
        "https://weibo.com/ajax/side/hotSearch",
        headers={"Referer": "https://weibo.com/"},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    items = []
    for entry in data.get("data", {}).get("realtime", []):
        if entry.get("is_ad"):
            continue
        word = entry.get("word") or entry.get("word_scheme")
        if word:
            items.append(
                {
                    "title": word,
                    "url": f"https://s.weibo.com/weibo?q={quote(word)}",
                    "raw_text": "",
                }
            )
    return items


def fetch_baidu(source):
    # 百度热搜榜的 cards[].content 嵌套深度不固定，递归展开找出所有 {word,url} 叶子节点。
    session = get_session()
    resp = session.get(
        "https://top.baidu.com/api/board?platform=wise&tab=realtime", timeout=15
    )
    resp.raise_for_status()
    data = resp.json()
    items = []

    def collect(node):
        if not isinstance(node, dict):
            return
        word, url = node.get("word"), node.get("url")
        if word and url:
            items.append({"title": word, "url": url, "raw_text": ""})
        for child in node.get("content") or []:
            collect(child)

    for card in data.get("data", {}).get("cards", []):
        collect(card)
    return items


def fetch_bili(source):
    session = get_session()
    resp = session.get("https://s.search.bilibili.com/main/hotword", timeout=15)
    resp.raise_for_status()
    data = resp.json()
    items = []
    for entry in data.get("list", []):
        keyword = entry.get("keyword")
        if keyword:
            items.append(
                {
                    "title": keyword,
                    "url": f"https://search.bilibili.com/all?keyword={quote(keyword)}",
                    "raw_text": "",
                }
            )
    return items


def fetch_zhihu(source):
    session = get_session()
    resp = session.get("https://www.zhihu.com/api/v4/search/top_search", timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise ValueError(f"zhihu top_search rejected: {data['error']}")
    items = []
    for w in data.get("top_search", {}).get("words", []):
        query = w.get("display_query") or w.get("query")
        if query:
            items.append(
                {
                    "title": query,
                    "url": f"https://www.zhihu.com/search?type=content&q={quote(query)}",
                    "raw_text": "",
                }
            )
    return items
