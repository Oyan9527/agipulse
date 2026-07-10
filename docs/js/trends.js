// 数据版页面脚本：24H 频谱 + 统计指标 + 日/周/月趋势看板 + 社媒热点 + GitHub 涨星榜。
import { renderSpectrum } from "./components/spectrum.js?v=20260710e";
import { renderStats, renderCategoryMomentum, renderKeywords } from "./components/dashboard.js?v=20260710e";
import { initPalette } from "./components/palette.js?v=20260710e";
import { renderSocialHot, renderGithubTrending } from "./components/socialHot.js?v=20260710e";

const state = {
  all: [],
  curated: [],
  trends: null,
  trendDim: "day",
  ghTrending: null,
  ghPeriod: "past_24_hours",
};

const els = {
  updatedAt: document.getElementById("updated-at"),
  datelineDate: document.getElementById("dateline-date"),
  issueNo: document.getElementById("issue-no"),
  spectrumChart: document.getElementById("spectrum-chart"),
  spectrumLegend: document.getElementById("spectrum-legend"),
  spectrumAxis: document.getElementById("spectrum-axis"),
  spectrumEmpty: document.getElementById("spectrum-empty"),
  spectrumTooltip: document.getElementById("spectrum-tooltip"),
  statsRow: document.getElementById("stats-row"),
  categoryMomentum: document.getElementById("category-momentum"),
  trendKeywords: document.getElementById("trend-keywords"),
  trendDimTabs: document.getElementById("trend-dim-tabs"),
  trendDimNote: document.getElementById("trend-dim-note"),
  momentumSub: document.getElementById("momentum-sub"),
  socialHotGrid: document.getElementById("social-hot-grid"),
  ghTrendingList: document.getElementById("gh-trending-list"),
  ghTrendingEmpty: document.getElementById("gh-trending-empty"),
  ghTrendingPeriod: document.getElementById("gh-trending-period"),
  ghPeriodTabs: document.getElementById("gh-period-tabs"),
  paletteOverlay: document.getElementById("command-palette"),
  paletteTrigger: document.getElementById("palette-trigger"),
  paletteInput: document.getElementById("palette-input"),
  paletteResults: document.getElementById("palette-results"),
};

let paletteApi = null;

async function fetchJson(path, fallback) {
  try {
    const res = await fetch(path, { cache: "no-store" });
    if (!res.ok) throw new Error(`${path}: ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn("data load failed", path, err);
    return fallback;
  }
}

const DIM_SUBS = {
  day: "近24h · 环比前24h",
  week: "近7天 · 环比前7天",
  month: "近30天 · 环比前30天",
};

function renderTrendPanels() {
  const dims = state.trends?.dimensions || {};
  const dim = dims[state.trendDim] || { keywords: [], category_momentum: [] };
  els.momentumSub.textContent = DIM_SUBS[state.trendDim];

  const archiveDays = state.trends?.archive_days ?? 0;
  els.trendDimNote.textContent =
    state.trendDim !== "day" && archiveDays < (state.trendDim === "week" ? 14 : 60)
      ? `归档已积累 ${archiveDays} 天，环比将随时间完整`
      : "";

  renderCategoryMomentum({ el: els.categoryMomentum, momentum: dim.category_momentum, dim: state.trendDim });
  renderKeywords({
    el: els.trendKeywords,
    keywords: dim.keywords,
    dim: state.trendDim,
    onSelect: (term) => {
      if (paletteApi) {
        paletteApi.open();
        els.paletteInput.value = term;
        els.paletteInput.dispatchEvent(new Event("input"));
      }
    },
  });
}

function setupTrendDimTabs() {
  els.trendDimTabs.addEventListener("click", (e) => {
    const btn = e.target.closest(".tab");
    if (!btn) return;
    [...els.trendDimTabs.children].forEach((c) => {
      c.classList.toggle("is-active", c === btn);
      c.setAttribute("aria-selected", String(c === btn));
    });
    state.trendDim = btn.dataset.dim;
    renderTrendPanels();
  });
}

function renderGhTrending() {
  renderGithubTrending({
    listEl: els.ghTrendingList,
    emptyEl: els.ghTrendingEmpty,
    periodEl: els.ghTrendingPeriod,
    data: state.ghTrending,
    period: state.ghPeriod,
  });
}

function setupGhPeriodTabs() {
  els.ghPeriodTabs.addEventListener("click", (e) => {
    const btn = e.target.closest(".tab");
    if (!btn) return;
    [...els.ghPeriodTabs.children].forEach((c) => {
      c.classList.toggle("is-active", c === btn);
      c.setAttribute("aria-selected", String(c === btn));
    });
    state.ghPeriod = btn.dataset.period;
    renderGhTrending();
  });
}

function renderDateline() {
  const now = new Date();
  const weekdays = ["日", "一", "二", "三", "四", "五", "六"];
  els.datelineDate.textContent =
    `${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日 星期${weekdays[now.getDay()]}`;
}

function formatUpdatedAt(iso) {
  if (!iso) return "暂无数据";
  const d = new Date(iso);
  return `更新于 ${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
}

async function bootstrap() {
  setupTrendDimTabs();
  setupGhPeriodTabs();

  const [all, curated, stories, sourceStatus, trends, socialHot, ghTrending] = await Promise.all([
    fetchJson("./data/latest-24h-all.json", []),
    fetchJson("./data/latest-24h.json", []),
    fetchJson("./data/stories-merged.json", []),
    fetchJson("./data/source-status.json", []),
    fetchJson("./data/trends.json", null),
    fetchJson("./data/social-hot.json", null),
    fetchJson("./data/github-trending.json", null),
  ]);

  state.all = all;
  state.curated = curated;
  state.trends = trends;
  state.ghTrending = ghTrending;

  renderDateline();
  els.updatedAt.textContent = formatUpdatedAt(trends?.generated_at);
  els.issueNo.textContent = String(Math.max(trends?.archive_days ?? 1, 1));

  renderSpectrum({
    chartEl: els.spectrumChart,
    legendEl: els.spectrumLegend,
    axisEl: els.spectrumAxis,
    emptyEl: els.spectrumEmpty,
    tooltipEl: els.spectrumTooltip,
    items: all,
    onSelectHour: () => {},  // 数据版没有信息流可筛选，点击不做动作
  });

  renderStats({ el: els.statsRow, all24h: all, curated24h: curated, sourceStatus, stories });
  renderTrendPanels();

  renderSocialHot({ gridEl: els.socialHotGrid, platforms: socialHot?.platforms });
  renderGhTrending();

  paletteApi = initPalette({
    overlayEl: els.paletteOverlay,
    triggerEl: els.paletteTrigger,
    inputEl: els.paletteInput,
    resultsEl: els.paletteResults,
    getSearchIndex: () => {
      const seen = new Set();
      return [...state.all, ...state.curated].filter((it) => {
        if (seen.has(it.id)) return false;
        seen.add(it.id);
        return true;
      });
    },
  });
}

bootstrap();
