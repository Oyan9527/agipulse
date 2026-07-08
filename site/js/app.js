import { renderFeed } from "./components/feed.js";
import { renderBrief, renderHotStories, renderSourceHealth } from "./components/brief.js";
import { initPalette } from "./components/palette.js";

const CATEGORIES = ["模型发布", "产品发布", "开源项目", "行业动态", "论文研究", "技巧与观点"];
const LAST_SEEN_KEY = "agi-pulse-last-seen";
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
  visibleCount: PAGE_SIZE,
};

const els = {
  updatedAt: document.getElementById("updated-at"),
  datelineDate: document.getElementById("dateline-date"),
  issueNo: document.getElementById("issue-no"),
  leadStory: document.getElementById("lead-story"),
  leadLink: document.getElementById("lead-link"),
  leadOrig: document.getElementById("lead-orig"),
  leadReason: document.getElementById("lead-reason"),
  leadMeta: document.getElementById("lead-meta"),
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

let leadId = null;

function currentFeedItems() {
  let items = state.view === "curated" ? state.curated : state.all;
  if (leadId) {
    items = items.filter((it) => it.id !== leadId); // 头条已在上方大字号展示，流内不重复
  }
  if (state.categoryFilter) {
    items = items.filter((it) => it.category === state.categoryFilter);
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

function formatUpdatedAt(iso) {
  if (!iso) return "暂无数据";
  const d = new Date(iso);
  return `更新于 ${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
}

function renderDateline() {
  const now = new Date();
  const weekdays = ["日", "一", "二", "三", "四", "五", "六"];
  els.datelineDate.textContent =
    `${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日 星期${weekdays[now.getDay()]}`;
}

function renderLead() {
  // 头条 = 今日简报榜首（分数最高的精选故事）
  const lead = state.brief?.items?.[0];
  if (!lead) return;
  leadId = lead.id;

  els.leadLink.textContent = lead.title_zh || lead.title;
  els.leadLink.href = lead.url;
  if (lead.title_zh) {
    els.leadOrig.textContent = lead.title;
    els.leadOrig.hidden = false;
  }
  els.leadReason.textContent = lead.reason_zh || "";
  const sources = lead.multi_source_count > 1 ? ` · ${lead.multi_source_count} 源确认` : "";
  els.leadMeta.innerHTML = `<span class="lead__cat"></span> · 加权分 ${lead.weighted_score?.toFixed(2) ?? "—"}${sources}`;
  els.leadMeta.querySelector(".lead__cat").textContent = lead.category || "";
  els.leadStory.hidden = false;
}

async function bootstrap() {
  setupTabs();
  setupCategoryFilters();
  setupFeedMore();

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
  renderDateline();
  els.issueNo.textContent = String(Math.max(trends?.archive_days ?? 1, 1));

  renderLead();
  renderFeedSection();
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
    document.querySelector(".pulse-dot")?.classList.add("has-fresh");
  }
  if (freshStamp) localStorage.setItem(LAST_SEEN_KEY, freshStamp);
}

bootstrap();
