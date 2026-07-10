"""AI 话题相关性判断（关键词法，中英双语）。

用于社媒热点面板：各平台的通用热搜里，只保留与 AI 相关的条目。
关注精确率（宁缺毋滥）——热搜标题短，AI 话题几乎都会出现下列可识别词。
纯规则、零依赖、零成本，每两小时随流水线运行。
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
_ZH_TERMS = [
    "人工智能", "大模型", "大语言模型", "语言模型", "生成式", "生成式ai",
    "智能体", "智能助手", "机器学习", "深度学习", "神经网络", "多模态",
    "机器人", "具身智能", "自动驾驶", "无人驾驶", "算力", "英伟达", "显卡",
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


def is_ai_related(text):
    """标题是否与 AI 话题相关。中文子串 + 英文词边界 + 英文短语三路匹配。
    匹配前先剔除把 AI 当型号名的消费硬件片段（见 _MODEL_NOISE_RE）。
    """
    if not text:
        return False
    low = _MODEL_NOISE_RE.sub(" ", text.lower())
    for t in _ZH_TERMS:
        if t in low:
            return True
    for t in _EN_PHRASE_TERMS:
        if t in low:
            return True
    if _EN_WORD_RE.search(low):
        return True
    return False
