// 关于页交互：中英语言切换 + 明暗主题切换。纯前端、无依赖。
(function () {
  var root = document.documentElement;
  var langBtn = document.getElementById("langBtn");
  var themeBtn = document.getElementById("themeBtn");

  langBtn.addEventListener("click", function () {
    var en = root.classList.toggle("lang-en");
    langBtn.textContent = en ? "中" : "EN";
    root.lang = en ? "en" : "zh-CN";
  });

  // 主题默认跟随系统，点击在 明/暗 间切换
  themeBtn.addEventListener("click", function () {
    var cur = root.getAttribute("data-theme");
    var isDark = cur ? cur === "dark"
      : window.matchMedia("(prefers-color-scheme: dark)").matches;
    root.setAttribute("data-theme", isDark ? "light" : "dark");
  });
})();
