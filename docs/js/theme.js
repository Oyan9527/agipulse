// 明暗主题：默认恒为浅色，按钮切到深色。
//
// 刻意不跟随系统的 prefers-color-scheme——这是一份报纸纸面配色，浅色是它的本来
// 面目，系统开着深色的人打开本站也该先看到纸面。深色是可选项，点 ◐ 才有。
//
// 与关于页(about.js)是同一套机制、同一组色值，两页行为保持一致。
// 同样不落盘：刷新后回到浅色，站点不写任何用户存储。
export function setupTheme(btn) {
  if (!btn) return;
  const root = document.documentElement;

  const isDark = () => root.getAttribute("data-theme") === "dark";

  const syncLabel = () => {
    btn.setAttribute("aria-label", isDark() ? "切换到浅色主题" : "切换到深色主题");
    btn.setAttribute("aria-pressed", String(isDark()));
  };

  btn.addEventListener("click", () => {
    root.setAttribute("data-theme", isDark() ? "light" : "dark");
    syncLabel();
  });

  syncLabel();
}
