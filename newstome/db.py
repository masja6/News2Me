import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from .config import secrets

SUBSCRIBERS_PATH = Path("data/subscribers.json")
LOGS_PATH = Path("data/delivery_logs.json")

logger = logging.getLogger(__name__)

_mongo_client = None
_mongo_db = None
_last_health_check = 0.0
_HEALTH_CHECK_INTERVAL = 60.0  # seconds


def _connect():
    """Create a fresh Mongo client. Returns (client, db) or (None, None)."""
    if not secrets.mongodb_uri:
        return None, None
    try:
        from pymongo import MongoClient
        client = MongoClient(secrets.mongodb_uri, serverSelectionTimeoutMS=3000)
        client.admin.command("ping")
        db = client.get_default_database("newstome")
        logger.info("MongoDB connected.")
        return client, db
    except Exception as e:
        logger.warning("MongoDB connect failed: %s — falling back to local JSON.", e)
        try:
            from .alerts import alert
            alert("MongoDB unavailable — using local JSON fallback", detail=str(e))
        except Exception:
            pass
        return None, None


def _get_db():
    """Return the active Mongo DB handle or False. Re-pings periodically so
    a transient outage doesn't wedge the cached client for the process lifetime."""
    global _mongo_client, _mongo_db, _last_health_check

    if not secrets.mongodb_uri:
        return False

    now = time.monotonic()
    if _mongo_db is not None and (now - _last_health_check) < _HEALTH_CHECK_INTERVAL:
        return _mongo_db

    if _mongo_client is not None:
        try:
            _mongo_client.admin.command("ping")
            _last_health_check = now
            return _mongo_db
        except Exception as e:
            logger.warning("MongoDB ping failed: %s — reconnecting.", e)
            try:
                _mongo_client.close()
            except Exception:
                pass
            _mongo_client = None
            _mongo_db = None

    client, db = _connect()
    _mongo_client = client
    _mongo_db = db if db is not None else False
    _last_health_check = now
    return _mongo_db


def load_subscribers(include_unsubscribed: bool = False) -> list[dict]:
    db = _get_db()
    if db is not False:
        q = {} if include_unsubscribed else {"unsubscribed": {"$ne": True}}
        return list(db.get_collection("subscribers").find(q, {"_id": 0}))
    else:
        if not SUBSCRIBERS_PATH.exists():
            return []
        subs = json.loads(SUBSCRIBERS_PATH.read_text())
        if include_unsubscribed:
            return subs
        return [s for s in subs if not s.get("unsubscribed")]


def set_unsubscribed(email: str) -> bool:
    db = _get_db()
    if db is not False:
        r = db.get_collection("subscribers").update_one(
            {"email": email}, {"$set": {"unsubscribed": True}}
        )
        return r.matched_count > 0
    else:
        if not SUBSCRIBERS_PATH.exists():
            return False
        subs = json.loads(SUBSCRIBERS_PATH.read_text())
        found = False
        for s in subs:
            if s.get("email") == email:
                s["unsubscribed"] = True
                found = True
        if found:
            SUBSCRIBERS_PATH.write_text(json.dumps(subs, indent=2))
        return found


def save_subscriber(data: dict) -> None:
    db = _get_db()
    if db is not False:
        email = data.get("email")
        if email:
            db.get_collection("subscribers").update_one({"email": email}, {"$set": data}, upsert=True)
    else:
        subs = load_subscribers()
        for i, s in enumerate(subs):
            if s.get("email") == data.get("email"):
                subs[i] = data
                break
        else:
            subs.append(data)
        SUBSCRIBERS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SUBSCRIBERS_PATH.write_text(json.dumps(subs, indent=2))


def save_delivery_log(user_email: str, summaries: list, tone: str, status: str = "success", error: str | None = None) -> None:
    log_entry = {
        "email": user_email,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tone": tone,
        "status": status,
        "error": error,
        "stories": [{"title": s.headline, "url": s.url, "category": s.category, "date": s.date} for s in summaries]
    }
    db = _get_db()
    if db is not False:
        db.get_collection("delivery_logs").insert_one(log_entry)
    else:
        logs = []
        if LOGS_PATH.exists():
            try:
                logs = json.loads(LOGS_PATH.read_text())
            except:
                pass
        logs.insert(0, log_entry)
        LOGS_PATH.write_text(json.dumps(logs[:100], indent=2))


def save_digest_archive(date_key: str, summaries: list[dict], title: str) -> None:
    """Persist a delivered digest so it can be rendered at /d/<date>."""
    payload = {
        "date": date_key,
        "title": title,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summaries": summaries,
    }
    db = _get_db()
    if db is not False:
        db.get_collection("digests").update_one(
            {"_id": date_key}, {"$set": payload}, upsert=True
        )
    else:
        archive_dir = Path("data/archive")
        archive_dir.mkdir(parents=True, exist_ok=True)
        (archive_dir / f"{date_key}.json").write_text(json.dumps(payload, indent=2))


