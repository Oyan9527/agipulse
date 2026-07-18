"""跨源同事件合并：36小时滚动窗口内，用手写的轻量 TF-IDF/余弦相似度做贪心聚类。
量级小（通常每次运行几百条），纯 Python 稀疏向量实现，不依赖 numpy/scikit-learn
（避免在无编译器环境下的构建失败，例如较新的 Python 版本还没有预编译 wheel 时）。
分词同时兼顾英文（单词）和中文（双字符 bigram），无需外部分词库。
"""
import math
import re
from collections import Counter
from datetime import datetime, timedelta

from .util import make_id, get_logger

log = get_logger(__name__)

_WORD_RE = re.compile(r"[a-zA-Z0-9]+")
_CJK_RE = re.compile(r"[一-鿿]")

# 强实体 = 带版本号的模型/产品标识（GPT-5.6、Claude Fable 5、LongCat-2.0、Gemini 3.5 …）。
# 同一事件的跨源报道措辞差别极大（中英混排、角度各异），TF-IDF 词袋抓不住它们，
# 但几乎必然共享这个标识符——实测 GPT-5.6 发布当天有 15 条报道分散成 13 个"故事"。
_ENTITY_RE = re.compile(r"([A-Za-z][A-Za-z]{2,})[\s\-]?v?[\s\-]?(\d+(?:\.\d+)?)")

# 品牌名 + 独立型号（型号本身是"字母+数字"而非纯数字，如 Kimi K3、DeepSeek R1、
# DeepSeek V3、OpenAI o3），_ENTITY_RE 抓不住——它要求品牌名后面直接接纯数字，
# 中间那个型号字母（K/R/V/o…）打破了这个模式。实测 Kimi K3 发布当天5个不同信源
# 分别报道，_strong_entities 全部返回空集合，一个都没识别成同一实体，本该合并成
# 一条多源头条的报道被拆成了5个独立故事。
_BRAND_MODEL_RE = re.compile(r"([A-Za-z][A-Za-z]{2,})\s+([A-Za-z]\d+(?:\.\d+)?)\b")

# 实体匹配分支的兜底：同实体但不同事件的报道（如"Model 3 软件升级"与"Model 3 遭监管召回"）
# 不该仅凭共享实体就合并。但不能靠余弦相似度兜底——跨语言/措辞差异极大的同一事件报道
# （GPT-5.6 那次，词袋几乎不重叠）余弦反而比"同实体不同事件"的报道更低，没有一个固定
# 阈值能同时接住两边。改用"事件类别词冲突"判断：只有当两条标题分别命中不同类别
# （如一条是"召回"类，另一条是"发布/更新"类）时才拦截合并；只要有一边没命中任何
# 类别词，或双方命中同一类别，就仍按实体合并（保留跨语言同事件的救援效果）。
#
# 类别粒度不能太粗：曾经把 召回/诉讼/泄露/裁员 等全塞进一个"incident"大类，导致同一
# 实体下两件都属于"incident"但实际无关的不同事件（如"数据泄露"与"版权诉讼"）因为
# 类别集合有交集而被错误放行合并。拆成更细的子类，只有真正同类的事件才共享类别。
_EVENT_CATEGORY_TERMS = {
    "safety_recall": {
        "召回", "缺陷", "故障", "起火",
        "recall", "defect", "malfunction",
    },
    "legal": {
        "诉讼", "禁令", "调查", "处罚",
        "lawsuit", "sue", "ban", "investigation", "fine",  # "sue" 覆盖 sued/sues/suing
    },
    "security_incident": {
        "泄露", "崩溃",
        "breach", "crash",
    },
    "corporate_disruption": {
        "裁员", "停产",
        "layoff",
    },
    "release": {
        "发布", "推出", "更新", "升级", "上线", "新版",
        "release", "launch", "update", "upgrade", "unveil", "announce", "debut",
    },
}


def _event_categories(title):
    """标题命中的事件类别集合（可能为空，也可能同时属于多个类别）。"""
    low = title.lower()
    return {cat for cat, terms in _EVENT_CATEGORY_TERMS.items() if any(t in low for t in terms)}

# 形如"名词+数字"但并非产品名的常见组合，否则 "Part 4"/"Top 10" 会把无关文章并到一起
_ENTITY_STOPWORDS = frozenset({
    "part", "top", "day", "step", "vol", "figure", "table", "chapter", "section",
    "week", "year", "level", "phase", "round", "episode", "chapter", "note",
    "win", "ios", "gpu", "rtx", "cuda", "http", "api", "x86", "arm",
})


def _strong_entities(title):
    """从标题里抽取带版本号的产品/模型标识，归一化成 'gpt5.6' 这样的键。

    要求首字母大写：模型名在标题里几乎总是大写(GPT/Claude/Gemini/LongCat)，
    而 "part 4"、"step 2" 这类小写组合会被挡掉。
    """
    found = set()
    for name, version in _ENTITY_RE.findall(title):
        if not name[0].isupper():
            continue
        lowered = name.lower()
        if lowered in _ENTITY_STOPWORDS:
            continue
        found.add(f"{lowered}{version}")
    for brand, model in _BRAND_MODEL_RE.findall(title):
        if not brand[0].isupper():
            continue
        if model[0].lower() == "v":
            continue  # "Name v2" 这类 v 前缀版本号已经由 _ENTITY_RE 处理，避免重复实体
        lowered_brand = brand.lower()
        if lowered_brand in _ENTITY_STOPWORDS:
            continue
        found.add(f"{lowered_brand}{model.lower()}")
    return found


