// 看板：统计指标瓦片 + 分类动量条 + 趋势关键词。
// 遵循 dataviz 规范：数值/标签用文字色而非系列色；细条形 + 圆角端点；每个色块旁必有文字标签。
import { categoryColor, CATEGORY_ORDER } from "../palette.js?v=20260715d";

function statTile({ value, label, hint }) {
  const div = document.createElement("div");
  div.className = "stat-tile";
  div.innerHTML = `
    <span class="stat-tile__value"></span>
    <span class="stat-tile__label"></span>
    <span class="stat-tile__hint"></span>
  `;
  div.querySelector(".stat-tile__value").textContent = value;
  div.querySelector(".stat-tile__label").textContent = label;
  div.querySelector(".stat-tile__hint").textContent = hint || "";
  return div;
}

export function renderStats({ el, all24h, curated24h, sourceStatus, stories }) {
  const okSources = sourceStatus.filter((s) => !s.last_error).length;
  const multiConfirmed = stories.filter((s) => s.source_count >= 2).length;
  const rate = all24h.length ? Math.round((curated24h.length / all24h.length) * 100) : 0;

  el.innerHTML = "";
  el.appendChild(statTile({ value: String(all24h.length), label: "24H 信号量", hint: "去重后全部条目" }));
  el.appendChild(statTile({ value: `${rate}%`, label: "精选率", hint: `${curated24h.length} 条越过门槛` }));
  el.appendChild(statTile({ value: `${okSources}/${sourceStatus.length}`, label: "活跃信源", hint: "本轮抓取成功" }));
  el.appendChild(statTile({ value: String(multiConfirmed), label: "多源确认", hint: "≥2 信源同报故事" }));
}

const DIM_LABELS = { day: "24小时", week: "7天", month: "30天" };

export function renderCategoryMomentum({ el, momentum, dim = "day" }) {
  el.innerHTML = "";
  if (!momentum.length) {
    const p = document.createElement("p");
    p.className = "trend-empty";
    p.textContent = "暂无分类动量数据";
    el.appendChild(p);
    return;
  }
  const max = Math.max(1, ...momentum.map((m) => m.count));

  momentum.forEach((m) => {
    const row = document.createElement("div");
    row.className = "momentum-row";
    const pct = Math.max((m.count / max) * 100, 2);
    const deltaText = m.delta > 0 ? `▲${m.delta}` : m.delta < 0 ? `▼${Math.abs(m.delta)}` : "—";
    row.innerHTML = `
      <span class="momentum-row__label"></span>
      <span class="momentum-row__track"><span class="momentum-row__bar"></span></span>
      <span class="momentum-row__count"></span>
      <span class="momentum-row__delta"></span>
    `;
    row.querySelector(".momentum-row__label").textContent = m.category;
    const bar = row.querySelector(".momentum-row__bar");
    bar.style.width = `${pct}%`;
    bar.style.background = categoryColor(m.category);
    row.querySelector(".momentum-row__count").textContent = String(m.count);
    const deltaEl = row.querySelector(".momentum-row__delta");
    deltaEl.textContent = deltaText;
    deltaEl.classList.toggle("is-up", m.delta > 0);
    deltaEl.classList.toggle("is-down", m.delta < 0);
    deltaEl.title = `环比前一个${DIM_LABELS[dim]} ${m.delta >= 0 ? "+" : ""}${m.delta}`;
    el.appendChild(row);
  });

  void CATEGORY_ORDER;
}

export function renderKeywords({ el, keywords, dim = "day", onSelect }) {
  el.innerHTML = "";
  if (!keywords.length) {
    const p = document.createElement("p");
    p.className = "trend-empty";
    p.textContent = `近${DIM_LABELS[dim]}没有形成聚集的关键词${dim !== "day" ? "（历史归档从部署当天开始积累）" : ""}。`;
    el.appendChild(p);
    return;
  }
  keywords.forEach((kw) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "trend-chip";
    const badge = kw.delta_pct === null
      ? `<span class="trend-chip__badge trend-chip__badge--new">新</span>`
      : kw.delta_pct > 0
        ? `<span class="trend-chip__badge">▲${kw.delta_pct}%</span>`
        : "";
    btn.innerHTML = `<span class="trend-chip__term"></span><span class="trend-chip__count"></span>${badge}`;
    btn.querySelector(".trend-chip__term").textContent = kw.term;
    btn.querySelector(".trend-chip__count").textContent = `×${kw.count}`;
    btn.title = `近${DIM_LABELS[dim]}被 ${kw.count} 条信号提及，点击搜索`;
    btn.addEventListener("click", () => onSelect(kw.term));
    el.appendChild(btn);
  });
}
