import json
from pathlib import Path
from .config import secrets

SUBSCRIBERS_PATH = Path("data/subscribers.json")

_mongo_collection = None

def _get_collection():
    global _mongo_collection
    if _mongo_collection is not None:
        return _mongo_collection

    if secrets.mongodb_uri:
        from pymongo import MongoClient
        client = MongoClient(secrets.mongodb_uri)
        # Use default DB from URI, fallback to 'newstome' if URI doesn't specify one
        db = client.get_default_database("newstome")
        _mongo_collection = db.get_collection("subscribers")
    else:
        _mongo_collection = False
    
    return _mongo_collection


def load_subscribers() -> list[dict]:
    coll = _get_collection()
    if coll is not False:
        return list(coll.find({}, {"_id": 0}))
    else:
        if not SUBSCRIBERS_PATH.exists():
            return []
        return json.loads(SUBSCRIBERS_PATH.read_text())


def save_subscriber(data: dict) -> None:
    coll = _get_collection()
    if coll is not False:
        email = data.get("email")
        if email:
            coll.update_one({"email": email}, {"$set": data}, upsert=True)
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
