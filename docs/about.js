// 关于页交互：中英语言切换 + 明暗主题切换。纯前端、无依赖。
(function () {
  var root = document.documentElement;
  var langBtn = document.getElementById("langBtn");
  var themeBtn = document.getElementById("themeBtn");

  function isEnglish() {
    return root.classList.contains("lang-en");
  }

  function isDark() {
    var cur = root.getAttribute("data-theme");
    return cur ? cur === "dark"
      : window.matchMedia("(prefers-color-scheme: dark)").matches;
  }

  function syncLangAriaLabel() {
    langBtn.setAttribute("aria-label", isEnglish() ? "Switch to Chinese" : "切换到英文");
  }

  function syncThemeAriaLabel() {
    var en = isEnglish();
    var dark = isDark();
    themeBtn.setAttribute("aria-label",
      en ? (dark ? "Switch to light theme" : "Switch to dark theme")
         : (dark ? "切换到浅色主题" : "切换到深色主题"));
  }

  langBtn.addEventListener("click", function () {
    var en = root.classList.toggle("lang-en");
    langBtn.textContent = en ? "中" : "EN";
    root.lang = en ? "en" : "zh-CN";
    syncLangAriaLabel();
    syncThemeAriaLabel();
  });

  // 主题默认跟随系统，点击在 明/暗 间切换
  themeBtn.addEventListener("click", function () {
    var dark = isDark();
    root.setAttribute("data-theme", dark ? "light" : "dark");
    syncThemeAriaLabel();
  });

  syncLangAriaLabel();
  syncThemeAriaLabel();
})();
