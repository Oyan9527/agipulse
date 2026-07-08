// 信息流：AGI Hunt 式卡片 —— 顶行(分类+徽章) / 衬线标题 / 英文副题 / 配图 / 摘要 / 底行(来源+时间)。
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

function excerptFor(item) {
  // 正式数据优先用 DeepSeek 中文推荐理由；mock 占位则回落到原文摘要
  const reason = item.reason_zh || "";
  if (reason && !reason.startsWith("[mock]")) return reason;
  const text = stripHtml(item.raw_text);
  if (text.length > 12) return text.slice(0, 160);
  return reason;
}

export function renderFeed({ listEl, emptyEl, template, items }) {
  listEl.innerHTML = "";
  emptyEl.hidden = items.length > 0;

  items.forEach((item, idx) => {
    const node = template.content.firstElementChild.cloneNode(true);
    node.dataset.curated = String(!!item.curated);
    node.style.animationDelay = `${Math.min(idx, 12) * 25}ms`;

    node.querySelector(".feed-card__category").textContent = item.category || "未分类";

    const scoreEl = node.querySelector(".feed-card__score");
    scoreEl.textContent = item.weighted_score != null ? item.weighted_score.toFixed(2) : "";

    const outEl = node.querySelector(".feed-card__out");
    outEl.href = item.url;

    // 报纸主题+副题结构：有译文时中文做主标题、英文原题做斜体副题行
    const titleEl = node.querySelector(".feed-card__title");
    titleEl.textContent = item.title_zh || item.title;
    titleEl.href = item.url;

    const deckEl = node.querySelector(".feed-card__deck");
    if (item.title_zh) {
      deckEl.textContent = item.title;
      deckEl.hidden = false;
    }

    // 原文配图：加载失败直接收起，不留破图
    if (item.image_url) {
      const media = node.querySelector(".feed-card__media");
      const img = node.querySelector(".feed-card__img");
      img.src = item.image_url;
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
        a.href = s.url;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.textContent = sourceLabel(s.source_id);
        li.appendChild(a);
        sourceListEl.appendChild(li);
      });
      multiEl.addEventListener("click", () => { expandEl.hidden = !expandEl.hidden; });
    }

    listEl.appendChild(node);
  });
}

export { sourceLabel, relativeTime };
