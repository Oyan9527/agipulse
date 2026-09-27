// 明暗主题：默认跟随系统，按钮在明/暗之间手动覆盖。
//
// 与关于页(about.js)是同一套机制、同一组色值——两页行为必须一致，否则从关于页
// 点回首页会"掉暗色"。同样不落盘：刷新后回到跟随系统，站点不写任何用户存储。
//
// 覆盖靠 <html data-theme>，CSS 那边 :root[data-theme=...] 的权重压过
// @media (prefers-color-scheme) 里的 :root:not([data-theme="light"])。
export function setupTheme(btn) {
  if (!btn) return;
  const root = document.documentElement;

  const isDark = () => {
    const cur = root.getAttribute("data-theme");
    return cur ? cur === "dark"
      : window.matchMedia("(prefers-color-scheme: dark)").matches;
  };

  const syncLabel = () => {
    btn.setAttribute("aria-label", isDark() ? "切换到浅色主题" : "切换到深色主题");
    btn.setAttribute("aria-pressed", String(isDark()));
  };

  btn.addEventListener("click", () => {
    root.setAttribute("data-theme", isDark() ? "light" : "dark");
    syncLabel();
  });

  // 没手动覆盖过时，系统主题变了要跟着变标签（配色本身由 CSS 媒体查询负责）
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (!root.getAttribute("data-theme")) syncLabel();
  });

  syncLabel();
}
