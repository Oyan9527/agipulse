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

    items_sorted = sorted(items, key=lambda x: x["published_at"])
    texts = [f"{it['title']} {it['raw_text'][:200]}" for it in items_sorted]
    vectors = _build_tfidf_vectors(texts)

    n = len(items_sorted)
    assigned = [-1] * n
    clusters = []

    for i in range(n):
        if assigned[i] != -1:
            continue
        cluster = [i]
        assigned[i] = len(clusters)
        t_i = _parse_iso(items_sorted[i]["published_at"])
        for j in range(i + 1, n):
            if assigned[j] != -1:
                continue
            t_j = _parse_iso(items_sorted[j]["published_at"])
            if abs(t_j - t_i) > window:
                continue
            if _cosine(vectors[i], vectors[j]) >= threshold:
                assigned[j] = len(clusters)
                cluster.append(j)
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
