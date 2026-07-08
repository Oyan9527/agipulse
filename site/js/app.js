import { renderSpectrum } from "./components/spectrum.js";
import { renderFeed } from "./components/feed.js";
import { renderBrief, renderHotStories, renderSourceHealth } from "./components/brief.js";
import { initPalette } from "./components/palette.js";
import { renderStats, renderCategoryMomentum, renderKeywords } from "./components/dashboard.js";

const CATEGORIES = ["模型发布", "产品发布", "开源项目", "行业动态", "论文研究", "技巧与观点"];
const LAST_SEEN_KEY = "signal-field-last-seen";
const PAGE_SIZE = 120;

const state = {
  curated: [],
  all: [],
  brief: null,
  stories: [],
  sourceStatus: [],
  trends: null,
  view: "curated",
  categoryFilter: null,
  hourFilter: null,
  visibleCount: PAGE_SIZE,
  trendDim: "day",
};

const els = {
  updatedAt: document.getElementById("updated-at"),
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
  viewTabs: document.getElementById("view-tabs"),
  categoryFilters: document.getElementById("category-filters"),
  feedList: document.getElementById("feed-list"),
  feedEmpty: document.getElementById("feed-empty"),
  feedMore: document.getElementById("feed-more"),
  feedRowTemplate: document.getElementById("feed-row-template"),
  hotList: document.getElementById("hot-list"),
  hotEmpty: document.getElementById("hot-empty"),
  briefList: document.getElementById("brief-list"),
  briefDate: document.getElementById("brief-date"),
  briefEmpty: document.getElementById("brief-empty"),
  sourceHealthList: document.getElementById("source-health-list"),
  themeToggle: document.getElementById("theme-toggle"),
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

function currentFeedItems() {
  let items = state.view === "curated" ? state.curated : state.all;
  if (state.categoryFilter) {
    items = items.filter((it) => it.category === state.categoryFilter);
  }
  if (state.hourFilter !== null) {
    items = items.filter((it) => {
      const ageHours = (Date.now() - new Date(it.published_at).getTime()) / 3600000;
      const bucketAge = 23 - state.hourFilter;
      return Math.floor(ageHours) === bucketAge;
    });
  }
  return items.slice().sort((a, b) => new Date(b.published_at) - new Date(a.published_at));
}

function renderFeedSection() {
  const items = currentFeedItems();
  const visible = items.slice(0, state.visibleCount);
  renderFeed({
    listEl: els.feedList,
    emptyEl: els.feedEmpty,
    template: els.feedRowTemplate,
    items: visible,
  });
  els.feedMore.hidden = items.length <= state.visibleCount;
  els.feedMore.textContent = `加载更多（还有 ${Math.max(items.length - state.visibleCount, 0)} 条）`;
}

function renderAll() {
  renderFeedSection();

  renderSpectrum({
    chartEl: els.spectrumChart,
    legendEl: els.spectrumLegend,
    axisEl: els.spectrumAxis,
    emptyEl: els.spectrumEmpty,
    tooltipEl: els.spectrumTooltip,
    items: state.all,
    onSelectHour: (hourIdx) => {
      state.hourFilter = state.hourFilter === hourIdx ? null : hourIdx;
      state.visibleCount = PAGE_SIZE;
      renderAll();
    },
  });
}

function setupTabs() {
  els.viewTabs.addEventListener("click", (e) => {
    const btn = e.target.closest(".tab");
    if (!btn) return;
    [...els.viewTabs.children].forEach((c) => {
      c.classList.toggle("is-active", c === btn);
      c.setAttribute("aria-selected", String(c === btn));
    });
    state.view = btn.dataset.view;
    state.visibleCount = PAGE_SIZE;
    renderFeedSection();
  });
}

function setupCategoryFilters() {
  els.categoryFilters.innerHTML = "";
  CATEGORIES.forEach((cat) => {
    const btn = document.createElement("button");
    btn.className = "chip";
    btn.type = "button";
    btn.textContent = cat;
    btn.addEventListener("click", () => {
      state.categoryFilter = state.categoryFilter === cat ? null : cat;
      state.visibleCount = PAGE_SIZE;
      [...els.categoryFilters.children].forEach((c) =>
        c.classList.toggle("is-active", c.textContent === state.categoryFilter)
      );
      renderFeedSection();
    });
    els.categoryFilters.appendChild(btn);
  });
}

function setupFeedMore() {
  els.feedMore.addEventListener("click", () => {
    state.visibleCount += PAGE_SIZE;
    renderFeedSection();
  });
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

function formatUpdatedAt(iso) {
  if (!iso) return "暂无数据";
  const d = new Date(iso);
  return `更新于 ${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
}

async function bootstrap() {
  setupTabs();
  setupCategoryFilters();
  setupFeedMore();
  setupTrendDimTabs();

  const [curated, all, brief, stories, sourceStatus, trends] = await Promise.all([
    fetchJson("./data/latest-24h.json", []),
    fetchJson("./data/latest-24h-all.json", []),
    fetchJson("./data/daily-brief.json", null),
    fetchJson("./data/stories-merged.json", []),
    fetchJson("./data/source-status.json", []),
    fetchJson("./data/trends.json", null),
  ]);

  state.curated = curated;
  state.all = all;
  state.brief = brief;
  state.stories = stories;
  state.sourceStatus = sourceStatus;
  state.trends = trends;

  els.updatedAt.textContent = formatUpdatedAt(trends?.generated_at || brief?.generated_at);

  renderAll();
  renderStats({
    el: els.statsRow,
    all24h: all,
    curated24h: curated,
    sourceStatus,
    stories,
  });
  renderTrendPanels();
  renderHotStories({ listEl: els.hotList, emptyEl: els.hotEmpty, stories: trends?.hot_stories || [] });
  renderBrief({ listEl: els.briefList, dateEl: els.briefDate, emptyEl: els.briefEmpty, brief });
  renderSourceHealth({ listEl: els.sourceHealthList, statuses: sourceStatus });

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

  const lastSeen = localStorage.getItem(LAST_SEEN_KEY);
  const freshStamp = trends?.generated_at || brief?.generated_at;
  if (freshStamp && (!lastSeen || new Date(freshStamp) > new Date(lastSeen))) {
    document.querySelector(".topbar__mark")?.classList.add("has-fresh");
  }
  if (freshStamp) localStorage.setItem(LAST_SEEN_KEY, freshStamp);
}

bootstrap();
