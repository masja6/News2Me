from rapidfuzz import fuzz

from .fetch import Article


def cluster(articles: list[Article], threshold: int) -> list[list[Article]]:
    """Group articles with near-duplicate titles using fuzzy match."""
    clusters: list[list[Article]] = []
    for a in articles:
        placed = False
        for c in clusters:
            if fuzz.token_set_ratio(a.title, c[0].title) >= threshold:
                c.append(a)
                placed = True
                break
            # Also cluster on category + broad semantic similarity (lower bar, same category)
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
