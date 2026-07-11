# 硅基脉动 · AGI Pulse

> 每 4 小时侦测硅基世界的脉搏 —— 一个零后端、自动运行的 AI 行业信息聚合站。
>
> 🌐 站点：<https://oyan9527.github.io/agipulse/> ｜ 📡 RSS：<https://oyan9527.github.io/agipulse/feed.xml> ｜ ℹ️ 关于：<https://oyan9527.github.io/agipulse/about.html>

*(English version below · 英文版见下方)*

---

## 这是什么

AI 行业每天产生的信息量远超任何人的阅读能力：官方博客、论文、开源发布、科技媒体、社区讨论散落在数百个渠道，重要的事被淹没在噪声里。

**硅基脉动**把 **300+ 信息源**聚合到一处，用 AI 完成筛选、打分、去重与摘要，只把真正重要的 AI 动态呈现给你——像一份每天自动编排、自动出版的 AI 行业日报。

它完全自动运行、无需人工干预，且**不收集任何用户数据**。

---

## 核心特点

### 📰 头版 —— 一眼看清今天最重要的事

- **今日综述**：由 AI 根据当天头部故事生成的一段中文导读，先点出最重磅的一两件事，再带过其余值得关注的方向。
- **头条**：当天最重要的新闻——以「多家独立信源同时报道」为首要信号，而非单纯的热度。
- **精选信息流**：越过质量门槛的内容，双栏瀑布流卡片，可按 6 大分类筛选（模型发布 / 产品发布 / 开源项目 / 行业动态 / 论文研究 / 技巧与观点）。
- **今日深度推荐**：由 AI 判定「读完能获得可迁移认知」的深度内容——可解释性研究、提出新方法的论文、工程师复盘真实系统的实践总结——而非资讯快讯。
- **热点雷达**：按多源确认数 × 新鲜度排序的当日热点故事。

### 📊 数据版 —— 用数据看趋势

- **24 小时信号频谱**：按小时 × 分类统计信息密度，一眼看出全天节奏与热点时段。
- **趋势看板**：日 / 周 / 月三档的分类动量与关键词热度，含环比升降。
- **话题追踪**：热点话题（模型名、公司名等）近 14 天的提及曲线，标注升温 / 降温 / 平稳。
- **社媒 AI 热点**：B站、Hacker News、Reddit、微博、知乎、X 上正热的 AI 话题（经关键词过滤，只留 AI 相关）。
- **GitHub 涨星榜**：日 / 周 / 月 / 年 / 总榜五档，涨星最快与总星最多的仓库。

### 🌏 面向中文读者

- 英文标题与正文由 AI 翻译成中文（保留模型名 / 公司名等专有名词原文）。
- 每条内容配一段 AI 生成的中文摘要。

### 🔗 多源合并，不重复

同一事件被多家报道时（如「GPT-5.6 发布」当天有 15 家同时报道），自动合并成一张卡片并标注「N 源确认」，点开可见全部来源——既确认了重要性，又不刷屏。

### 📡 开放订阅

提供标准 Atom / RSS 订阅源，任何阅读器都能订阅精选流。

---

## 技术架构

### 零后端设计

整站没有服务器、没有数据库。运行链路极简：

```
GitHub Actions（每 4 小时定时）
   └─ 运行 Python 流水线
        └─ 生成静态 JSON 数据文件
             └─ 提交回仓库
                  └─ GitHub Pages 直接托管，前端读取渲染
```

这带来三个直接好处：**几乎零成本运行**（仅 DeepSeek API 按量计费，日均几毛钱人民币）、**无需运维**、**零用户数据**——没有账号系统、不存邮箱、不接第三方追踪脚本，天然规避了隐私与数据安全负担。

### 数据处理流水线（Python）

每轮运行依次完成：

1. **抓取**：并发拉取 300+ 信源（RSS / arXiv / GitHub / Hacker News / Reddit / 微博 / 知乎 / X 等），单源失败自动降级，不影响整体。
2. **归一化 + 去重**：统一数据结构，模糊标题匹配剔除重复。
3. **AI 相关性过滤**：只对综合科技站与个人博客做严格关键词过滤，官方 AI 博客 / arXiv 等天然 AI 源直接放行，避免误杀。
4. **两级 LLM 处理（DeepSeek）**：先低成本粗筛剔除噪声，再对留存内容做四维度打分——**信息权威度 30% + 新颖度 25% + 影响力 25% + 实用价值 20%**——并生成分类、中文摘要、深度评分与译题。
5. **故事合并**：36 小时窗口内，用词袋相似度 + 模型/产品标识（如 GPT-5.6）双判据，把同一事件的跨源报道聚成一条。
6. **质量门控**：多源确认数 ≥ 2 **或** 加权分 ≥ 0.72 才进入精选流；冷清日不硬凑内容。
7. **产出**：写出信息流、深度推荐、每日综述、话题曲线、趋势、RSS 等静态文件。

### 前端

