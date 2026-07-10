// 今日简报 + 热点雷达：两个都是真正的排序榜单，编号是有意义的（不是装饰性 01/02/03）。
import { setSafeHref } from "../safe.js?v=20260710p";

// 侧栏窄，放不下双语两行：与社媒热点一致——译文为主，英文原题放 title 悬浮提示；
// 译文比原生中文标题醒目一档(is-translated)，帮助分辨"这是翻译过的"。
function setTitleWithTranslation(anchor, item) {
  if (item.title_zh && item.title_zh.trim() !== item.title.trim()) {
    anchor.textContent = item.title_zh;
    anchor.title = item.title;
    anchor.classList.add("is-translated");
  } else {
    anchor.textContent = item.title;
  }
}

export function renderBrief({ listEl, dateEl, emptyEl, brief }) {
  const items = (brief && brief.items) || [];
  emptyEl.hidden = items.length > 0;
  dateEl.textContent = brief ? brief.date : "";

  listEl.innerHTML = "";
  items.forEach((item, idx) => {
    const li = document.createElement("li");
    li.className = "brief-row" + (idx < 3 ? " is-top" : "");
    li.innerHTML = `
      <span class="brief-row__rank">${String(idx + 1).padStart(2, "0")}</span>
      <div class="brief-row__body">
        <a class="brief-row__title" target="_blank" rel="noopener noreferrer"></a>
        <p class="brief-row__reason"></p>
      </div>
    `;
    const a = li.querySelector(".brief-row__title");
    setTitleWithTranslation(a, item);
    setSafeHref(a, item.url);
    li.querySelector(".brief-row__reason").textContent = item.reason_zh || "";
    listEl.appendChild(li);
  });
}

export function renderHotStories({ listEl, emptyEl, stories }) {
  const top = (stories || []).slice(0, 10);
  emptyEl.hidden = top.length > 0;

  listEl.innerHTML = "";
  top.forEach((story, idx) => {
    const li = document.createElement("li");
    li.className = "hot-row" + (idx < 3 ? " is-top" : "");
    li.innerHTML = `
      <span class="hot-row__rank">${String(idx + 1).padStart(2, "0")}</span>
      <div class="hot-row__body">
        <a class="hot-row__title" target="_blank" rel="noopener noreferrer"></a>
        <p class="hot-row__meta">
          <span class="hot-row__sources"></span><span class="hot-row__heat"></span>
        </p>
      </div>
    `;
    const a = li.querySelector(".hot-row__title");
    setTitleWithTranslation(a, story);
    setSafeHref(a, story.url);
    li.querySelector(".hot-row__sources").textContent =
      story.source_count >= 2 ? `${story.source_count} 源确认` : "单源";
    li.querySelector(".hot-row__heat").textContent = ` · 热度 ${story.heat.toFixed(1)}`;
    listEl.appendChild(li);
  });
}

export function renderSourceHealth({ listEl, statuses }) {
  listEl.innerHTML = "";
  statuses
    .slice()
    .sort((a, b) => (a.last_error ? 1 : 0) - (b.last_error ? 1 : 0))
    .forEach((s) => {
      const li = document.createElement("li");
      li.className = "source-health__item";
      const ok = !s.last_error;
      // last_error 是第三方源返回的异常字符串，拼进 innerHTML 会被当成 HTML/属性解析
      // （引号可闭合 title="" 并注入事件处理器）——一律走 textContent / setAttribute
      li.innerHTML = `
        <span class="source-health__name"></span>
        <span class="status-dot ${ok ? "ok" : "err"}"></span>
      `;
      li.querySelector(".source-health__name").textContent = s.source_id;
      li.querySelector(".status-dot").setAttribute("title", ok ? "正常" : String(s.last_error));
      listEl.appendChild(li);
    });
}
