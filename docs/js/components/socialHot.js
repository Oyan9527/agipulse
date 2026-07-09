// 社媒热点 + GitHub 涨星榜：独立于 AI 主流程，不做相关性过滤，纯展示各平台当前热搜。

const PERIOD_LABELS = {
  past_24_hours: "近24小时",
  past_week: "近7天",
  past_month: "近30天",
};

export function renderSocialHot({ gridEl, platforms }) {
  gridEl.innerHTML = "";
  const withItems = (platforms || []).filter((p) => p.items && p.items.length);

  if (!withItems.length) {
    const p = document.createElement("p");
    p.className = "social-hot__empty";
    p.textContent = "各平台暂时没有正热的 AI 话题。";
    gridEl.appendChild(p);
    return;
  }

  withItems.forEach((platform) => {
    const card = document.createElement("div");
    card.className = "social-hot__card";
    const title = document.createElement("h3");
    title.className = "social-hot__platform";
    title.textContent = platform.platform;
    card.appendChild(title);

    const list = document.createElement("ol");
    list.className = "social-hot__list";
    platform.items.slice(0, 8).forEach((item, idx) => {
      const li = document.createElement("li");
      li.className = "social-hot__item";
      const rank = document.createElement("span");
      rank.className = "social-hot__rank";
      rank.textContent = String(idx + 1).padStart(2, "0");
      const a = document.createElement("a");
      a.className = "social-hot__link";
      a.href = item.url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      // 英文标题优先显示中文译文（空间紧凑的单行列表放不下双语两行），英文原题放 title 悬浮提示
      if (item.title_zh && item.title_zh.trim() !== item.title.trim()) {
        a.textContent = item.title_zh;
        a.title = item.title;
      } else {
        a.textContent = item.title;
      }
      li.append(rank, a);
      list.appendChild(li);
    });
    card.appendChild(list);
    gridEl.appendChild(card);
  });
}

export function renderGithubTrending({ listEl, emptyEl, periodEl, data }) {
  const repos = (data && data.repos) || [];
  emptyEl.hidden = repos.length > 0;
  if (data && data.period) {
    periodEl.textContent = `${PERIOD_LABELS[data.period] || data.period}新增 star 最多的仓库`;
  }

  listEl.innerHTML = "";
  repos.forEach((repo, idx) => {
    const li = document.createElement("li");
    li.className = "gh-trending__row";
    li.innerHTML = `
      <span class="gh-trending__rank">${String(idx + 1).padStart(2, "0")}</span>
      <div class="gh-trending__body">
        <a class="gh-trending__repo" target="_blank" rel="noopener noreferrer"></a>
        <p class="gh-trending__desc"></p>
      </div>
      <div class="gh-trending__meta">
        <span class="gh-trending__stars"></span>
        <span class="gh-trending__lang"></span>
      </div>
    `;
    const a = li.querySelector(".gh-trending__repo");
    a.textContent = repo.repo;
    a.href = repo.url;
    li.querySelector(".gh-trending__desc").textContent = repo.description || "";
    li.querySelector(".gh-trending__stars").textContent = `★ +${repo.stars_gained}`;
    const langEl = li.querySelector(".gh-trending__lang");
    if (repo.language) langEl.textContent = repo.language;
    listEl.appendChild(li);
  });
}
