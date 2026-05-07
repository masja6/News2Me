from rapidfuzz import fuzz

from .fetch import Article

_SKIP_CLUSTERING = {"paper", "essay"}


def cluster(articles: list[Article], threshold: int) -> list[list[Article]]:
    """Group articles with near-duplicate titles using fuzzy match.

    Papers and essays are low-dup by nature — each becomes its own cluster.
    """
    clusters: list[list[Article]] = []
    for a in articles:
        if a.content_type in _SKIP_CLUSTERING:
            clusters.append([a])
            continue
        placed = False
        for c in clusters:
            if c[0].content_type in _SKIP_CLUSTERING:
                continue
            if fuzz.token_set_ratio(a.title, c[0].title) >= threshold:
                c.append(a)
                placed = True
                break
            if a.category == c[0].category and fuzz.partial_ratio(a.title, c[0].title) >= 70:
                c.append(a)
                placed = True
                break
        if not placed:
            clusters.append([a])
    return clusters


def cluster_representative(cluster: list[Article]) -> Article:
    """Pick the highest-trust article, breaking ties by content length."""
    return max(cluster, key=lambda a: (a.trust, len(a.content or "")))
