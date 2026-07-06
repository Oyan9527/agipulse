// 今日简报：真正的排序榜单，编号是有意义的（不是装饰性 01/02/03）。
export function renderBrief({ listEl, dateEl, emptyEl, brief }) {
  const items = (brief && brief.items) || [];
  emptyEl.hidden = items.length > 0;
  dateEl.textContent = brief ? brief.date : "";

  listEl.innerHTML = "";
  items.forEach((item, idx) => {
    const li = document.createElement("li");
    li.className = "brief-row";
    li.innerHTML = `
      <span class="brief-row__rank">${String(idx + 1).padStart(2, "0")}</span>
      <div class="brief-row__body">
        <a class="brief-row__title" target="_blank" rel="noopener noreferrer"></a>
        <p class="brief-row__reason"></p>
      </div>
    `;
    const a = li.querySelector(".brief-row__title");
    a.textContent = item.title;
    a.href = item.url;
    li.querySelector(".brief-row__reason").textContent = item.reason_zh || "";
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
      li.innerHTML = `
        <span class="source-health__name">${s.source_id}</span>
        <span class="status-dot ${ok ? "ok" : "err"}" title="${ok ? "正常" : s.last_error}"></span>
      `;
      listEl.appendChild(li);
    });
}
