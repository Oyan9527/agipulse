// URL 安全兜底：条目的 url / image_url 来自第三方 RSS 与 API，会被写进 <a href> 和 <img src>。
// javascript: 链接一旦被点击就是 XSS。后端 normalize 已经过滤（见 scripts/util.py 的
// safe_http_url），这里是第二道防线——数据文件是静态 JSON，也可能被别的方式改动。

/** 只放行 http/https；其余（javascript:、data:、file: …）返回 null。 */
export function safeUrl(url) {
  if (typeof url !== "string" || !url.trim()) return null;
  let parsed;
  try {
    parsed = new URL(url, window.location.href);
  } catch {
    return null;  // 非法 URL
  }
  return (parsed.protocol === "http:" || parsed.protocol === "https:") ? parsed.href : null;
}

/** 给链接设置 href：不安全时干脆不设，链接自然不可点，而不是留一个能执行脚本的 href。 */
export function setSafeHref(anchor, url) {
  const href = safeUrl(url);
  if (href) {
    anchor.href = href;
  } else {
    anchor.removeAttribute("href");
  }
  return !!href;
}
