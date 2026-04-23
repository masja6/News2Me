import json
from datetime import datetime, timezone
from pathlib import Path
from .config import secrets

SUBSCRIBERS_PATH = Path("data/subscribers.json")
LOGS_PATH = Path("data/delivery_logs.json")

_mongo_db = None

def _get_db():
    global _mongo_db
    if _mongo_db is not None:
        return _mongo_db

    if secrets.mongodb_uri:
        from pymongo import MongoClient
        client = MongoClient(secrets.mongodb_uri)
        _mongo_db = client.get_default_database("newstome")
    else:
        _mongo_db = False
    
    return _mongo_db


def load_subscribers() -> list[dict]:
    db = _get_db()
    if db is not False:
        return list(db.get_collection("subscribers").find({}, {"_id": 0}))
    else:
        if not SUBSCRIBERS_PATH.exists():
            return []
        return json.loads(SUBSCRIBERS_PATH.read_text())


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