def _tokenize(text):
    text = text.lower()
    tokens = _WORD_RE.findall(text)
    cjk_chars = _CJK_RE.findall(text)
    for i in range(len(cjk_chars) - 1):
        tokens.append(cjk_chars[i] + cjk_chars[i + 1])
    return tokens


def _build_tfidf_vectors(texts):
    doc_tokens = [_tokenize(t) for t in texts]
    df = Counter()
    for tokens in doc_tokens:
        df.update(set(tokens))

    n_docs = len(texts)
    idf = {term: math.log((1 + n_docs) / (1 + count)) + 1 for term, count in df.items()}

    vectors = []
    for tokens in doc_tokens:
        tf = Counter(tokens)
        vec = {term: count * idf[term] for term, count in tf.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        vectors.append({term: v / norm for term, v in vec.items()})
    return vectors


def _cosine(vec_a, vec_b):
    # 用较短的向量遍历以减少运算量
    if len(vec_a) > len(vec_b):
        vec_a, vec_b = vec_b, vec_a
    return sum(v * vec_b.get(term, 0.0) for term, v in vec_a.items())


def _parse_iso(s):
    return datetime.fromisoformat(s)


def merge_stories(items, weights_config):
    if not items:
        return [], []

    window = timedelta(hours=weights_config["story_merge"]["window_hours"])
    threshold = weights_config["story_merge"]["similarity_threshold"]

    merge_by_entity = weights_config["story_merge"].get("merge_by_entity", True)

    items_sorted = sorted(items, key=lambda x: x["published_at"])
    texts = [f"{it['title']} {it['raw_text'][:200]}" for it in items_sorted]
    vectors = _build_tfidf_vectors(texts)
    entities = [_strong_entities(it["title"]) for it in items_sorted]
    categories = [_event_categories(it["title"]) for it in items_sorted]

    n = len(items_sorted)
    assigned = [-1] * n
    clusters = []

    for i in range(n):
        if assigned[i] != -1:
            continue
        cluster = [i]
        assigned[i] = len(clusters)
        # 时间窗对齐簇内"最近一条"而非种子（items 已按时间升序，最近一条即最后加入的那条）。
        # 否则一条早报道会把锚点拖到很前面，同一事件的后续报道超窗后另起一簇——
        # 实测 GPT-5.6 只差 10 小时的两条报道就因此被拆成两个故事。
        latest_t = _parse_iso(items_sorted[i]["published_at"])
        for j in range(i + 1, n):
            if assigned[j] != -1:
                continue
            t_j = _parse_iso(items_sorted[j]["published_at"])
            if t_j - latest_t > window:
                continue
            # 两条路径都算同一事件：措辞相近(词袋相似度)，或同一时间窗内谈同一个产品/模型
            # ——但共享实体只是"辅助"信号，若两条标题分别命中互斥的事件类别词（发布 vs 召回
            # 这类），说明是同一产品的两件不同事情，不该被判成同一故事。
            cosine = _cosine(vectors[i], vectors[j])
            same_event = cosine >= threshold
            if not same_event and merge_by_entity and (entities[i] & entities[j]):
                cats_i, cats_j = categories[i], categories[j]
                conflicting = bool(cats_i) and bool(cats_j) and not (cats_i & cats_j)
                same_event = not conflicting
            if same_event:
                assigned[j] = len(clusters)
                cluster.append(j)
                latest_t = t_j
        clusters.append(cluster)

    stories = []
    enriched_items = []
    for member_indices in clusters:
        members = [items_sorted[k] for k in member_indices]
        source_ids = {m["source_id"] for m in members}
        canonical = members[0]  # 已按时间排序，最早的为 canonical
        story_id = make_id("story", canonical["id"])

        stories.append(
            {
                "story_id": story_id,
                "canonical_title": canonical["title"],
                "first_seen": canonical["published_at"],
                "category": canonical.get("category"),
                "source_count": len(source_ids),
                "item_ids": [m["id"] for m in members],
            }
        )

        for m in members:
            m = dict(m)
            m["story_id"] = story_id
            m["multi_source_count"] = len(source_ids)
            m["sources"] = [
                {"source_id": mm["source_id"], "url": mm["url"]} for mm in members
            ]
            enriched_items.append(m)

    log.info("story_merge: %d items -> %d stories", n, len(stories))
    return enriched_items, stories


def collapse_stories(items):
    """同一 story 只保留一条代表，供展示流使用。

    merge_stories 会给同一事件的每条报道都打上相同 story_id 和 multi_source_count，
    但成员条目全部留在列表里。若直接拿去渲染，"GPT-5.6 发布"这类被多家同时报道的事件
    就会在信息流里重复出现好几张卡片。代表条目自带 sources 列表，前端的 ×N 徽章
    点开即可看到其余来源，信息并不丢失。

    代表 = 加权分最高的那条（分数相同取最早发布）：canonical 取的是最早那条，
    但最早未必是标题最清楚、来源最权威的一条。
    """
    def rank(item):
        # 分数高者优先；同分时取更早发布的（负号让"更早"排在前面）
        return (item.get("weighted_score") or 0, -_parse_iso(item["published_at"]).timestamp())

    best = {}
    for it in items:
        key = it.get("story_id") or it["id"]
        if key not in best or rank(it) > rank(best[key]):
            best[key] = it

    collapsed = list(best.values())
    if len(collapsed) < len(items):
        log.info("collapse_stories: %d items -> %d (每个故事只展示一条)", len(items), len(collapsed))
    return collapsed
