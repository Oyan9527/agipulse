"""趋势热点分析：从 48 小时窗口的条目里产出三类信号，写入 trends.json。

1. hot_stories   —— 热点故事：多源确认数 × 时间新鲜度衰减 排序（对齐 AI News Radar v0.7 热点视图思路）
2. keywords      —— 关键词动量：近24h提及数 vs 前24h，识别上升/下降话题
3. category_momentum —— 分类动量：各分类近24h条数与环比变化

关键词提取用"已知AI实体词表 + 英文专有词启发式"，纯规则零依赖——
词表只影响趋势展示，不影响打分/精选主流程，宁可漏不可错。
"""
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from .util import get_logger

log = get_logger(__name__)

# 已知 AI 实体词表（小写匹配 -> 展示名）。维护成本低，新热词靠专有词启发式兜底。
KNOWN_ENTITIES = {
    "openai": "OpenAI", "gpt": "GPT", "chatgpt": "ChatGPT", "sora": "Sora",
    "anthropic": "Anthropic", "claude": "Claude",
    "gemini": "Gemini", "deepmind": "DeepMind", "google": "Google",
    "llama": "Llama", "meta": "Meta",
    "mistral": "Mistral", "qwen": "Qwen", "deepseek": "DeepSeek",
    "kimi": "Kimi", "glm": "GLM", "minimax": "MiniMax", "doubao": "豆包",
    "grok": "Grok", "xai": "xAI",
    "nvidia": "NVIDIA", "cuda": "CUDA",
    "hugging face": "Hugging Face", "huggingface": "Hugging Face",
    "pytorch": "PyTorch", "vllm": "vLLM", "ollama": "Ollama",
    "langchain": "LangChain", "transformers": "Transformers",
    "copilot": "Copilot", "cursor": "Cursor", "windsurf": "Windsurf",
    "agent": "Agent", "agentic": "Agent", "mcp": "MCP", "rag": "RAG",
    "diffusion": "Diffusion", "robotics": "Robotics", "robot": "Robotics",
    "benchmark": "Benchmark", "multimodal": "多模态",
    "open source": "开源", "open-source": "开源",
    "fine-tune": "微调", "fine-tuning": "微调",
    "reasoning": "Reasoning", "inference": "推理",
}

# 英文专有词启发式：连续大写开头的词组（如 "Signal Field"），过滤常见句首词
_PROPER_RE = re.compile(r"\b([A-Z][a-zA-Z0-9]+(?:[ -][A-Z][a-zA-Z0-9]+)*)\b")
_STOP_PROPER = {
    "The", "A", "An", "This", "That", "What", "Why", "How", "When", "Is", "Are",
    "New", "AI", "I", "My", "We", "You", "It", "If", "In", "On", "For", "With",
    "Introducing", "Announcing", "Show", "Ask", "Reddit", "Github", "GitHub",
}


def _extract_keywords(text):
    found = set()
    lower = text.lower()
    for needle, display in KNOWN_ENTITIES.items():
        if needle in lower:
            found.add(display)
    for m in _PROPER_RE.finditer(text):
        phrase = m.group(1)
        if phrase in _STOP_PROPER or len(phrase) < 3:
            continue
        if " " in phrase or "-" in phrase:  # 词组比单词更可能是真实体
            found.add(phrase)
    return found


def _parse_iso(s):
    return datetime.fromisoformat(s)


def _build_hot_stories(items, stories, weights_config, now):
    """热点故事：多源确认 × 新鲜度衰减 × 最高分。"""
    decay_hours = weights_config.get("freshness", {}).get("decay_window_hours", 48)
    items_by_id = {it["id"]: it for it in items}
    hot = []
    for story in stories:
        age_h = (now - _parse_iso(story["first_seen"])).total_seconds() / 3600
        if age_h > decay_hours:
            continue
        freshness = math.exp(-age_h / (decay_hours / 2))
        member_scores = [
            items_by_id[iid].get("weighted_score") or 0
            for iid in story["item_ids"] if iid in items_by_id
        ]
        best_score = max(member_scores, default=0)
        heat = story["source_count"] * freshness * (0.5 + best_score)
        canonical = items_by_id.get(story["item_ids"][0], {})
        hot.append(
            {
                "story_id": story["story_id"],
                "title": story["canonical_title"],
                "title_zh": canonical.get("title_zh"),
                "url": canonical.get("url"),
                "category": story.get("category"),
                "source_count": story["source_count"],
                "first_seen": story["first_seen"],
                "heat": round(heat, 4),
                "reason_zh": canonical.get("reason_zh", ""),
            }
        )
    hot.sort(key=lambda x: x["heat"], reverse=True)
    return hot[:10]


