// 命令面板：Ctrl/Cmd+K 打开，模糊搜索已加载的全部条目。
import { safeUrl } from "../safe.js?v=20260715d";
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
      inputEl.removeAttribute("aria-activedescendant");
      return;
    }
    items.forEach((item, idx) => {
      const li = document.createElement("li");
      const isActive = idx === activeIndex;
      li.id = `palette-result-${idx}`;
      li.className = "palette__result" + (isActive ? " is-active" : "");
      li.setAttribute("role", "option");
      li.setAttribute("aria-selected", String(isActive));
      li.innerHTML = `
        <span class="palette__result-title"></span>
        <span class="palette__result-meta"></span>
      `;
      li.querySelector(".palette__result-title").textContent = item.title;
      li.querySelector(".palette__result-meta").textContent = `${item.source_id} · ${item.category || ""}`;
      const url = safeUrl(item.url);
      if (url) li.addEventListener("click", () => window.open(url, "_blank", "noopener,noreferrer"));
      resultsEl.appendChild(li);
    });
    syncActiveDescendant();
  }

  // 把当前高亮项同步给屏幕阅读器：aria-activedescendant 指向高亮 option 的 id
  function syncActiveDescendant() {
    if (activeIndex === -1) {
      inputEl.removeAttribute("aria-activedescendant");
    } else {
      inputEl.setAttribute("aria-activedescendant", `palette-result-${activeIndex}`);
    }
  }

  function updateActive(delta) {
    if (!currentResults.length) return;
    activeIndex = (activeIndex + delta + currentResults.length) % currentResults.length;
    [...resultsEl.children].forEach((el, i) => {
      const isActive = i === activeIndex;
      el.classList.toggle("is-active", isActive);
      el.setAttribute("aria-selected", String(isActive));
    });
    resultsEl.children[activeIndex]?.scrollIntoView({ block: "nearest" });
    syncActiveDescendant();
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

  function getFocusable() {
    return [...overlayEl.querySelectorAll('a[href], button, input, textarea, select, [tabindex]:not([tabindex="-1"])')]
      .filter((el) => !el.disabled);
  }

  overlayEl.addEventListener("keydown", (e) => {
    if (e.key === "Escape") close();
    if (e.key === "ArrowDown") { e.preventDefault(); updateActive(1); }
    if (e.key === "ArrowUp") { e.preventDefault(); updateActive(-1); }
    if (e.key === "Enter" && currentResults[activeIndex]) {
      const url = safeUrl(currentResults[activeIndex].url);
      if (url) window.open(url, "_blank", "noopener,noreferrer");
    }
    if (e.key === "Tab") {
      const focusable = getFocusable();
      if (!focusable.length) { e.preventDefault(); return; }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey) {
        if (document.activeElement === first || !overlayEl.contains(document.activeElement)) {
          e.preventDefault();
          last.focus();
        }
      } else if (document.activeElement === last || !overlayEl.contains(document.activeElement)) {
        e.preventDefault();
        first.focus();
      }
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
