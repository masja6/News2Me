from dataclasses import dataclass

from rapidfuzz import fuzz

from .summarize import Summary


@dataclass
class QcIssue:
    severity: str  # "warn" | "error"
    url: str | None
    message: str


@dataclass
class QcReport:
    issues: list[QcIssue]
    category_counts: dict[str, int]

    @property
    def ok(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)


def check(summaries: list[Summary], min_categories: int = 3) -> QcReport:
    issues: list[QcIssue] = []

    for s in summaries:
        headline_words = len(s.headline.split())
        body_words = len(s.body.split())

        if headline_words < 5 or headline_words > 12:
            issues.append(QcIssue(
                "warn", s.url,
                f"headline has {headline_words} words (want 6-10): {s.headline!r}",
            ))

        if body_words < 28 or body_words > 45:
            issues.append(QcIssue(
                "warn", s.url,
                f"body has {body_words} words (want 30-40)",
            ))

        if not s.body.strip():
            issues.append(QcIssue("error", s.url, "empty body"))

    for i, a in enumerate(summaries):
        for b in summaries[i + 1:]:
            if fuzz.token_set_ratio(a.headline, b.headline) > 75:
                issues.append(QcIssue(
                    "warn", b.url,
                    f"near-duplicate of earlier story: {a.headline!r}",
                ))

    category_counts: dict[str, int] = {}
    for s in summaries:
        category_counts[s.category] = category_counts.get(s.category, 0) + 1

    if summaries and len(category_counts) < min_categories:
        issues.append(QcIssue(
            "warn", None,
            f"only {len(category_counts)} categories in digest (want ≥{min_categories}): {category_counts}",
        ))

    max_in_one = max(category_counts.values()) if category_counts else 0
    if summaries and max_in_one / len(summaries) > 0.6:
        top = max(category_counts, key=category_counts.get)
        issues.append(QcIssue(
            "warn", None,
            f"category '{top}' is {max_in_one}/{len(summaries)} stories (>60%, too skewed)",
        ))

    return QcReport(issues=issues, category_counts=category_counts)