def _dimension_from_window(items, now, window, keyword_samples_limit=3):
    """day 维度：直接从当前处理窗口的条目算 近window vs 前window。"""
    recent_kw, prior_kw = Counter(), Counter()
    recent_cat, prior_cat = Counter(), Counter()
    keyword_samples = defaultdict(list)

    for it in items:
        age = now - _parse_iso(it["published_at"])
        if age > window * 2:
            continue
        is_recent = age <= window
        for kw in _extract_keywords(it["title"]):
            (recent_kw if is_recent else prior_kw)[kw] += 1
            if is_recent and len(keyword_samples[kw]) < keyword_samples_limit:
                keyword_samples[kw].append(it["id"])
        cat = it.get("category")
        if cat:
            (recent_cat if is_recent else prior_cat)[cat] += 1

    return _pack_dimension(recent_kw, prior_kw, recent_cat, prior_cat, keyword_samples)


def _dimension_from_archive(daily_archives, now, days):
    """week/month 维度：聚合日档。近 N 天 vs 前 N 天。历史不足时前段为空 → delta 显示为'新'。"""
    today = now.date()
    recent_kw, prior_kw = Counter(), Counter()
    recent_cat, prior_cat = Counter(), Counter()

    for date_str, payload in daily_archives.items():
        d = datetime.fromisoformat(date_str).date()
        age_days = (today - d).days
        if age_days < 0 or age_days >= days * 2:
            continue
        target_kw, target_cat = (recent_kw, recent_cat) if age_days < days else (prior_kw, prior_cat)
        for kw, c in payload.get("keyword_counts", {}).items():
            target_kw[kw] += c
        for cat, c in payload.get("by_category", {}).items():
            target_cat[cat] += c

    return _pack_dimension(recent_kw, prior_kw, recent_cat, prior_cat, {})


def _pack_dimension(recent_kw, prior_kw, recent_cat, prior_cat, keyword_samples):
    keywords = []
    for kw, count in recent_kw.most_common(30):
        if count < 2:
            continue  # 单次提及不构成趋势
        prev = prior_kw.get(kw, 0)
        delta_pct = round(((count - prev) / prev) * 100) if prev else None
        keywords.append(
            {
                "term": kw,
                "count": count,
                "count_prev": prev,
                "delta_pct": delta_pct,  # None 表示前一周期没出现过（新）
                "sample_item_ids": keyword_samples.get(kw, []),
            }
        )
    keywords = keywords[:16]

    category_momentum = []
    for cat in sorted(set(recent_cat) | set(prior_cat)):
        cur, prev = recent_cat.get(cat, 0), prior_cat.get(cat, 0)
        category_momentum.append(
            {"category": cat, "count": cur, "count_prev": prev, "delta": cur - prev}
        )
    category_momentum.sort(key=lambda x: x["count"], reverse=True)

    return {"keywords": keywords, "category_momentum": category_momentum}


def build_trends(items, stories, weights_config, daily_archives=None):
    """items: 已打分合并的条目（处理窗口）；stories: 故事列表；daily_archives: 日档 {date: payload}。

    输出三个维度：
      day   —— 近24h vs 前24h（当前窗口内直接计算）
      week  —— 近7天 vs 前7天（日档聚合）
      month —— 近30天 vs 前30天（日档聚合；部署初期历史不足时环比显示为"新"）
    """
    now = datetime.now(timezone.utc)
    daily_archives = daily_archives or {}

    dimensions = {
        "day": _dimension_from_window(items, now, timedelta(hours=24)),
        "week": _dimension_from_archive(daily_archives, now, days=7),
        "month": _dimension_from_archive(daily_archives, now, days=30),
    }

    hot_stories = _build_hot_stories(items, stories, weights_config, now)

    log.info(
        "trends: %d hot stories; day %d kw / week %d kw / month %d kw",
        len(hot_stories),
        len(dimensions["day"]["keywords"]),
        len(dimensions["week"]["keywords"]),
        len(dimensions["month"]["keywords"]),
    )
    return {
        "generated_at": now.isoformat(),
        "hot_stories": hot_stories,
        "dimensions": dimensions,
        "archive_days": len(daily_archives),
    }