原生 ES modules，无框架、无构建步骤。信号频谱、话题曲线均为纯 SVG 实时渲染。桌面 / 移动端自适应。设计取「青瓷 · 电路」主题 + 报纸头版式版面，克制而不浮夸。

### 成本控制

**结果缓存**是降本关键：处理窗口 48 小时内，同一条内容会被重复抓取多次；缓存把每条内容的判定结果按 id 持久化，命中过的直接复用、不再调用 DeepSeek，只有首次出现的新内容才真正计费。

### 工程质量

- **自动化测试 + CI**：77 项测试覆盖过滤、合并、安全校验、话题聚合等核心逻辑；每次提交与每轮抓取前自动运行，坏逻辑无法把脏数据写进站点。
- **静默失效告警**：大批信源失效或 AI 打分中断时，自动让任务标红并邮件告警——数据仍照常保留，只是提醒你介入。
- **安全加固**：内容安全策略（CSP）+ URL 协议白名单 + 全程输出转义，防御来自第三方信源的注入攻击。

---
---

# AGI Pulse (English)

> Sensing the pulse of the silicon world every 4 hours — a zero-backend, fully-automated AI news aggregator.
>
> 🌐 Site: <https://oyan9527.github.io/agipulse/> ｜ 📡 RSS: <https://oyan9527.github.io/agipulse/feed.xml> ｜ ℹ️ About: <https://oyan9527.github.io/agipulse/about.html>

## What it is

The AI field produces far more information every day than anyone can read — official blogs, papers, open-source releases, tech media, and community discussions scattered across hundreds of channels, with the important buried under the noise.

**AGI Pulse** aggregates **300+ sources** into one place and uses AI to filter, score, deduplicate, and summarize — surfacing only what genuinely matters. Think of it as an AI-industry daily that curates and publishes itself.

It runs entirely on its own, with no human intervention — and **collects no user data whatsoever**.

## Highlights

**📰 Front Page — see today's most important stories at a glance**

- **Daily Digest** — an AI-written overview of the day's top stories, leading with the biggest developments.
- **Headline** — the day's most important news, ranked primarily by *how many independent sources reported it*, not raw popularity.
- **Curated Feed** — content that clears the quality bar, in a two-column masonry layout, filterable across 6 categories (Model Releases / Product Launches / Open Source / Industry / Research / Tips & Opinions).
- **Deep Reads** — content the AI judges as genuinely insightful (interpretability research, novel-method papers, engineering post-mortems), not newswire blurbs.
- **Hot Radar** — trending stories ranked by multi-source confirmation × freshness.

**📊 Data Page — trends at a glance**

- **24-hour signal spectrum** (density by hour × category), **daily/weekly/monthly momentum & keyword trends**, **topic tracking** (14-day mention curves with up/down/flat trend), **social AI hotspots** (Bilibili, Hacker News, Reddit, Weibo, Zhihu, X — AI-filtered), and a **GitHub star leaderboard** (day/week/month/year/all-time).

**🌏 Built for Chinese readers** — English titles and bodies are AI-translated (keeping proper nouns like model/company names in the original), each item with an AI-generated summary.

**🔗 Multi-source merging** — when one event is covered by many outlets (e.g. a major model launch reported by 15 sources at once), they collapse into a single card marked "N sources," confirming importance without flooding the feed.

**📡 Open subscription** — a standard Atom/RSS feed for any reader.

## Architecture

**Zero backend.** No servers, no database. The entire pipeline is:

```
GitHub Actions (every 4 hours)
   └─ Python pipeline → static JSON → committed to repo → served by GitHub Pages
```

Three direct benefits: **near-zero running cost** (only pay-per-use DeepSeek API, cents per day), **no ops burden**, and **zero user data** — no accounts, no stored emails, no third-party tracking scripts, sidestepping privacy and data-security liabilities by design.

**The pipeline** (Python) runs each cycle: concurrent **fetch** of 300+ sources (single-source failures degrade gracefully) → **normalize & dedupe** → **AI-relevance filter** (strict only for general-tech sources; native AI sources pass through) → **two-stage LLM** with DeepSeek (cheap prefilter, then 4-dimension scoring — **authority 30% + novelty 25% + impact 25% + practicality 20%** — plus category, Chinese summary, depth score, translation) → **story merging** (bag-of-words similarity + model/product identifiers) → **quality gate** (≥2 sources OR score ≥0.72; quiet days aren't padded) → **output** of static files.

**Frontend** — vanilla ES modules, no framework, no build step. Spectrum and topic curves are live SVG. Desktop/mobile responsive, with a restrained "celadon + circuit" newspaper-broadsheet design.

**Cost control** — a persistent result cache keyed by content id reuses prior verdicts within the 48-hour window, so only genuinely new content ever costs an API call.

**Engineering quality** — 77 automated tests (filtering, merging, security, aggregation) run on every push and before every fetch; silent-failure alerts flag the run red if sources or scoring break; and a Content-Security-Policy + URL allowlist + output escaping defend against injection from third-party sources.
