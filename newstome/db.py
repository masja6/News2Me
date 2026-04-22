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


def save_delivery_log(user_email: str, summaries: list, tone: str) -> None:
    log_entry = {
        "email": user_email,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tone": tone,
        "stories": [{"title": s.headline, "url": s.url, "category": s.category} for s in summaries]
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
