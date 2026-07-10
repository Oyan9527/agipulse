# 硅基脉动 · AGI Pulse

一个零后端、零服务器成本的 AI 行业信息聚合网站。GitHub Actions 定时抓取 **300+ 公开信源** → DeepSeek 两级打分/中文翻译/去重/故事合并/趋势分析 → 静态 JSON → GitHub Pages 直接托管，前端运行时 fetch 数据渲染，没有任何构建步骤。

两个版面：**头版**（`index.html`：头条大字号 + 精选/全部信息流 + 热点雷达 + 今日简报）与**数据版**（`trends.html`：24H 信息密度频谱√缩放、信号量/精选率/信源健康/多源确认指标、**日/周/月三维度**分类动量与趋势关键词、**社媒 AI 热点**（B站/微博/Hacker News/Reddit 上正热的 AI 话题，关键词过滤+英文标题自动翻译）、**GitHub 涨星榜**（近24h 新增 star 最多的仓库））。通用能力：英文标题自动附中文译文、精选分类配额（论文≤10、开源项目保底5）、命令面板搜索（Ctrl/Cmd+K）。界面为中文报纸头版风格：米白纸面、衬线大刊头、朱红强调色、细线分栏。

信源构成（共 308）：152 个 RSS（官方博客/研究机构/高信号个人/科技媒体 52 + 中文媒体与独立博客 100）+ 111 个重点 GitHub 仓库 releases + 19 个 arXiv 分类 + 20 个 Reddit 社区 + 5 组 Hacker News 主题查询。中文源第三批为批量实测导入（媒体 12 + 独立博客 88，AI 标签优先），依赖 DeepSeek 粗筛过滤非 AI 内容。此外另有 5 个独立展示源（`role: social_hot` / `gh_trending`）：百度/B站/知乎热搜、Hacker News 前台、GitHub 涨星榜——不进 AI 打分主流程，仅供数据版对应面板展示。