def load_digest_archive(date_key: str) -> dict | None:
    db = _get_db()
    if db is not False:
        doc = db.get_collection("digests").find_one({"_id": date_key})
        if doc:
            doc.pop("_id", None)
            return doc
        return None
    path = Path("data/archive") / f"{date_key}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def list_digest_archive(limit: int = 30) -> list[dict]:
    db = _get_db()
    if db is not False:
        return list(
            db.get_collection("digests")
            .find({}, {"summaries": 0})
            .sort("_id", -1)
            .limit(limit)
        )
    archive_dir = Path("data/archive")
    if not archive_dir.exists():
        return []
    files = sorted(archive_dir.glob("*.json"), reverse=True)[:limit]
    out = []
    for f in files:
        try:
            d = json.loads(f.read_text())
            d.pop("summaries", None)
            out.append(d)
        except Exception:
            continue
    return out


def load_delivery_logs(limit: int = 20) -> list[dict]:
    db = _get_db()
    if db is not False:
        return list(db.get_collection("delivery_logs").find({}, {"_id": 0}).sort("timestamp", -1).limit(limit))
    else:
        if not LOGS_PATH.exists():
            return []
        try:
            return json.loads(LOGS_PATH.read_text())[:limit]
        except:
            return []


def log_click(email: str, category: str, url: str) -> None:
    """Logs a user click on a story category."""
    db = _get_db()
    if db is not False:
        db.get_collection("subscribers").update_one(
            {"email": email},
            {"$inc": {f"clicks.{category}": 1}},
            upsert=True
        )
    else:
        subs = load_subscribers()
        for s in subs:
            if s.get("email") == email:
                clicks = s.setdefault("clicks", {})
                clicks[category] = clicks.get(category, 0) + 1
                save_subscriber(s)
                break


def aggregate_clicks(limit_users: int = 200) -> dict:
    """Summarize click data across all subscribers. Returns totals and per-category counts."""
    subs = load_subscribers(include_unsubscribed=True)[:limit_users]
    total_users = len(subs)
    users_with_clicks = 0
    category_totals: dict[str, int] = {}
    top_users: list[dict] = []
    for s in subs:
        clicks = s.get("clicks", {}) or {}
        if not clicks:
            continue
        users_with_clicks += 1
        user_total = 0
        for cat, n in clicks.items():
            category_totals[cat] = category_totals.get(cat, 0) + int(n)
            user_total += int(n)
        top_users.append({"email": s.get("email", "?"), "total": user_total, "clicks": clicks})
    top_users.sort(key=lambda x: x["total"], reverse=True)
    grand_total = sum(category_totals.values())
    return {
        "total_users": total_users,
        "users_with_clicks": users_with_clicks,
        "grand_total": grand_total,
        "category_totals": dict(sorted(category_totals.items(), key=lambda x: -x[1])),
        "top_users": top_users[:10],
    }


def get_user_category_weights(email: str) -> dict[str, float]:
    """Returns category weights (boosts) based on click history."""
    db = _get_db()
    clicks = {}
    if db is not False:
        user = db.get_collection("subscribers").find_one({"email": email}, {"clicks": 1, "_id": 0})
        if user:
            clicks = user.get("clicks", {})
    else:
        subs = load_subscribers()
        for s in subs:
            if s.get("email") == email:
                clicks = s.get("clicks", {})
                break
    
    if not clicks:
        return {}
    
    # Calculate relative weights. Max boost of +50% (0.5)
    total_clicks = sum(clicks.values())
    if total_clicks == 0:
        return {}
    
    weights = {cat: (count / total_clicks) * 0.5 for cat, count in clicks.items()}
    return weights


def get_cached_summary(url: str, tone: str, jargon_busting: bool) -> dict | None:
    db = _get_db()
    cache_key = f"{url}:{tone}:{jargon_busting}"
    if db is not False:
        # Create TTL index if it doesn't exist (expires after 7 days = 604800 seconds)
        db.get_collection("summary_cache").create_index("created_at", expireAfterSeconds=604800)
        cached = db.get_collection("summary_cache").find_one({"_id": cache_key})
        return cached["summary_data"] if cached else None
    else:
        # Local JSON fallback
        cache_path = Path("data/summary_cache.json")
        if cache_path.exists():
            try:
                cache = json.loads(cache_path.read_text())
                return cache.get(cache_key)
            except:
                pass
        return None


def set_cached_summary(url: str, tone: str, jargon_busting: bool, summary_data: dict) -> None:
    db = _get_db()
    cache_key = f"{url}:{tone}:{jargon_busting}"
    if db is not False:
        db.get_collection("summary_cache").update_one(
            {"_id": cache_key},
            {"$set": {"summary_data": summary_data, "created_at": datetime.now(timezone.utc)}},
            upsert=True
        )
    else:
        cache_path = Path("data/summary_cache.json")
        cache = {}
        if cache_path.exists():
            try:
                cache = json.loads(cache_path.read_text())
            except:
                pass
        cache[cache_key] = summary_data
        cache_path.write_text(json.dumps(cache, indent=2))

def get_cache_stats() -> dict:
    """Returns total items in cache and estimated savings."""
    db = _get_db()
    if db is not False:
        count = db.get_collection("summary_cache").estimated_document_count()
        # Assume average 1500 tokens input, 200 output per saved call
        # Haiku 4.5: $1.00/1M in, $5.00/1M out
        saved_usd = count * (1500 * (1.00/1_000_000) + 200 * (5.00/1_000_000))
        return {"total_items": count, "lifetime_savings_usd": round(saved_usd, 2)}
    return {"total_items": 0, "lifetime_savings_usd": 0.0}
