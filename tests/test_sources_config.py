"""信源配置的健全性守卫（config/sources.yaml + config/weights.yaml）。

这些都是"写错了不会报错、只会静默少抓/少过滤"的地方：id 拼错，过滤规则就悄悄
失效；url 漏了协议，抓取器要到线上才报错；status 写成别的词，broken 源照样被抓。
"""
import re

from scripts.util import load_yaml

SOURCES = load_yaml("config/sources.yaml")["sources"]
WEIGHTS = load_yaml("config/weights.yaml")
IDS = [s["id"] for s in SOURCES]
# optional = 需要自建服务(RSSHub / wewe-rss)才能启用的桥接源，url 是 PLACEHOLDER_*
VALID_STATUS = {"confirmed", "broken", "optional", "candidate"}


def test_source_ids_are_unique():
    dupes = {i for i in IDS if IDS.count(i) > 1}
    assert not dupes, "重复的 source id: %s" % sorted(dupes)


def test_status_values_are_known():
    """status 只认这几个词——写成 'disabled' 之类的，过滤逻辑看不懂，源会照抓。"""
    bad = {s["id"]: s["status"] for s in SOURCES
           if s.get("status") and s["status"] not in VALID_STATUS}
    assert not bad, "未知的 status: %s" % bad


def test_strict_sources_reference_existing_ids():
    """ai_relevance.strict_sources 里的 id 必须真实存在。

    拼错不会报错，只会让那个源的标题关键词过滤静默失效——综合科技站的非 AI 内容
    就直接灌进库里了。
    """
    known = set(IDS)
    missing = [i for i in WEIGHTS["ai_relevance"]["strict_sources"] if i not in known]
    assert not missing, "strict_sources 引用了不存在的 id: %s" % missing


def test_broken_sources_explain_themselves():
    """标了 broken 就要写清为什么，否则过几个月没人知道能不能恢复。"""
    silent = [s["id"] for s in SOURCES
              if s.get("status") == "broken" and not str(s.get("notes") or "").strip()]
    assert not silent, "这些 broken 源没写停抓原因: %s" % silent


# PLACEHOLDER_* 是"等你自建服务后把地址填这儿"的占位，run_pipeline 会跳过它们
_URL_SOURCES = [s for s in SOURCES
                if s.get("type", "rss") == "rss"
                and not str(s.get("url", "")).startswith("PLACEHOLDER")]


def test_rss_sources_have_plausible_url():
    """一条用例查全部六百多个源：parametrize 会把用例数撑到四百多，
    跑一次测试满屏都是点，反而看不出这套守卫总共几条。坏的 id 一次列全就够定位。"""
    bad = {}
    for src in _URL_SOURCES:
        url = src.get("url", "")
        if not url.startswith(("http://", "https://")):
            bad[src["id"]] = "缺少协议: %r" % url
        elif re.search(r"\s", url):
            bad[src["id"]] = "url 里有空白字符: %r" % url
    assert not bad, "url 有问题的源: %s" % bad


def test_generic_zh_sources_are_covered_by_strict_filter():
    """zh- 开头的中文通用站靠前缀规则过滤；前缀要是被改掉，这批源会失去过滤。"""
    prefixes = tuple(WEIGHTS["ai_relevance"]["strict_source_prefixes"])
    zh_sources = [i for i in IDS if i.startswith("zh-")]
    assert zh_sources, "没有 zh- 源了？那这条守卫该删"
    assert all(i.startswith(prefixes) for i in zh_sources), (
        "有 zh- 源不被 strict_source_prefixes %s 覆盖" % (prefixes,))
