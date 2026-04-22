import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

SEEN_FILE = Path("data/seen.json")
TTL_DAYS = 7


def _hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> dict[str, str]:
    if not SEEN_FILE.exists():
        return {}
    return json.loads(SEEN_FILE.read_text())


def _save(seen: dict[str, str]) -> None:
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(seen, indent=2))


def _prune(seen: dict[str, str]) -> dict[str, str]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=TTL_DAYS)
    return {k: v for k, v in seen.items() if datetime.fromisoformat(v) > cutoff}


def filter_unseen(urls: list[str]) -> list[str]:
    seen = _prune(_load())
    _save(seen)
    return [u for u in urls if _hash(u) not in seen]


def mark_seen(urls: list[str]) -> None:
    seen = _load()
    now = _now()
    for u in urls:
        seen[_hash(u)] = now
    _save(seen)
