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


def build_trends(items, stories, weights_config):
    """items: 已打分合并的条目（48h窗口）；stories: 故事列表。"""
    now = datetime.now(timezone.utc)
    day = timedelta(hours=24)

    # ---- 1. 热点故事：多源确认 × 新鲜度衰减 ----
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
                "url": canonical.get("url"),
                "category": story.get("category"),
                "source_count": story["source_count"],
                "first_seen": story["first_seen"],
                "heat": round(heat, 4),
                "reason_zh": canonical.get("reason_zh", ""),
            }
        )
    hot.sort(key=lambda x: x["heat"], reverse=True)
    hot_stories = hot[:10]

    # ---- 2. 关键词动量：近24h vs 前24h ----
    recent_counts, prior_counts = Counter(), Counter()
    keyword_samples = defaultdict(list)
    for it in items:
        published = _parse_iso(it["published_at"])
        age = now - published
        kws = _extract_keywords(it["title"])
        bucket = recent_counts if age <= day else prior_counts
        for kw in kws:
            bucket[kw] += 1
            if age <= day and len(keyword_samples[kw]) < 3:
                keyword_samples[kw].append(it["id"])

    keywords = []
    for kw, count in recent_counts.most_common(30):
        if count < 2:
            continue  # 单次提及不构成趋势
        prev = prior_counts.get(kw, 0)
        delta_pct = round(((count - prev) / prev) * 100) if prev else None
        keywords.append(
            {
                "term": kw,
                "count_24h": count,
                "count_prev_24h": prev,
                "delta_pct": delta_pct,  # None 表示新出现
                "sample_item_ids": keyword_samples[kw],
            }
        )
    keywords = keywords[:16]

    # ---- 3. 分类动量 ----
    cat_recent, cat_prior = Counter(), Counter()
    for it in items:
        cat = it.get("category")
        if not cat:
            continue
        age = now - _parse_iso(it["published_at"])
        (cat_recent if age <= day else cat_prior)[cat] += 1

    category_momentum = []
    for cat in sorted(set(cat_recent) | set(cat_prior)):
        cur, prev = cat_recent.get(cat, 0), cat_prior.get(cat, 0)
        category_momentum.append(
            {
                "category": cat,
                "count_24h": cur,
                "count_prev_24h": prev,
                "delta": cur - prev,
            }
        )
    category_momentum.sort(key=lambda x: x["count_24h"], reverse=True)

    log.info(
        "trends: %d hot stories, %d trending keywords, %d categories",
        len(hot_stories), len(keywords), len(category_momentum),
    )
    return {
        "generated_at": now.isoformat(),
        "hot_stories": hot_stories,
        "keywords": keywords,
        "category_momentum": category_momentum,
    }
