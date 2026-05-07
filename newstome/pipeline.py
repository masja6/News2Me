import json
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .classify import classify_articles
from .cluster import cluster, cluster_representative
from .config import load_config, secrets
from .dedupe import filter_unseen, mark_seen
from .fetch import Article, fetch_all
from .qc import QcReport, check
from .rank import RankedCluster, enforce_diversity, rank
from .summarize import Summary, summarize, reset_metrics, get_metrics
from .db import save_delivery_log, get_user_category_weights, save_digest_archive, get_tracked_ids
from . import observe
from .sources.arxiv import fetch_arxiv
from .sources.blogs import fetch_blogs
from .sources.pypi import fetch_pypi_npm
from .sources.huggingface import fetch_huggingface
from .sources.github import fetch_github_trending, fetch_github_releases

LAST_DIGEST_PATH = Path("data/last_digest.json")


def prepare_clusters(verbose: bool = True) -> list[RankedCluster]:
    cfg = load_config()
    log = print if verbose else (lambda *a, **k: None)
    reset_metrics()
    observe.start_trace("digest_run")

    log(f"Fetching {len(cfg.feeds)} RSS feeds...")
    articles = fetch_all(cfg.feeds)
    log(f"  {len(articles)} articles from RSS feeds")

    ai_sources: list[tuple[str, callable]] = [
        ("arXiv", fetch_arxiv),
        ("blogs/Substack", fetch_blogs),
        ("PyPI/npm", fetch_pypi_npm),
        ("Hugging Face", fetch_huggingface),
        ("GitHub trending", fetch_github_trending),
        ("GitHub releases", fetch_github_releases),
    ]
    for source_name, fetcher in ai_sources:
        try:
            batch = fetcher()
            log(f"  {len(batch)} from {source_name}")
            articles.extend(batch)
        except Exception as e:
            log(f"  {source_name} failed: {e}")

    log(f"  {len(articles)} total articles fetched")

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

    user_cats = set(
        user.get("india_categories", [])
        + user.get("global_categories", [])
        + user.get("ai_categories", [])
    )
    if user_cats:
        user_ranked = [rc for rc in ranked if rc.articles[0].category in user_cats]
    else:
        user_ranked = ranked

    # Keyword following: boost clusters matching subscriber keywords to top
    keywords = [kw.strip().lower() for kw in user.get("keywords", []) if kw.strip()]
    if keywords:
        def _keyword_match(rc: RankedCluster) -> bool:
            text = " ".join(a.title.lower() for a in rc.articles)
            return any(kw in text for kw in keywords)
        keyword_hits = [rc for rc in user_ranked if _keyword_match(rc)]
        rest = [rc for rc in user_ranked if not _keyword_match(rc)]
        user_ranked = keyword_hits + rest
        log(f"  {len(keyword_hits)} keyword-matched clusters boosted to top ({keywords})")

    # Personalization: Re-rank based on user click history + trackers
    email = user.get("email")
    tracked_ids = get_tracked_ids(user)
    if email:
        weights = get_user_category_weights(email)
        if weights or tracked_ids:
            log(f"  Applying personalized boosts for {email}: {weights}")
            raw_clusters = [rc.articles for rc in user_ranked]
            user_ranked = rank(raw_clusters, cfg.ranking, category_boosts=weights, tracked_ids=tracked_ids)
    elif tracked_ids:
        raw_clusters = [rc.articles for rc in user_ranked]
        user_ranked = rank(raw_clusters, cfg.ranking, tracked_ids=tracked_ids)

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
        if not user.get("email"):
            date_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            save_digest_archive(date_key, [asdict(s) for s in summaries],
                                title=cfg.telegram.digest_title)

    observe.end_trace()
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
        "metrics": get_metrics(),
    }, indent=2))


def load_last_digest() -> dict | None:
    if not LAST_DIGEST_PATH.exists():
        return None
    return json.loads(LAST_DIGEST_PATH.read_text())
