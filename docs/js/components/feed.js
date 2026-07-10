// 信息流：AGI Hunt 式卡片 —— 顶行(分类+徽章) / 衬线标题 / 英文副题 / 配图 / 摘要 / 底行(来源+时间)。
import { categoryColor, categoryTextColor } from "../palette.js?v=20260710n";
import { safeUrl, setSafeHref } from "../safe.js?v=20260710n";

const SOURCE_LABELS = {
  "openai-blog": "OpenAI Blog",
  "anthropic-news": "Anthropic",
  "deepmind-blog": "Google DeepMind",
  "google-ai-blog": "Google AI Blog",
  "google-research-blog": "Google Research",
  "microsoft-research": "Microsoft Research",
  "aws-ml-blog": "AWS ML Blog",
  "huggingface-blog": "Hugging Face",
  "microsoft-ai-blog": "Microsoft AI",
  "nvidia-ai-blog": "NVIDIA AI",
  "github-changelog": "GitHub Changelog",
  "github-ai-blog": "GitHub Blog · AI",
  "apple-ml": "Apple ML Research",
  "amazon-science": "Amazon Science",
  "google-cloud-ai": "Google Cloud AI",
  "pytorch-blog": "PyTorch Blog",
  "bair-berkeley": "Berkeley BAIR",
  "mit-news-ai": "MIT News",
  "cmu-ml-blog": "CMU ML Blog",
  "eleuther": "EleutherAI",
  "the-gradient": "The Gradient",
  "karpathy": "Andrej Karpathy",
  "chiphuyen": "Chip Huyen",
  "simonwillison": "Simon Willison",
  "interconnects": "Interconnects",
  "oneusefulthing": "One Useful Thing",
  "lilianweng": "Lilian Weng",
  "fastai": "fast.ai",
  "answerai": "Answer.AI",
  "raschka": "Sebastian Raschka",
  "latent-space": "Latent Space",
  "import-ai": "Import AI",
  "semianalysis": "SemiAnalysis",
  "zvi": "The Zvi",
  "gary-marcus": "Gary Marcus",
  "techcrunch-ai": "TechCrunch",
  "verge-ai": "The Verge",
  "venturebeat-ai": "VentureBeat",
  "mit-tech-review-ai": "MIT Tech Review",
  "ars-technica-ai": "Ars Technica",
  "qbitai": "量子位",
  "infoq-cn-ai": "InfoQ 中文",
  "jiqizhixin": "机器之心",
  "ruanyifeng": "阮一峰的网络日志",
  "ifanr": "爱范儿",
  "36kr": "36氪",
  "baoyu": "宝玉",
  "hn-ai": "Hacker News",
  "hn-anthropic": "Hacker News",
  "hn-openai": "Hacker News",
  "hn-gemini": "Hacker News",
  "hn-openweights": "Hacker News",
  "qdrant-blog": "Qdrant Blog",
  "weaviate-blog": "Weaviate Blog",
  "together-blog": "Together AI",
};

function sourceLabel(id) {
  if (SOURCE_LABELS[id]) return SOURCE_LABELS[id];
  if (id.startsWith("gh-")) return `GitHub · ${id.slice(3)}`;
  if (id.startsWith("arxiv-")) return `arXiv ${id.slice(6).replace(/-/g, ".").toUpperCase()}`;
  if (id.startsWith("reddit-")) return `r/${id.slice(7)}`;
  return id;
}

