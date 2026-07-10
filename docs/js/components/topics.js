// 话题追踪：每个热点话题一行——名称 + 迷你折线(sparkline) + 窗口内总提及 + 升降趋势。
// 数据来自 topics.json（按天聚合的提及次数曲线），纯展示。

const TREND_LABEL = { up: "↑ 升温", down: "↓ 降温", flat: "— 平稳" };

// 把一组数值画成 SVG sparkline。定宽 viewBox，points 归一化到 [0,1] 再映射。
function sparkline(series) {
  const w = 120, h = 28, pad = 2;
  const max = Math.max(1, ...series);
  const n = series.length;
  const pts = series.map((v, i) => {
    const x = n <= 1 ? w / 2 : pad + (i / (n - 1)) * (w - pad * 2);
    const y = h - pad - (v / max) * (h - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "topics__spark");
  svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
  svg.setAttribute("preserveAspectRatio", "none");

  const line = document.createElementNS(svg.namespaceURI, "polyline");
  line.setAttribute("points", pts.join(" "));
  line.setAttribute("fill", "none");
  line.setAttribute("stroke", "var(--accent)");
  line.setAttribute("stroke-width", "1.5");
  line.setAttribute("stroke-linejoin", "round");
  line.setAttribute("stroke-linecap", "round");
  svg.appendChild(line);

  // 末点加一个圆点，强调"当前"
  const last = pts[pts.length - 1]?.split(",");
  if (last) {
    const dot = document.createElementNS(svg.namespaceURI, "circle");
    dot.setAttribute("cx", last[0]);
    dot.setAttribute("cy", last[1]);
    dot.setAttribute("r", "1.8");
    dot.setAttribute("fill", "var(--accent)");
    svg.appendChild(dot);
  }
  return svg;
}

export function renderTopics({ sectionEl, listEl, windowEl, data }) {
  const topics = data?.topics || [];
  if (!topics.length) {
    sectionEl.hidden = true;   // 归档不足或无热点：整块收起
    return;
  }
  if (windowEl) windowEl.textContent = `近 ${data.window_days} 天热点话题的提及趋势`;

  listEl.innerHTML = "";
  topics.forEach((t) => {
    const li = document.createElement("li");
    li.className = "topics__row";

    const term = document.createElement("span");
    term.className = "topics__term";
    term.textContent = t.term;

    const spark = sparkline(t.series || []);
    spark.setAttribute("role", "img");
    spark.setAttribute("aria-label", `${t.term} 近 ${data.window_days} 天提及趋势`);

    const total = document.createElement("span");
    total.className = "topics__total";
    total.textContent = `${t.total} 次`;

    const trend = document.createElement("span");
    trend.className = `topics__trend topics__trend--${t.trend || "flat"}`;
    trend.textContent = TREND_LABEL[t.trend] || TREND_LABEL.flat;

    li.append(term, spark, total, trend);
    listEl.appendChild(li);
  });

  sectionEl.hidden = false;
}
