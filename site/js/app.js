import { renderSpectrum } from "./components/spectrum.js";
import { renderFeed } from "./components/feed.js";
import { renderBrief, renderSourceHealth } from "./components/brief.js";
import { initPalette } from "./components/palette.js";

const CATEGORIES = ["模型发布", "产品发布", "开源项目", "行业动态", "论文研究", "技巧与观点"];
const THEME_KEY = "signal-field-theme";
const LAST_SEEN_KEY = "signal-field-last-seen";

const state = {
  curated: [],
  all: [],
  brief: null,
  stories: [],
  sourceStatus: [],
  view: "curated",
  categoryFilter: null,
  hourFilter: null,
};

const els = {
  updatedAt: document.getElementById("updated-at"),
  spectrumChart: document.getElementById("spectrum-chart"),
  spectrumLegend: document.getElementById("spectrum-legend"),
  spectrumAxis: document.getElementById("spectrum-axis"),
  spectrumEmpty: document.getElementById("spectrum-empty"),
  viewTabs: document.getElementById("view-tabs"),
  categoryFilters: document.getElementById("category-filters"),
  feedList: document.getElementById("feed-list"),
  feedEmpty: document.getElementById("feed-empty"),
  feedRowTemplate: document.getElementById("feed-row-template"),
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

function renderAll() {
  renderFeed({
    listEl: els.feedList,
    emptyEl: els.feedEmpty,
    template: els.feedRowTemplate,
    items: currentFeedItems(),
  });

  renderSpectrum({
    chartEl: els.spectrumChart,
    legendEl: els.spectrumLegend,
    axisEl: els.spectrumAxis,
    emptyEl: els.spectrumEmpty,
    items: state.all,
    onSelectHour: (hourIdx) => {
      state.hourFilter = state.hourFilter === hourIdx ? null : hourIdx;
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
    renderAll();
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
      [...els.categoryFilters.children].forEach((c) =>
        c.classList.toggle("is-active", c.textContent === state.categoryFilter)
      );
      renderAll();
    });
    els.categoryFilters.appendChild(btn);
  });
}

function setupTheme() {
  const saved = localStorage.getItem(THEME_KEY);
  if (saved) document.documentElement.setAttribute("data-theme", saved);
  updateThemeLabel();

  els.themeToggle.addEventListener("click", () => {
    const next = document.documentElement.getAttribute("data-theme") === "light" ? "dark" : "light";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem(THEME_KEY, next);
    updateThemeLabel();
  });
}

function updateThemeLabel() {
  const isLight = document.documentElement.getAttribute("data-theme") === "light";
  els.themeToggle.querySelector(".theme-toggle__label").textContent = isLight ? "夜间读数" : "日间读数";
  els.themeToggle.setAttribute("aria-pressed", String(isLight));
}

function formatUpdatedAt(iso) {
  if (!iso) return "暂无数据";
  const d = new Date(iso);
  return `更新于 ${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
}

async function bootstrap() {
  setupTabs();
  setupCategoryFilters();
  setupTheme();

  const [curated, all, brief, stories, sourceStatus] = await Promise.all([
    fetchJson("./data/latest-24h.json", []),
    fetchJson("./data/latest-24h-all.json", []),
    fetchJson("./data/daily-brief.json", null),
    fetchJson("./data/stories-merged.json", []),
    fetchJson("./data/source-status.json", []),
  ]);

  state.curated = curated;
  state.all = all;
  state.brief = brief;
  state.stories = stories;
  state.sourceStatus = sourceStatus;

  els.updatedAt.textContent = formatUpdatedAt(brief?.generated_at);

  renderAll();
  renderBrief({ listEl: els.briefList, dateEl: els.briefDate, emptyEl: els.briefEmpty, brief });
  renderSourceHealth({ listEl: els.sourceHealthList, statuses: sourceStatus });

  initPalette({
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
  if (brief?.generated_at && (!lastSeen || new Date(brief.generated_at) > new Date(lastSeen))) {
    document.querySelector(".topbar__mark")?.classList.add("has-fresh");
  }
  if (brief?.generated_at) localStorage.setItem(LAST_SEEN_KEY, brief.generated_at);
}

bootstrap();
