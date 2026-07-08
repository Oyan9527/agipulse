// 信息流：密集单列列表，每行含时间戳/多源确认圆点/分类标签/AI推荐理由。
const SOURCE_LABELS = {
  "openai-blog": "OpenAI Blog",
  "anthropic-news": "Anthropic",
  "deepmind-blog": "Google DeepMind",
  "google-ai-blog": "Google AI Blog",
  "huggingface-blog": "Hugging Face",
  "microsoft-ai-blog": "Microsoft AI",
  "nvidia-ai-blog": "NVIDIA AI",
  "github-changelog": "GitHub Changelog",
  "github-ai-blog": "GitHub Blog · AI",
  "hn-ai": "Hacker News",
  "reddit-machinelearning": "r/MachineLearning",
  "reddit-localllama": "r/LocalLLaMA",
  "reddit-singularity": "r/singularity",
  "reddit-openai": "r/OpenAI",
  "zhihu-hot": "知乎热榜",
};

function sourceLabel(id) {
  if (SOURCE_LABELS[id]) return SOURCE_LABELS[id];
  if (id.startsWith("gh-")) return `GitHub · ${id.slice(3)}`;
  if (id.startsWith("arxiv-")) return `arXiv ${id.slice(6).toUpperCase()}`;
  return id;
}

function relativeTime(iso) {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return "刚刚";
  if (mins < 60) return `${mins}分钟前`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}小时前`;
  const days = Math.round(hrs / 24);
  return `${days}天前`;
}

export function renderFeed({ listEl, emptyEl, template, items }) {
  listEl.innerHTML = "";
  emptyEl.hidden = items.length > 0;

  items.forEach((item, idx) => {
    const node = template.content.firstElementChild.cloneNode(true);
    node.dataset.curated = String(!!item.curated);
    node.style.animationDelay = `${Math.min(idx, 12) * 25}ms`;

    const time = node.querySelector(".feed-row__time");
    time.textContent = relativeTime(item.published_at);
    time.dateTime = item.published_at;

    const sourcesEl = node.querySelector(".feed-row__sources");
    const count = item.multi_source_count || 1;
    const dots = Math.min(count, 5);
    sourcesEl.innerHTML = "";
    for (let i = 0; i < dots; i++) {
      const dot = document.createElement("span");
      dot.className = "source-dot" + (i < count ? " is-lit" : "");
      sourcesEl.appendChild(dot);
    }
    sourcesEl.title = `${count} 个信源确认`;

    const catEl = node.querySelector(".feed-row__category");
    catEl.textContent = item.category || "未分类";

    const scoreEl = node.querySelector(".feed-row__score");
    if (item.weighted_score != null) {
      scoreEl.textContent = item.weighted_score.toFixed(2);
    } else {
      scoreEl.textContent = "";
    }

    const titleEl = node.querySelector(".feed-row__title");
    titleEl.textContent = item.title;
    titleEl.href = item.url;

    const reasonEl = node.querySelector(".feed-row__reason");
    reasonEl.textContent = item.reason_zh || "";

    const expandEl = node.querySelector(".feed-row__expand");
    const sourceListEl = node.querySelector(".feed-row__source-list");
    const sources = item.sources && item.sources.length ? item.sources : [{ source_id: item.source_id, url: item.url }];
    if (sources.length > 1) {
      sourceListEl.innerHTML = "";
      sources.forEach((s) => {
        const li = document.createElement("li");
        const a = document.createElement("a");
        a.href = s.url;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.textContent = sourceLabel(s.source_id);
        li.appendChild(a);
        sourceListEl.appendChild(li);
      });
      node.querySelector(".feed-row__body").addEventListener("click", (e) => {
        if (e.target.closest("a")) return;
        expandEl.hidden = !expandEl.hidden;
      });
    }

    listEl.appendChild(node);
  });
}

export { sourceLabel, relativeTime };
