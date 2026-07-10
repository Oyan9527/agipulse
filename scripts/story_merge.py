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
_ENTITY_RE = re.compile(r"([A-Za-z][A-Za-z]{2,})[\s\-]?(\d+(?:\.\d+)?)")

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
            same_event = _cosine(vectors[i], vectors[j]) >= threshold
            if not same_event and merge_by_entity and (entities[i] & entities[j]):
                same_event = True
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
