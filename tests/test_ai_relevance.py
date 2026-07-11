"""AI 相关性关键词判断（scripts.ai_relevance）的回归测试。

踩过的坑：`_ZH_TERMS` 里的 "显卡"/"算力"/"机器人" 是歧义词，在严格过滤的通用
中文源（strict_source_prefixes: zh-）里会命中大量非 AI 内容——显卡降价新闻、
比特币挖矿算力新闻、扫地机器人新闻——把噪声整条放进后续去重与两阶段打分，
浪费打分预算。修复后这三个词必须结合上下文判断，且不能误伤真正的 AI 内容。
"""
from scripts.ai_relevance import is_ai_related


def test_gpu_price_news_is_not_ai_related():
    assert is_ai_related("RTX 5090显卡跌至历史冰点价，玩家：终于等到了") is False


def test_bitcoin_hashrate_news_is_not_ai_related():
    assert is_ai_related("比特币算力再创新高，矿机厂商订单爆满") is False


def test_robot_vacuum_news_is_not_ai_related():
    assert is_ai_related("小米推出新款扫地机器人，主打自动集尘") is False


def test_genuine_ai_gpu_and_compute_news_still_matches():
    # 同样含"显卡"/"算力"，但语境是真实 AI 新闻（且带有"英伟达"/"ai"信号词）
    assert is_ai_related("英伟达发布新一代AI显卡，算力提升3倍") is True


def test_genuine_ai_robot_news_still_matches():
    # "机器人"需伴随其他真实 AI 信号词（此处为"具身智能"）才计入
    assert is_ai_related("具身智能机器人成为本届展会最大亮点") is True


def test_robot_with_only_english_ai_signal_still_matches():
    # 回归测试：机器人共现检查曾经是死代码——is_ai_related 先查完 _ZH_TERMS
    # 才会走到 _has_ambiguous_zh_term，届时 _ZH_TERMS 必然已不命中，若该函数
    # 只检查 _ZH_TERMS 共现，"机器人+英文AI词"（标题里没有任何 _ZH_TERMS 词）
    # 这类报道就会被永远漏判。这里标题只含"机器人"和英文信号词"gpt"，不含任何
    # _ZH_TERMS 词，专门验证共现检查真的会生效，而不是恰好被主循环提前命中。
    assert is_ai_related("波士顿动力机器人现场展示新一代 GPT 驱动的类人机器人") is True
