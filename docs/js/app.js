import { renderFeed, excerptFor, relativeTime } from "./components/feed.js?v=20260724d";
import { renderBrief, renderHotStories, renderSourceHealth } from "./components/brief.js?v=20260724d";
import { initPalette } from "./components/palette.js?v=20260724d";
import { categoryColor, categoryTextColor } from "./palette.js?v=20260724d";
import { safeUrl, setSafeHref } from "./safe.js?v=20260724d";

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
  digestSection: document.getElementById("daily-digest"),
  digestBody: document.getElementById("digest-body"),
  leadLink: document.getElementById("lead-link"),
  leadOrig: document.getElementById("lead-orig"),
  leadReason: document.getElementById("lead-reason"),
  leadMeta: document.getElementById("lead-meta"),
  leadImg: document.getElementById("lead-img"),
  leadPlaceholder: document.getElementById("lead-placeholder"),
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
  const selectTab = (btn) => {
    [...els.viewTabs.children].forEach((c) => {
      const isActive = c === btn;
      c.classList.toggle("is-active", isActive);
      c.setAttribute("aria-selected", String(isActive));
      c.tabIndex = isActive ? 0 : -1;
    });
    state.view = btn.dataset.view;
    state.visibleCount = PAGE_SIZE;
    renderFeedSection();
  };
  // roving tabindex：初始时仅激活 tab 留在 Tab 顺序里，其余移出（tabindex=-1），
  // 这样 Tab 键一次跳过整组，组内改用方向键移动，匹配原生 tablist 行为
  [...els.viewTabs.children].forEach((c) => {
    c.tabIndex = c.classList.contains("is-active") ? 0 : -1;
  });
  els.viewTabs.addEventListener("click", (e) => {
    const btn = e.target.closest(".tab");
    if (!btn) return;
    selectTab(btn);
  });
  // ArrowLeft/Right（及 Home/End）在同组 tab 间移动焦点并直接激活，匹配原生 tablist 行为
  els.viewTabs.addEventListener("keydown", (e) => {
    const tabs = [...els.viewTabs.children];
    const currentIndex = tabs.indexOf(document.activeElement);
    if (currentIndex === -1) return;
    let newIndex;
    if (e.key === "ArrowRight") newIndex = (currentIndex + 1) % tabs.length;
    else if (e.key === "ArrowLeft") newIndex = (currentIndex - 1 + tabs.length) % tabs.length;
    else if (e.key === "Home") newIndex = 0;
    else if (e.key === "End") newIndex = tabs.length - 1;
    else return;
    e.preventDefault();
    const newTab = tabs[newIndex];
    newTab.focus();
    selectTab(newTab);
  });
}

function setupCategoryFilters() {
  els.categoryFilters.innerHTML = "";
  CATEGORIES.forEach((cat) => {
    const btn = document.createElement("button");
    btn.className = "chip";
    btn.type = "button";
    const dot = document.createElement("i");
    dot.className = "cat-dot";
    dot.style.background = categoryColor(cat);
    btn.append(dot, cat);
    // 激活态用各分类自己的颜色（下划线=数据色，文字=加深变体）
    btn.style.setProperty("--cat", categoryColor(cat));
    btn.style.setProperty("--cat-text", categoryTextColor(cat));
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

// 头版头条 = 当天最重要的新闻，不是最有深度的那篇。
// 这里曾直接取"今日简报"榜首；简报后来改成按 depth_score 排序的"今日深度推荐"，
// 头条的语义就跟着漂了——结果头条是一篇 arXiv 论文，而当天 15 家同时报道的
// GPT-5.6 发布反倒被埋进信息流。
// 重要性判据：先看几家独立信源同时报道（跨源确认是最强的重要性信号），再看加权分。
function pickHeadline(curated) {
  return curated
    .slice()
    .sort((a, b) =>
      (b.multi_source_count || 1) - (a.multi_source_count || 1) ||
      (b.weighted_score || 0) - (a.weighted_score || 0)
    )[0];
}

function renderDigest(digest) {
  const text = (digest && digest.summary || "").trim();
  if (!text) return;               // 冷清日或未生成：区块保持 hidden
  els.digestBody.textContent = text;
  els.digestSection.hidden = false;
}

function renderLead() {
  const lead = pickHeadline(state.curated);
  if (!lead) return;
  leadId = lead.id;

  // 英文原题为主标题（大），中文译文为副题行（小）
  els.leadLink.textContent = lead.title;
  els.leadLink.title = lead.title;   // 标题最多3行，被截断时可悬浮看全文
  setSafeHref(els.leadLink, lead.url);
  if (lead.title_zh && lead.title_zh.trim() !== lead.title.trim()) {
    els.leadOrig.textContent = lead.title_zh;
    els.leadOrig.hidden = false;
  }
  els.leadReason.textContent = excerptFor(lead, 420, true);
  const sources = lead.multi_source_count > 1 ? ` · ${lead.multi_source_count} 源确认` : "";
  els.leadMeta.innerHTML = `<span class="lead__cat"></span> · 加权分 ${lead.weighted_score?.toFixed(2) ?? "—"}${sources} · <time></time>`;
  els.leadMeta.querySelector("time").textContent = relativeTime(lead.published_at);
  els.leadMeta.querySelector("time").dateTime = lead.published_at;
  const leadCat = els.leadMeta.querySelector(".lead__cat");
  const catDot = document.createElement("i");
  catDot.className = "cat-dot";
  catDot.style.background = categoryColor(lead.category);
  leadCat.append(catDot, lead.category || "");
  leadCat.style.color = categoryTextColor(lead.category);

  // 配图：有 image_url 用原图；加载失败或超时(5s)回落到脉冲占位图
  const leadImageUrl = safeUrl(lead.image_url);
  if (leadImageUrl) {
    const fallback = () => {
      els.leadImg.hidden = true;
      els.leadPlaceholder.style.display = "";
    };
    const timer = setTimeout(() => {
      if (!(els.leadImg.complete && els.leadImg.naturalWidth > 0)) fallback();
    }, 5000);
    els.leadImg.addEventListener("load", () => clearTimeout(timer), { once: true });
    els.leadImg.addEventListener("error", () => { clearTimeout(timer); fallback(); }, { once: true });
    els.leadImg.src = leadImageUrl;
    els.leadImg.alt = lead.title || "";
    els.leadImg.hidden = false;
    els.leadPlaceholder.style.display = "none";
  }

  els.leadStory.hidden = false;
}

async function bootstrap() {
  setupTabs();
  setupCategoryFilters();
  setupFeedMore();

  const [curated, all, brief, stories, sourceStatus, trends, digest] = await Promise.all([
    fetchJson("./data/latest-24h.json", []),
    fetchJson("./data/latest-24h-all.json", []),
    fetchJson("./data/daily-brief.json", null),
    fetchJson("./data/stories-merged.json", []),
    fetchJson("./data/source-status.json", []),
    fetchJson("./data/trends.json", null),
    fetchJson("./data/daily-digest.json", null),
  ]);

  state.curated = curated;
  state.all = all;
  state.brief = brief;
  state.stories = stories;
  state.sourceStatus = sourceStatus;
  state.trends = trends;

  els.updatedAt.textContent = formatUpdatedAt(trends?.generated_at || brief?.generated_at);
  renderDateline();
  renderDigest(digest);
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
