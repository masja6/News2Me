import json
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .classify import classify_articles
from .cluster import cluster, cluster_representative
from .config import load_config
from .dedupe import filter_unseen, mark_seen
from .fetch import fetch_all
from .qc import QcReport, check
from .rank import RankedCluster, enforce_diversity, rank
from .summarize import Summary, summarize

LAST_DIGEST_PATH = Path("data/last_digest.json")


def prepare_clusters(verbose: bool = True) -> list[RankedCluster]:
    cfg = load_config()
    log = print if verbose else (lambda *a, **k: None)

    log(f"Fetching {len(cfg.feeds)} feeds...")
    articles = fetch_all(cfg.feeds)
    log(f"  {len(articles)} articles fetched")

    unseen = set(filter_unseen([a.url for a in articles]))
    articles = [a for a in articles if a.url in unseen]
    log(f"  {len(articles)} new after URL dedupe")

    if cfg.categories and articles:
        log(f"Classifying {len(articles)} articles into {len(cfg.categories)} categories...")
        articles = classify_articles(articles, cfg.categories)
        cat_dist = {}
        for a in articles:
            cat_dist[a.category] = cat_dist.get(a.category, 0) + 1
        log(f"  distribution: {cat_dist}")

    clusters = cluster(articles, cfg.ranking.dedupe_similarity)
    log(f"  {len(clusters)} clusters after similarity grouping")

    ranked = rank(clusters, cfg.ranking)
    return ranked


def build_user_digest(ranked: list[RankedCluster], user: dict, verbose: bool = True) -> tuple[list[Summary], QcReport | None]:
    cfg = load_config()
    log = print if verbose else (lambda *a, **k: None)

    user_cats = set(user.get("india_categories", []) + user.get("global_categories", []))
    if user_cats:
        user_ranked = [rc for rc in ranked if rc.articles[0].category in user_cats]
    else:
        user_ranked = ranked

    max_items = user.get("max_items", cfg.ranking.max_items)
    tone = user.get("tone", "Standard")
    jargon = user.get("jargon_busting", False)

    selected = enforce_diversity(user_ranked, cfg.ranking.per_category_max, max_items, cfg.ranking.per_region_max)
    log(f"  {len(selected)} top clusters after diversity caps for {user.get('email', 'global')}")

    if not selected:
        return [], None

    log(f"Summarizing (Tone: {tone}, Jargon: {jargon})...")
    summaries: list[Summary] = []
    for rc in selected:
        rep = cluster_representative(rc.articles)
        if not rep.content or len(rep.content) < 200:
            log(f"  skip (thin content): {rep.title[:60]}")
            continue
        if summaries:
            time.sleep(cfg.summarizer.request_delay_sec)
        try:
            s = summarize(rep, cfg.summarizer, tone=tone, jargon_busting=jargon)
        except Exception as e:
            log(f"  summarize failed ({type(e).__name__}); stopping with {len(summaries)} stories")
            break
        summaries.append(s)
        log(f"  [{len(summaries)}] ({s.category}) {s.headline}")

    log("Running QC checks...")
    report = check(summaries, min_categories=cfg.qc.min_categories)
    for issue in report.issues:
        log(f"  [{issue.severity}] {issue.message}")

    if summaries:
        mark_seen([s.url for s in summaries])
        _save_last_digest(summaries, report)
    return summaries, report


def build_digest(verbose: bool = True) -> tuple[list[Summary], QcReport | None]:
    ranked = prepare_clusters(verbose)
    cfg = load_config()
    return build_user_digest(ranked, {"max_items": cfg.ranking.max_items}, verbose)


def _save_last_digest(summaries: list[Summary], report: QcReport | None) -> None:
    LAST_DIGEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAST_DIGEST_PATH.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summaries": [asdict(s) for s in summaries],
        "qc": {
            "issues": [asdict(i) for i in report.issues] if report else [],
            "category_counts": report.category_counts if report else {},
            "ok": report.ok if report else True,
        },
    }, indent=2))


def load_last_digest() -> dict | None:
    if not LAST_DIGEST_PATH.exists():
        return None
    return json.loads(LAST_DIGEST_PATH.read_text())
