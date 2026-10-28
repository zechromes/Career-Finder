"""Small-corpus lexical ranking and deterministic reciprocal rank fusion."""

import math
import re
from collections import Counter, defaultdict
from backend.search.embedding_text import profile_embedding_text


# Build distinct role, skills, and recent-work queries to capture different match signals.
def retrieval_queries(profile, target_roles=()):
    data = profile if isinstance(profile, dict) else profile.model_dump()
    focused = profile_embedding_text(data)
    queries = [str(role).strip() for role in target_roles if str(role).strip()]
    if data.get("tech_skills"):
        queries.append(" ".join(data["tech_skills"]))
    recent = (
        focused.partition("Recent work: ")[2]
        .split("\nTechnical skills:")[0]
        .split("\nPreferred domains:")[0]
    )
    if recent:
        queries.append(recent)
    if not queries and focused:
        queries.append(focused)
    return list(dict.fromkeys(queries))


def retrieval_query_weights(profile, target_roles=()):
    """Give role intent, skills and experience one vote each, regardless of role count."""
    data = profile if isinstance(profile, dict) else profile.model_dump()
    roles = list(
        dict.fromkeys(str(role).strip() for role in target_roles if str(role).strip())
    )
    background = retrieval_queries(data)
    skills = " ".join(data.get("tech_skills") or [])
    groups = [roles]
    if skills:
        groups.append([skills])
    recent = [query for query in background if query != skills]
    if recent:
        groups.append(recent)
    weights = defaultdict(float)
    for group in groups:
        for query in group:
            weights[query] += 1 / len(group)
    return dict(weights)


# Preserve punctuation that distinguishes technology names during lexical matching.
def tokens(text):
    # Preserve technology names such as C++, C#, .NET and Node.js.
    return re.findall(r"\.?[a-z0-9]+(?:[.+#-][a-z0-9+#]+|[+#]+)*", text.lower())


class BM25Index:
    """Reusable lexical statistics and inverted postings, preserving the BM25 formula."""

    def __init__(self, texts):
        documents = [Counter(tokens(text)) for text in texts]
        self.lengths = [sum(doc.values()) for doc in documents]
        self.average = sum(self.lengths) / max(1, len(self.lengths)) or 1
        self.count = len(documents)
        self.postings = defaultdict(list)
        for index, document in enumerate(documents):
            for term, count in document.items():
                self.postings[term].append((index, count))

    def rank(self, query, limit):
        scores = defaultdict(float)
        # Preserve the original term accumulation order and index tie-break.
        for term in set(tokens(query)):
            postings = self.postings.get(term, ())
            if not postings:
                continue
            idf = math.log(
                1 + (self.count - len(postings) + 0.5) / (len(postings) + 0.5)
            )
            for index, count in postings:
                scores[index] += (
                    idf
                    * count
                    * 2.5
                    / (count + 1.5 * (0.25 + 0.75 * self.lengths[index] / self.average))
                )
        return [
            index
            for index, score in sorted(
                scores.items(), key=lambda item: (-item[1], item[0])
            )
            if score > 0
        ][:limit]


def bm25_rank(texts, query, limit):
    """Compatibility helper for callers with a single query."""
    return BM25Index(texts).rank(query, limit)


# Combine rank positions so lexical and semantic scores need not share a scale.
def reciprocal_rank_fusion(rankings, limit, constant=60, weights=None):
    scores = defaultdict(float)
    if weights is not None and len(weights) != len(rankings):
        raise ValueError("One weight is required per ranking")
    for index, ranking in enumerate(rankings):
        for rank, key in enumerate(dict.fromkeys(ranking), 1):
            scores[key] += (weights[index] if weights is not None else 1) / (
                constant + rank
            )
    return sorted(scores, key=lambda key: (-scores[key], str(key)))[:limit]