function relativeTime(iso) {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return "刚刚";
  if (mins < 60) return `${mins} 分钟前`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs} 小时前`;
  const days = Math.round(hrs / 24);
  return `${days} 天前`;
}

const _parser = new DOMParser();

function stripHtml(html) {
  if (!html) return "";
  return _parser.parseFromString(html, "text/html").body.textContent?.replace(/\s+/g, " ").trim() || "";
}

// 摘要一律用中文：summary_zh 是 DeepSeek 在打分阶段生成的中文内容摘要(120-200字)。
// 英文原文只在条目未打分(打分批次失败，仅进入"全部动态")时兜底——此前头条无条件优先
// raw_text，导致英文源的头条摘要始终是英文原文。
// 头条(preferLong)要填满多行，优先更长的 summary_zh；卡片优先简洁的推荐理由 reason_zh。
function excerptFor(item, maxLen = 320, preferLong = false) {
  const summary = item.summary_zh || "";
  const reason = (item.reason_zh && !item.reason_zh.startsWith("[mock]")) ? item.reason_zh : "";

  for (const candidate of (preferLong ? [summary, reason] : [reason, summary])) {
    if (candidate) return candidate.slice(0, maxLen);
  }
  return stripHtml(item.raw_text).slice(0, maxLen);  // 未打分条目：无任何中文字段
}

function buildCardNode(item, idx, template) {
  const node = template.content.firstElementChild.cloneNode(true);
  node.dataset.curated = String(!!item.curated);
  node.style.animationDelay = `${Math.min(idx, 12) * 25}ms`;

  // 分类标签：数据色色点 + 同色系加深文字，与频谱/动量条的颜色一一对应
  const catEl = node.querySelector(".feed-card__category");
  const cat = item.category || "未分类";
  const dot = document.createElement("i");
  dot.className = "cat-dot";
  dot.style.background = categoryColor(cat);
  catEl.append(dot, cat);
  catEl.style.color = categoryTextColor(cat);

  const scoreEl = node.querySelector(".feed-card__score");
  scoreEl.textContent = item.weighted_score != null ? item.weighted_score.toFixed(2) : "";

  const outEl = node.querySelector(".feed-card__out");
  setSafeHref(outEl, item.url);

  // 标题层级：英文原题为主标题（大），中文译文为副题行（小）
  const titleEl = node.querySelector(".feed-card__title");
  titleEl.textContent = item.title;
  setSafeHref(titleEl, item.url);

  const deckEl = node.querySelector(".feed-card__deck");
  if (item.title_zh && item.title_zh.trim() !== item.title.trim()) {
    deckEl.textContent = item.title_zh;
    deckEl.hidden = false;
  }

  // 原文配图：加载失败直接收起，不留破图
  const imageUrl = safeUrl(item.image_url);
  if (imageUrl) {
    const media = node.querySelector(".feed-card__media");
    const img = node.querySelector(".feed-card__img");
    img.src = imageUrl;
    media.hidden = false;
    img.addEventListener("error", () => { media.hidden = true; }, { once: true });
  }

  node.querySelector(".feed-card__excerpt").textContent = excerptFor(item);

  node.querySelector(".feed-card__source").textContent = sourceLabel(item.source_id);
  const timeEl = node.querySelector(".feed-card__time");
  timeEl.textContent = relativeTime(item.published_at);
  timeEl.dateTime = item.published_at;

  // 多源确认徽章：×N，点击展开来源列表
  const count = item.multi_source_count || 1;
  const multiEl = node.querySelector(".feed-card__multi");
  const expandEl = node.querySelector(".feed-card__expand");
  if (count > 1) {
    multiEl.textContent = `×${count}`;
    multiEl.hidden = false;
    const sourceListEl = node.querySelector(".feed-card__source-list");
    (item.sources || []).forEach((s) => {
      const li = document.createElement("li");
      const a = document.createElement("a");
      setSafeHref(a, s.url);
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.textContent = sourceLabel(s.source_id);
      li.appendChild(a);
      sourceListEl.appendChild(li);
    });
    multiEl.addEventListener("click", () => { expandEl.hidden = !expandEl.hidden; });
  }

  return node;
}

// 卡片高度粗估：用于瀑布流按列分配，不需要精确，只需相对准确
function estimateCardHeight(item) {
  let h = 130; // 顶行 + 底行 + 内边距等固定开销
  const titleLen = (item.title || "").length;
  h += Math.max(1, Math.ceil(titleLen / 42)) * 34; // 标题行数
  if (item.title_zh && item.title_zh.trim() !== item.title.trim()) h += 26; // 副题行
  const excerptLen = excerptFor(item).length;
  h += Math.min(3, Math.max(1, Math.ceil(excerptLen / 55))) * 22; // 摘要最多3行截断
  if (item.image_url) h += 210; // 配图区块（92%宽×16:10 + 相框留白）
  return h;
}

export function renderFeed({ listEl, emptyEl, template, items }) {
  listEl.innerHTML = "";
  emptyEl.hidden = items.length > 0;
  if (!items.length) return;

  // 瀑布流双栏：贪心地把每条内容放进当前"预估高度更矮"的一栏，
  // 而不是强制左右逐行配对——左边没图的短卡可以连放两张，配右边一张带图的长卡。
  const isNarrow = window.matchMedia("(max-width: 800px)").matches;
  const colCount = isNarrow ? 1 : 2;
  const cols = Array.from({ length: colCount }, () => document.createElement("ol"));
  cols.forEach((col) => col.className = "feed-list__col");
  const colHeights = new Array(colCount).fill(0);

  items.forEach((item, idx) => {
    const node = buildCardNode(item, idx, template);
    const shortestCol = colHeights.indexOf(Math.min(...colHeights));
    cols[shortestCol].appendChild(node);
    colHeights[shortestCol] += estimateCardHeight(item);
  });

  cols.forEach((col) => listEl.appendChild(col));
}

export { sourceLabel, relativeTime, excerptFor };