对标 [AI News Radar](https://learnprompt.github.io/ai-news-radar/)、[AIHOT](https://aihot.virxact.com/)、[AGI Hunt](https://agihunt.info/) 三个产品的信息覆盖范围与设计思路，细节见 `.claude/plans/` 下的建站方案文档。

## 目录结构

```
config/            信息源注册表、分类定义、打分权重与质量门控阈值
scripts/           抓取/归一化/去重/DeepSeek打分/故事合并/编排入口
docs/              纯静态前端（无构建步骤；命名为 docs 是因为 GitHub Pages 分支模式只认 /(root) 或 /docs）
docs/data/         流水线产出的 JSON，前端运行时直接 fetch
.github/workflows/ 定时抓取工作流
```

## 本地开发

```bash
pip install -r requirements.txt

# 只跑抓取/归一化/去重，验证数据源是否可用，不调用任何 LLM
python -m scripts.run_pipeline --skip-llm --output-dir docs/data

# 用确定性启发式打分代替真实 DeepSeek 调用，产出可用于前端联调的真实数据（推荐日常前端开发用这个）
python -m scripts.run_pipeline --mock-llm --output-dir docs/data

# 生产模式：真实调用 DeepSeek 两级打分（需要设置环境变量 DEEPSEEK_API_KEY）
export DEEPSEEK_API_KEY=sk-xxx
python -m scripts.run_pipeline --output-dir docs/data
```

预览前端：

```bash
python -m http.server 8778 --directory docs
# 打开 http://localhost:8778
```

> 当前仓库里 `docs/data/*.json` 是用 `--mock-llm` 生成的示例数据（条目里的 `reason_zh` 会带 `[mock]` 前缀），仅用于前端开发联调。部署后由 GitHub Actions 用真实 DeepSeek Key 跑出的数据会覆盖它。

## 加一个新信源

编辑 `config/sources.yaml`，新增一条：

```yaml
- id: some-blog
  type: rss                      # rss | github_releases | arxiv | hn_algolia | reddit | generic_json
  url: https://example.com/feed.xml
  category_hint: [模型发布]
  authority_weight: 0.7           # 0-1，用于四维度打分中的"信源权威度"
  poll_minutes: 60
  status: verify                  # 先标 verify，本地跑一次 --skip-llm 确认能抓到数据后改成 confirmed
```

单个源抓取失败不会影响整体流水线——失败信息会记录在 `docs/data/source-status.json` 里，前端"信源健康度"面板会显示出来。

## 部署到 GitHub Pages（详细步骤）

### 第 1 步：建仓库

登录 GitHub（本项目对应账号 `Oyan9527`）→ 右上角 `+` → **New repository**：
- Repository name：`agipulse`（已建好）
- 可见性选 **Public**（Public 仓库才有免费无限的 Actions 分钟数；Private 每月只有 2000 分钟额度，每小时跑一次很快就会用完）
- 不要勾选 "Add a README"（本地已有，勾了会产生冲突）
- 点 **Create repository**

### 第 2 步：推送代码

在项目目录（本机是 `C:\Users\Yan\ccstudy`）执行：

```bash
git branch -M main
git remote add origin https://github.com/Oyan9527/agipulse.git
git push -u origin main
```

> 首次推送会要求登录。Windows 会弹出浏览器授权（Git Credential Manager），登录 `Oyan9527` 账号授权即可。

### 第 3 步：配置密钥

仓库页面 → **Settings**（顶栏最右）→ 左侧 **Secrets and variables** → **Actions** → 绿色按钮 **New repository secret**：

| Name | Value | 必需？ |
|---|---|---|
| `DEEPSEEK_API_KEY` | 你在 [platform.deepseek.com](https://platform.deepseek.com/) 创建的 API Key（`sk-` 开头） | ✅ 必需，没有它流水线会直接报错 |
| `GH_PAT` | 一个勾选了 `public_repo` 权限的 [Personal Access Token](https://github.com/settings/tokens) | ⚠️ 强烈建议。注册表里有 111 个 GitHub 仓库源，匿名限额只有 60 次/小时，不配 PAT 大部分 GitHub 源会被限流跳过（其他源不受影响）；配上后限额 5000 次/小时 |

### 第 4 步：确认 Actions 权限（重要，最容易漏）

仓库 **Settings** → 左侧 **Actions** → **General** → 拉到最下面 **Workflow permissions**：
- 确认选中 **"Read and write permissions"**，然后 **Save**。
- 工作流要把抓到的数据 commit 回仓库，没有写权限会报 `Permission denied` / 403。（workflow 文件里已声明 `permissions: contents: write`，但如果组织/账号级别禁用了写权限，这里的仓库级开关是最终开关。）

### 第 5 步：开启 Pages

仓库 **Settings** → 左侧 **Pages**（在 "Code and automation" 分组下）：

1. **Build and deployment** 区域 → **Source** 下拉框 → 选 **"Deploy from a branch"**
2. 下方会出现 **Branch** 行，有两个下拉框：
   - 第一个选 **`main`**
   - 第二个（默认显示 `/(root)`）点开 → 选 **`/docs`**（GitHub 分支部署模式只支持 `/(root)` 和 `/docs` 两个选项，所以前端目录命名为 docs）
3. 点 **Save**
4. 等 1-2 分钟，页面顶部会出现绿色横幅 "Your site is live at `https://oyan9527.github.io/agipulse/`"，这就是你的站点地址

> 如果 Source 下拉里看到 "GitHub Actions" 选项，不要选它——那是给自定义构建流程用的，我们这种纯静态站直接 "Deploy from a branch" 最简单。

### 第 6 步：手动触发首次数据抓取（种子数据）

仓库顶栏 **Actions** → 左侧列表选 **"Update AI signal data"** → 右侧 **Run workflow** 按钮 → 保持 `main` 分支 → 绿色 **Run workflow**。

- 运行约 3-6 分钟。点进运行记录可以看每一步日志：抓了多少条、DeepSeek 筛掉多少、精选多少。
- 成功后仓库会多一个 `data: update feeds @ ...` 的提交，`docs/data/*.json` 变成真实 DeepSeek 打分的数据（`reason_zh` 不再带 `[mock]` 前缀）。
- 这个提交会自动触发 Pages 重新发布（1-2 分钟生效）。

### 第 7 步：验证站点

访问 `https://oyan9527.github.io/agipulse/`，检查：
- [ ] 频谱图有数据、随时间分布
- [ ] 看板四个指标卡有数字
- [ ] 信息流条目的推荐理由是真实中文理由（无 `[mock]`）
- [ ] 右侧"热点雷达"和"今日简报"有内容
- [ ] Ctrl/Cmd+K 能搜索

### 之后的日常运维

- workflow 每小时整点自动跑，无需人工干预；每次有新数据才会产生提交，没有新数据就静默跳过。
- **加/删信源**：改 `config/sources.yaml` 后 push 到 `main`，下一次运行生效。
- **调打分权重/门槛/分类配额**：改 `config/weights.yaml`（`category_quotas` 控制精选里各分类的上限/保底，当前：论文研究最多10条、开源项目保底5条）。
- **周/月趋势**：依赖 `docs/data/archive/` 下的每日聚合日档（由流水线自动生成、自动清理62天前的旧档）。部署首日周/月环比会显示"新"，随归档积累自动完整，无需任何操作。
- **换 DeepSeek Key**：直接在 Settings → Secrets 里更新 `DEEPSEEK_API_KEY` 的值，即时生效。
- **调抓取频率**：改 `.github/workflows/pipeline.yml` 里的 cron（比如 `"0 */2 * * *"` 是每2小时一次，成本减半）。

### 常见问题排查

| 症状 | 原因与处理 |
|---|---|
| Actions 报 `DEEPSEEK_API_KEY not set` | 第 3 步的 secret 没配或名字打错（必须全大写完全一致） |
| Actions 报 403 / `Permission denied` 推不上代码 | 第 4 步的 Workflow permissions 没开 Read and write |
| 站点 404 | Pages 还没发布完（等2分钟）；或第 5 步目录选成了 `/(root)`——必须选 `/docs` |
| 页面能开但一直"读取中" | `docs/data/*.json` 还没被真实数据覆盖，先跑第 6 步；或浏览器控制台看 fetch 报错 |
| Reddit 源持续 429 | 正常现象，单次失败不影响其他源；GitHub Actions 每次运行 IP 不同，通常下轮就恢复 |

### 成本

- GitHub Actions / Pages：Public 仓库完全免费。
- DeepSeek API：按量计费。以约 700 条/天、每小时跑一次估算，配合两级过滤（粗筛丢弃大部分噪声后才进入更贵的打分调用），日均成本预计在几毛钱人民币以内。
- **结果缓存**（`docs/data/llm-cache.json`）进一步压低成本：处理窗口是 48 小时，同一条内容在被淘汰出窗口前会被连续抓到多次（每小时一次，最多约48次）；缓存把每条内容的判定结果（prefilter拒绝 / 打分完成）按内容id持久化下来，命中过的下一轮直接复用、不再调用DeepSeek，只有真正首次出现的新内容才会真正花钱调用两级判定——相当于把重复调用次数从"最多48次"降到"1次"。缓存随数据一起提交进仓库，跟着GitHub Actions的每次全新checkout生效，超出48h窗口的旧条目会自动从缓存清理，不会无限增长。

## Phase 3：补充 X/Twitter、知乎、微信公众号覆盖（可选）

这几类信源没有稳定免费的官方 API，`config/sources.yaml` 里已经预留了 `status: optional` 的占位源，接入方式是"自建一个转 RSS 的桥接服务，把它的输出 URL 当成普通 RSS 源注册进来"，不需要为它们单独写抓取逻辑：

- **X/Twitter**（社媒热点面板用）：自建一个 [RSSHub](https://github.com/DIYgod/RSSHub) 实例（可以另开一个仓库用 GitHub Actions/Railway/Render 免费额度跑），配置好关键词/列表订阅，把输出 RSS 地址填入 `x-ai-social`（数据版"社媒AI热点"用）或 `rsshub-x-bridge`（主信息流用）的 `url` 字段，`status` 改成 `confirmed`。
- **知乎**（社媒热点面板用）：实测(2026-07-10) `/search/v3` 404、`/hot-lists/total` 401、`/billboard` 页 403，均需登录态或签名头，无免费直连路径。同样通过自建 RSSHub 的 `/zhihu/hot` 或 `/zhihu/search/:keyword` 路由，填入 `zhihu-ai-social` 的 `url` 字段激活。
- **微信公众号**（主信息流用）：自建开源的 [wewe-rss](https://github.com/cooderl/wewe-rss)（公众号转 RSS 镜像工具），同样拿到输出的 RSS 地址填进 `wewe-rss-bridge` 条目。

这样"不稳定"信源被隔离在独立部署的桥接服务里，即使它们挂了也不会影响主站抓取流水线。

> 社媒 AI 热点面板目前实际生效的是 **B站**（关键词"AI 大模型"搜索）、**微博**（热搜榜，AI话题上榜与否取决于当天热点，常态是空很正常）、**Hacker News**（前台热榜）、**Reddit**（r/singularity）——都经同一套中英文关键词过滤器（`scripts/ai_relevance.py`）只保留 AI 相关条目，英文标题由 DeepSeek 顺带译成中文。

## 已知限制 / 后续可做的事

- `anthropic-news`、`microsoft-ai-blog` 目前标记为 `broken`（官方无稳定 RSS / 反爬），可以后续接入 Jina Reader（`https://r.jina.ai/<url>`）做静态页兜底抓取。
- `zhihu-hot` 标记为 `broken`（原端点已下线），需要找新的公开端点。
- Reddit 对匿名出口 IP 限流较严，个别 subreddit 偶发 429（已加重试+退避），GitHub Actions 各次运行 IP 不同，通常不会持续失败。
