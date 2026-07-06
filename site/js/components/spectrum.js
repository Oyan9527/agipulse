// 频谱条：把 latest-24h-all.json 按"小时 x 分类"分桶，渲染成竖条频谱图（signature element）。
const CATEGORY_COLORS = {
  "模型发布": "var(--amber)",
  "产品发布": "var(--cyan)",
  "开源项目": "#7dd3a8",
  "行业动态": "#c99bf0",
  "论文研究": "#f0a6c9",
  "技巧与观点": "#8b93a7",
};
const FALLBACK_COLOR = "#4a5468";
const BUCKET_HOURS = 24;

function bucketItems(items) {
  const now = Date.now();
  const buckets = Array.from({ length: BUCKET_HOURS }, () => ({}));
  for (const item of items) {
    const t = new Date(item.published_at).getTime();
    const ageHours = (now - t) / 3600000;
    if (ageHours < 0 || ageHours >= BUCKET_HOURS) continue;
    const idx = BUCKET_HOURS - 1 - Math.floor(ageHours);
    const cat = item.category || "行业动态";
    buckets[idx][cat] = (buckets[idx][cat] || 0) + 1;
  }
  return buckets;
}

export function renderSpectrum({ chartEl, legendEl, axisEl, emptyEl, items, onSelectHour }) {
  const buckets = bucketItems(items);
  const maxTotal = Math.max(1, ...buckets.map((b) => Object.values(b).reduce((a, c) => a + c, 0)));
  const total = buckets.reduce((sum, b) => sum + Object.values(b).reduce((a, c) => a + c, 0), 0);

  emptyEl.hidden = total > 0;
  chartEl.querySelectorAll(".spectrum__bar-group").forEach((el) => el.remove());

  const categoriesPresent = new Set();
  buckets.forEach((b) => Object.keys(b).forEach((c) => categoriesPresent.add(c)));

  buckets.forEach((bucket, hourIdx) => {
    const group = document.createElement("div");
    group.className = "spectrum__bar-group";
    group.dataset.hourIdx = String(hourIdx);
    group.setAttribute("tabindex", "0");
    group.setAttribute("role", "button");
    const hoursAgo = BUCKET_HOURS - 1 - hourIdx;
    group.setAttribute("aria-label", `${hoursAgo} 小时前，共 ${Object.values(bucket).reduce((a, c) => a + c, 0)} 条`);

    Object.entries(bucket).forEach(([cat, count], i) => {
      const seg = document.createElement("div");
      seg.className = "spectrum__segment";
      const heightPct = (count / maxTotal) * 100;
      seg.style.height = `${Math.max(heightPct, 2)}%`;
      seg.style.background = CATEGORY_COLORS[cat] || FALLBACK_COLOR;
      seg.style.animationDelay = `${hourIdx * 12}ms`;
      group.appendChild(seg);
    });
    if (Object.keys(bucket).length === 0) {
      const seg = document.createElement("div");
      seg.className = "spectrum__segment";
      seg.style.height = "2%";
      seg.style.background = "var(--line)";
      seg.style.animationDelay = `${hourIdx * 12}ms`;
      group.appendChild(seg);
    }

    group.addEventListener("click", () => onSelectHour(hourIdx));
    group.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        onSelectHour(hourIdx);
      }
    });

    chartEl.appendChild(group);
  });

  legendEl.innerHTML = "";
  [...categoriesPresent].forEach((cat) => {
    const li = document.createElement("li");
    li.innerHTML = `<span class="swatch" style="background:${CATEGORY_COLORS[cat] || FALLBACK_COLOR}"></span>${cat}`;
    legendEl.appendChild(li);
  });

  axisEl.innerHTML = "";
  ["24h 前", "12h 前", "现在"].forEach((label) => {
    const span = document.createElement("span");
    span.textContent = label;
    axisEl.appendChild(span);
  });
}
