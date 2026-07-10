"""URL 安全校验的回归测试。

safe_http_url 是防 XSS 的第一道防线：条目的 url/image_url 完全由第三方 RSS 与 API 控制，
最终会被写进 <a href> 和 <img src>。这道防线被改坏了不会有任何症状——页面照常渲染，
直到某个源投毒才出事。所以它必须有测试守着。
"""
import pytest

from scripts.normalize import normalize_items
from scripts.util import safe_http_url


@pytest.mark.parametrize("url", [
    "https://example.com/a",
    "http://example.com",
    "https://example.com/path?q=1#frag",
    "  https://example.com/spaces  ",   # 两端空白应被容忍
])
def test_safe_urls_pass_through(url):
    assert safe_http_url(url) == url.strip()


@pytest.mark.parametrize("url", [
    "javascript:alert(1)",
    "JaVaScRiPt:alert(1)",              # 大小写绕过
    "  javascript:alert(1)",            # 前导空白绕过
    "data:text/html,<script>x</script>",
    "vbscript:msgbox",
    "file:///etc/passwd",
    "//evil.com",                       # 协议相对 URL：无 scheme
    "https://",                         # 无 netloc
    "",
    None,
    123,                                # 非字符串
])
def test_dangerous_urls_rejected(url):
    assert safe_http_url(url) is None


def test_normalize_drops_items_with_dangerous_url():
    raw = [
        {"title": "good", "url": "https://ok.com/1"},
        {"title": "evil", "url": "javascript:alert(1)"},
    ]
    out = normalize_items(raw, {"id": "s", "category_hint": []})
    assert [it["title"] for it in out] == ["good"]


def test_normalize_nulls_dangerous_image_url():
    raw = [{"title": "t", "url": "https://ok.com/1", "image_url": "javascript:alert(1)"}]
    out = normalize_items(raw, {"id": "s", "category_hint": []})
    assert out[0]["image_url"] is None


def test_normalize_keeps_safe_image_url():
    raw = [{"title": "t", "url": "https://ok.com/1", "image_url": "https://img.com/a.png"}]
    out = normalize_items(raw, {"id": "s", "category_hint": []})
    assert out[0]["image_url"] == "https://img.com/a.png"
