// 命令面板：Ctrl/Cmd+K 打开，模糊搜索已加载的全部条目。
export function initPalette({ overlayEl, triggerEl, inputEl, resultsEl, getSearchIndex }) {
  let activeIndex = -1;
  let currentResults = [];

  function open() {
    overlayEl.hidden = false;
    inputEl.value = "";
    inputEl.focus();
    renderResults(getSearchIndex().slice(0, 8));
  }

  function close() {
    overlayEl.hidden = true;
    triggerEl.focus();
  }

  function renderResults(items) {
    currentResults = items;
    activeIndex = items.length ? 0 : -1;
    resultsEl.innerHTML = "";
    if (!items.length) {
      resultsEl.innerHTML = `<li class="palette__empty">没有匹配的结果</li>`;
      return;
    }
    items.forEach((item, idx) => {
      const li = document.createElement("li");
      li.className = "palette__result" + (idx === activeIndex ? " is-active" : "");
      li.innerHTML = `
        <span class="palette__result-title"></span>
        <span class="palette__result-meta"></span>
      `;
      li.querySelector(".palette__result-title").textContent = item.title;
      li.querySelector(".palette__result-meta").textContent = `${item.source_id} · ${item.category || ""}`;
      li.addEventListener("click", () => window.open(item.url, "_blank", "noopener,noreferrer"));
      resultsEl.appendChild(li);
    });
  }

  function updateActive(delta) {
    if (!currentResults.length) return;
    activeIndex = (activeIndex + delta + currentResults.length) % currentResults.length;
    [...resultsEl.children].forEach((el, i) => el.classList.toggle("is-active", i === activeIndex));
    resultsEl.children[activeIndex]?.scrollIntoView({ block: "nearest" });
  }

  inputEl.addEventListener("input", () => {
    const q = inputEl.value.trim().toLowerCase();
    if (!q) {
      renderResults(getSearchIndex().slice(0, 8));
      return;
    }
    const matches = getSearchIndex()
      .filter((it) =>
        it.title.toLowerCase().includes(q) ||
        it.source_id.toLowerCase().includes(q) ||
        (it.category || "").toLowerCase().includes(q)
      )
      .slice(0, 20);
    renderResults(matches);
  });

  overlayEl.addEventListener("keydown", (e) => {
    if (e.key === "Escape") close();
    if (e.key === "ArrowDown") { e.preventDefault(); updateActive(1); }
    if (e.key === "ArrowUp") { e.preventDefault(); updateActive(-1); }
    if (e.key === "Enter" && currentResults[activeIndex]) {
      window.open(currentResults[activeIndex].url, "_blank", "noopener,noreferrer");
    }
  });

  overlayEl.addEventListener("click", (e) => {
    if (e.target === overlayEl) close();
  });

  triggerEl.addEventListener("click", open);

  document.addEventListener("keydown", (e) => {
    const isMod = e.metaKey || e.ctrlKey;
    if (isMod && e.key.toLowerCase() === "k") {
      e.preventDefault();
      overlayEl.hidden ? open() : close();
    }
  });

  return { open, close };
}
