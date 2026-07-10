// 频谱条：把 latest-24h-all.json 按"小时 x 分类"分桶，渲染成竖条频谱图（signature element）。
// 分类颜色使用经校验的共享色板；悬停有 tooltip 读数，键盘可操作。
import { categoryColor, CATEGORY_ORDER } from "../palette.js?v=20260710c";

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

function orderedEntries(bucket) {
  // 按固定分类顺序渲染分段，保证同一分类在所有柱子里的堆叠位置一致
  return CATEGORY_ORDER.filter((c) => bucket[c]).map((c) => [c, bucket[c]])
    .concat(Object.entries(bucket).filter(([c]) => !CATEGORY_ORDER.includes(c)));
}

export function renderSpectrum({ chartEl, legendEl, axisEl, emptyEl, tooltipEl, items, onSelectHour }) {
  const buckets = bucketItems(items);
  // √缩放：arXiv 等批量投放源会造成单小时尖峰，线性刻度下其他时段全被压扁；
  // 平方根缩放保留量级感又能看清低谷时段的结构，页面上有明确标注。
  const sqrtMax = Math.sqrt(
    Math.max(1, ...buckets.map((b) => Object.values(b).reduce((a, c) => a + c, 0)))
  );
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
    const bucketTotal = Object.values(bucket).reduce((a, c) => a + c, 0);
    group.setAttribute("aria-label", `${hoursAgo} 小时前，共 ${bucketTotal} 条`);

    const entries = orderedEntries(bucket);
    const groupHeightPct = bucketTotal ? (Math.sqrt(bucketTotal) / sqrtMax) * 100 : 0;
    entries.forEach(([cat, count]) => {
      const seg = document.createElement("div");
      seg.className = "spectrum__segment";
      // 柱子总高按√缩放，柱内各分类分段按原始占比切分
      const heightPct = groupHeightPct * (count / bucketTotal);
      seg.style.height = `${Math.max(heightPct, 2)}%`;
      seg.style.background = categoryColor(cat);
      seg.style.animationDelay = `${hourIdx * 12}ms`;
      group.appendChild(seg);
    });
    if (!entries.length) {
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

    if (tooltipEl) {
      group.addEventListener("mouseenter", () => {
        const lines = entries.map(([cat, count]) => `${cat} ${count}`).join(" · ");
        tooltipEl.textContent = `${hoursAgo}h 前 · 共 ${bucketTotal} 条${lines ? " — " + lines : ""}`;
        tooltipEl.hidden = false;
        const rect = group.getBoundingClientRect();
        const parentRect = chartEl.getBoundingClientRect();
        const left = rect.left - parentRect.left + rect.width / 2;
        tooltipEl.style.left = `${Math.min(Math.max(left, 90), parentRect.width - 90)}px`;
      });
      group.addEventListener("mouseleave", () => { tooltipEl.hidden = true; });
    }

    chartEl.appendChild(group);
  });

  legendEl.innerHTML = "";
  CATEGORY_ORDER.filter((c) => categoriesPresent.has(c)).forEach((cat) => {
    const li = document.createElement("li");
    li.innerHTML = `<span class="swatch" style="background:${categoryColor(cat)}"></span>${cat}`;
    legendEl.appendChild(li);
  });

  axisEl.innerHTML = "";
  ["24h 前", "12h 前", "现在"].forEach((label) => {
    const span = document.createElement("span");
    span.textContent = label;
    axisEl.appendChild(span);
  });
}
