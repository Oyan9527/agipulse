# 信号场 · AI Signal Field

一个零后端、零服务器成本的 AI 行业信息聚合网站。GitHub Actions 定时抓取公开信源 → DeepSeek 两级打分/去重/故事合并 → 静态 JSON → GitHub Pages 直接托管，前端运行时 fetch 数据渲染，没有任何构建步骤。

对标 [AI News Radar](https://learnprompt.github.io/ai-news-radar/)、[AIHOT](https://aihot.virxact.com/)、[AGI Hunt](https://agihunt.info/) 三个产品的信息覆盖范围与设计思路，细节见 `.claude/plans/` 下的建站方案文档。

## 目录结构

```
config/            信息源注册表、分类定义、打分权重与质量门控阈值
scripts/           抓取/归一化/去重/DeepSeek打分/故事合并/编排入口
site/              纯静态前端（无构建步骤）
site/data/         流水线产出的 JSON，前端运行时直接 fetch
.github/workflows/ 定时抓取工作流
```

## 本地开发

```bash
pip install -r requirements.txt

# 只跑抓取/归一化/去重，验证数据源是否可用，不调用任何 LLM
python -m scripts.run_pipeline --skip-llm --output-dir site/data

# 用确定性启发式打分代替真实 DeepSeek 调用，产出可用于前端联调的真实数据（推荐日常前端开发用这个）
python -m scripts.run_pipeline --mock-llm --output-dir site/data

# 生产模式：真实调用 DeepSeek 两级打分（需要设置环境变量 DEEPSEEK_API_KEY）
export DEEPSEEK_API_KEY=sk-xxx
python -m scripts.run_pipeline --output-dir site/data
```

预览前端：

```bash
python -m http.server 8778 --directory site
# 打开 http://localhost:8778
```

> 当前仓库里 `site/data/*.json` 是用 `--mock-llm` 生成的示例数据（条目里的 `reason_zh` 会带 `[mock]` 前缀），仅用于前端开发联调。部署后由 GitHub Actions 用真实 DeepSeek Key 跑出的数据会覆盖它。

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

单个源抓取失败不会影响整体流水线——失败信息会记录在 `site/data/source-status.json` 里，前端"信源健康度"面板会显示出来。

## 部署到 GitHub Pages（详细步骤）

1. **建仓库**：在 GitHub 新建一个 **Public** 仓库（Public 才有免费无限 Actions 分钟数）。
2. **推送代码**：
   ```bash
   git init
   git add .
   git commit -m "init: AI signal field"
   git branch -M main
   git remote add origin https://github.com/<你的用户名>/<仓库名>.git
   git push -u origin main
   ```
3. **配置密钥**：仓库 Settings → Secrets and variables → Actions → New repository secret
   - `DEEPSEEK_API_KEY`：你自己的 DeepSeek API Key（必需）
   - `GH_PAT`：一个有 `public_repo` 读权限的 GitHub Personal Access Token（可选，用于把 GitHub API 限额从 60次/小时提升到 5000次/小时；不设置也能跑，只是并发抓取 GitHub releases 时更容易触发限流）
4. **开启 Pages**：仓库 Settings → Pages → Build and deployment → Source 选择 "Deploy from a branch" → Branch 选 `main`，目录选 `/site`。
5. **首次种子数据**：仓库 Actions 页面 → 选择 "Update AI signal data" workflow → Run workflow（手动触发一次 `workflow_dispatch`），等待跑完，确认 `site/data/*.json` 被更新并提交。
6. **验证站点**：访问 `https://<你的用户名>.github.io/<仓库名>/`，确认页面能正常加载频谱图和信息流（此时应该是真实 DeepSeek 打分的数据，不再带 `[mock]` 前缀）。
7. **之后**：workflow 每小时自动跑一次，无需人工干预。改 `config/sources.yaml` 后 push 到 `main`，下一次运行就会生效。

### 成本

- GitHub Actions / Pages：Public 仓库完全免费。
- DeepSeek API：按量计费。以约 700 条/天、每小时跑一次估算，配合两级过滤（粗筛丢弃大部分噪声后才进入更贵的打分调用），日均成本预计在几毛钱人民币以内。

## Phase 3：补充 X/Twitter 与微信公众号覆盖（可选）

这两类信源没有稳定免费的官方 API，`config/sources.yaml` 里已经预留了两个 `status: optional` 的占位源，接入方式是"自建一个转 RSS 的桥接服务，把它的输出 URL 当成普通 RSS 源注册进来"，不需要为它们单独写抓取逻辑：

- **X/Twitter**：自建一个 [RSSHub](https://github.com/DIYgod/RSSHub) 实例（可以另开一个仓库用 GitHub Actions/Railway/Render 免费额度跑），配置好想关注的创始人/研究员的 X 列表，拿到类似 `https://your-rsshub.example.com/twitter/list/xxxx` 的 RSS 地址，填入 `rsshub-x-bridge` 这条源的 `url` 字段，把 `status` 改成 `confirmed`。
- **微信公众号**：自建开源的 [wewe-rss](https://github.com/cooderl/wewe-rss)（公众号转 RSS 镜像工具），同样拿到输出的 RSS 地址填进 `wewe-rss-bridge` 条目。

这样两类"不稳定"信源被隔离在独立部署的桥接服务里，即使它们挂了也不会影响主站抓取流水线。

## 已知限制 / 后续可做的事

- `anthropic-news`、`microsoft-ai-blog` 目前标记为 `broken`（官方无稳定 RSS / 反爬），可以后续接入 Jina Reader（`https://r.jina.ai/<url>`）做静态页兜底抓取。
- `zhihu-hot` 标记为 `broken`（原端点已下线），需要找新的公开端点。
- Reddit 对匿名出口 IP 限流较严，个别 subreddit 偶发 429（已加重试+退避），GitHub Actions 各次运行 IP 不同，通常不会持续失败。
