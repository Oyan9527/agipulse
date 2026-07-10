"""给前端静态资源(css/js)的引用统一打上版本串，做 cache busting。

为什么需要：页面结构与样式/脚本是强耦合的——浏览器或 GitHub Pages CDN 若拿到
新 HTML 配旧 CSS，头条栅格定位丢失、图文版式会直接崩坏；配旧 JS 则摘要退回英文原文。
给每个引用加 ?v=<版本> 后，改动版本即改变 URL，浏览器必然重新下载。

ES module 的静态 import 只接受字面量路径，无法在运行时拼版本号，
所以 import 语句里的路径也要一并改写——手改 13 处太容易漏，用本脚本统一处理。

用法（改动 docs/css 或 docs/js 后执行）：
    python -m scripts.bump_assets_version            # 用当天日期+序号自动生成新版本
    python -m scripts.bump_assets_version --version 20260711a
可重复运行：已有的 ?v=... 会被替换成新版本，不会叠加。
"""
import argparse
import re
from datetime import date
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"

# (文件glob, 匹配资源引用的正则)。每个正则必须有 named group `path` 指向不带query的资源路径。
PATTERNS = [
    (["*.html"], re.compile(r'(?P<pre>href=")(?P<path>css/[\w./-]+\.css)(?:\?v=[\w.-]+)?(?P<post>")')),
    (["*.html"], re.compile(r'(?P<pre>src=")(?P<path>js/[\w./-]+\.js)(?:\?v=[\w.-]+)?(?P<post>")')),
    (["js/*.js", "js/components/*.js"],
     re.compile(r'(?P<pre>from ")(?P<path>\.{1,2}/[\w./-]+\.js)(?:\?v=[\w.-]+)?(?P<post>")')),
]


def next_version(today=None):
    """同一天多次发布用后缀字母递增：20260710a -> 20260710b。"""
    stamp = (today or date.today()).strftime("%Y%m%d")
    existing = set()
    for path in DOCS.rglob("*"):
        if path.suffix in (".html", ".js") and path.is_file():
            existing.update(re.findall(rf"\?v=({stamp}[a-z]?)", path.read_text(encoding="utf-8")))
    suffixes = [v[len(stamp):] for v in existing if v.startswith(stamp)]
    if not suffixes:
        return f"{stamp}a"
    last = max(s for s in suffixes if s) or "a"
    return f"{stamp}{chr(ord(last[0]) + 1)}"


def bump(version):
    changed = []
    for globs, pattern in PATTERNS:
        for glob in globs:
            for path in sorted(DOCS.glob(glob)):
                src = path.read_text(encoding="utf-8")
                new = pattern.sub(rf"\g<pre>\g<path>?v={version}\g<post>", src)
                if new != src:
                    path.write_text(new, encoding="utf-8", newline="")
                    changed.append(path.relative_to(DOCS))
    return changed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", help="显式指定版本串，默认按当天日期自动生成")
    args = parser.parse_args()

    version = args.version or next_version()
    changed = bump(version)
    print(f"assets version -> {version}")
    for path in dict.fromkeys(changed):
        print(f"  updated {path}")
    if not changed:
        print("  (no references found)")


if __name__ == "__main__":
    main()
