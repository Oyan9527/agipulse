"""AI 话题相关性判断（关键词法，中英双语）。

用于社媒热点面板：各平台的通用热搜里，只保留与 AI 相关的条目。
关注精确率（宁缺毋滥）——热搜标题短，AI 话题几乎都会出现下列可识别词。
纯规则、零依赖、零成本，随流水线运行。
"""
import re

# 英文/缩写关键词：作为独立词匹配（\b 词边界），避免 "ai" 命中 "chair"/"maintain" 等
_EN_WORD_TERMS = [
    "ai", "agi", "asi", "llm", "llms", "gpt", "chatgpt", "genai", "aigc",
    "openai", "anthropic", "claude", "gemini", "deepmind", "llama", "mistral",
    "qwen", "deepseek", "kimi", "grok", "xai", "copilot", "cursor", "sora",
    "midjourney", "stable diffusion", "diffusion", "transformer", "transformers",
    "nvidia", "cuda", "huggingface", "pytorch", "tensorflow", "vllm", "ollama",
    "langchain", "rag", "mcp", "agent", "agentic", "agents", "multimodal",
    "chatbot", "neural", "deepfake", "veo", "nano banana", "gpu",
]

# 英文短语（含空格/连字符，直接子串匹配，小写）
_EN_PHRASE_TERMS = [
    "machine learning", "deep learning", "large language model",
    "language model", "generative ai", "artificial intelligence",
    "foundation model", "fine-tune", "fine-tuning", "open-source model",
    "text-to-image", "text-to-video", "self-driving", "autonomous driving",
]

# 中文关键词（直接子串匹配）
# 注意："显卡"/"算力"/"机器人" 不在此列——它们是歧义词，常见于非 AI 语境
# （显卡促销、比特币挖矿、扫地机器人等），改由 _has_ambiguous_zh_term 结合
# 上下文判断，避免误判（见下方注释）。
_ZH_TERMS = [
    "人工智能", "大模型", "大语言模型", "语言模型", "生成式", "生成式ai",
    "智能体", "智能助手", "机器学习", "深度学习", "神经网络", "多模态",
    "具身智能", "自动驾驶", "无人驾驶", "英伟达",
    "文心", "通义", "千问", "豆包", "混元", "星火", "盘古", "文小言",
    "智谱", "月之暗面", "面壁", "阶跃", "商汤", "旷视", "科大讯飞", "讯飞",
    "百度智能", "算法模型", "aigc", "提示词", "微调", "推理模型", "扩散模型",
    "文生图", "文生视频", "图生视频", "数字人", "虚拟人", "深度伪造", "换脸",
    "机器智能", "认知智能", "通用人工智能", "超级智能", "大厂ai", "ai眼镜",
    "ai手机", "ai编程", "ai助手", "ai模型", "ai芯片", "ai绘画", "ai视频",
]

_EN_WORD_RE = re.compile(
    r"(?<![a-z])(" + "|".join(re.escape(t) for t in sorted(_EN_WORD_TERMS, key=len, reverse=True)) + r")(?![a-z])"
)


# 型号噪声：把"AI"当型号名/营销后缀的消费硬件（AMD 锐龙 AI 9 HX、Ryzen AI Max、
# Intel Core Ultra 的 AI Boost 等）。这些标题的报道主体是笔记本/CPU 本身而非 AI，
# 判断前先剔除这些片段——剔除后若标题不再含任何 AI 词，就正确地判为不相关。
# 注意不能顺手剔除 "AI PC/AI 手机/AI 眼镜"，那些是真的 AI 品类。
_MODEL_NOISE_RE = re.compile(
    r"锐龙\s*ai\s*\d*\s*[a-z]*\s*\d*"      # 锐龙 AI 9 HX 470
    r"|ryzen\s*ai(\s*max)?\s*\d*\s*[a-z]*\s*\d*"  # Ryzen AI 9 / Ryzen AI Max
    r"|\bai\s*\d+\s*hx\b"                  # AI 9 HX
    r"|\bai\s*boost\b"                     # Intel AI Boost (NPU 营销名)
)


# 歧义词：字面命中不代表话题相关，需结合上下文，否则会在通用硬件/金融/
# 消费类新闻里造成误判（strict_source_prefixes 的通用中文源尤其容易踩中）。
# - "显卡"：多见于纯硬件降价/首发新闻，伴随促销或型号词（跌价/降价/首发价/
#   开售/RTX/GTX 等）时不计入 AI 信号。
# - "算力"：比特币/矿机报道里的"挖矿算力"与 AI 算力无关，伴随这类词时不计入。
# - "机器人"：扫地机器人等消费硬件报道极常见，要求同一标题里还出现别的
#   真实 AI 信号词（_ZH_TERMS 中的任一词）才计入，否则通用机器人新闻会被
#   误判为 AI 相关。
_GPU_SALE_NOISE_RE = re.compile(r"跌价|降价|涨价|首发价|开售|发售|预售|冰点价|优惠价|促销|特价|rtx|gtx")
_HASHRATE_NOISE_RE = re.compile(r"比特币|挖矿|矿机|以太坊|加密货币|虚拟货币|区块链")


def _has_ambiguous_zh_term(low):
    """歧义中文词是否在当前上下文里应计入 AI 信号（见上方逐词说明）。

    注意："机器人"的共现检查必须在这里自己判断中/英文信号词，不能指望调用方
    "先查完 _ZH_TERMS 再调用本函数"这个顺序——is_ai_related 正是先查完
    _ZH_TERMS 才会走到这里，届时 _ZH_TERMS 必然已经不命中，若只检查
    _ZH_TERMS 共现，这个分支就永远是死代码（机器人+英文AI词的报道会被漏判）。
    """
    if "显卡" in low and not _GPU_SALE_NOISE_RE.search(low):
        return True
    if "算力" in low and not _HASHRATE_NOISE_RE.search(low):
        return True
    if "机器人" in low:
        has_other_signal = (
            any(t in low for t in _ZH_TERMS)
            or any(t in low for t in _EN_PHRASE_TERMS)
            or bool(_EN_WORD_RE.search(low))
        )
        if has_other_signal:
            return True
    return False


def is_ai_related(text):
    """标题是否与 AI 话题相关。中文子串 + 英文词边界 + 英文短语三路匹配。
    匹配前先剔除把 AI 当型号名的消费硬件片段（见 _MODEL_NOISE_RE）；
    歧义中文词（显卡/算力/机器人）另需上下文判断（见 _has_ambiguous_zh_term）。
    """
    if not text:
        return False
    low = _MODEL_NOISE_RE.sub(" ", text.lower())
    for t in _ZH_TERMS:
        if t in low:
            return True
    if _has_ambiguous_zh_term(low):
        return True
    for t in _EN_PHRASE_TERMS:
        if t in low:
            return True
    if _EN_WORD_RE.search(low):
        return True
    return False
