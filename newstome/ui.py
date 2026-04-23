import json
from datetime import datetime, timezone
from pathlib import Path

import yaml
from fastapi import BackgroundTasks, Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .config import CONFIG_PATH, load_config, save_config, secrets
from .pipeline import build_digest, build_user_digest, load_last_digest, prepare_clusters
from .telegram import send_digest as tg_send
from .email_send import send_email
from .auth import require_admin, verify_unsubscribe_token

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="NewsToMe Admin")
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
def _ratelimit_handler(request: Request, exc: RateLimitExceeded):
    return HTMLResponse("Too many requests. Please try again in a moment.", status_code=429)


templates = Jinja2Templates(directory="templates")
from .db import load_subscribers, save_subscriber, load_delivery_logs, log_click, set_unsubscribed


from .delivery import run_delivery_cycle


_running = False


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "onboard.html")


@app.get("/r")
@limiter.limit("60/minute")
async def track_redirect(request: Request, url: str, cat: str, u: str):
    """Tracks a click and redirects to the article."""
    if u:
        log_click(u, cat, url)
    return RedirectResponse(url)


@app.get("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe(u: str, t: str):
    if not verify_unsubscribe_token(u, t):
        return HTMLResponse(
            "<h2>Invalid unsubscribe link</h2><p>This link is malformed or expired. "
            "Please reply to any digest email and we'll remove you manually.</p>",
            status_code=400,
        )
    found = set_unsubscribed(u)
    if found:
        msg = f"<h2>Unsubscribed</h2><p>{u} will no longer receive NewsToMe digests.</p>"
    else:
        msg = f"<h2>Not found</h2><p>{u} is not a current subscriber.</p>"
    return HTMLResponse(
        f"<!doctype html><html><body style='font-family:-apple-system,sans-serif;"
        f"max-width:520px;margin:80px auto;padding:0 24px;color:#111'>{msg}"
        f"<p style='color:#666;font-size:13px;margin-top:24px'>NewsToMe · Shelby Co.</p>"
        f"</body></html>"
    )


@app.post("/subscribe")
@limiter.limit("5/minute")
async def subscribe(request: Request, background: BackgroundTasks):
    data = await request.json()
    data["setup_complete"] = True
    data["created_at"] = datetime.now(timezone.utc).isoformat()
    save_subscriber(data)
    
    # Trigger first digest immediately
    background.add_task(_send_welcome_digest, data)
    
    return {"status": "ok"}


def _send_welcome_digest(user: dict) -> None:
    """Generates and sends the first digest immediately to a new subscriber."""
    try:
        print(f"🚀 Generating welcome digest for {user.get('email')}...")
        cfg = load_config()
        
        # 1. Fetch fresh clusters
        ranked = prepare_clusters(verbose=True)
        if not ranked:
            print("  ! No stories found for welcome digest.")
            return

        # 2. Build personalized summary
        summaries, _ = build_user_digest(ranked, user, verbose=True)
        
        # 3. Send via Email
        if summaries and secrets.gmail_address and secrets.gmail_app_password:
            title = f"Welcome to {cfg.telegram.digest_title}!"
            send_email(summaries, title=title, to=user["email"])
            print(f"  ✓ Welcome digest sent to {user.get('email')}")
    except Exception as e:
        print(f"  ❌ Failed to send welcome digest: {e}")


@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request, _: str = Depends(require_admin)):
    subscribers = load_subscribers()
    cfg = load_config()
    last = load_last_digest()

    # Digest data
    summaries = last.get("summaries", []) if last else []
    last_generated = ""
    if last:
        try:
            dt = datetime.fromisoformat(last["generated_at"])
            last_generated = dt.strftime("%d %b %Y, %I:%M %p UTC")
        except Exception:
            last_generated = last.get("generated_at", "")

    # QC data
    qc = last.get("qc") if last else None
    qc_ok = qc.get("ok", True) if qc else True
    qc_issues = qc.get("issues", []) if qc else []
    category_counts = qc.get("category_counts", {}) if qc else {}

    # Ranking params for display
    ranking_dict = cfg.ranking.model_dump()

    return templates.TemplateResponse(request, "admin.html", {
        "subscribers": subscribers,
        "running": _running,
        "feeds": cfg.feeds,
        "ranking": ranking_dict,
        "channels": cfg.delivery.channels,
        "email_to": cfg.delivery.email_to or secrets.gmail_address,
        "yaml_text": CONFIG_PATH.read_text(),
        "summaries": summaries,
        "story_count": len(summaries),
        "last_generated": last_generated,
        "qc": qc,
        "qc_ok": qc_ok,
        "qc_issues": qc_issues,
        "category_counts": category_counts,
        "delivery_logs": load_delivery_logs(20),
    })


@app.post("/admin/save")
def admin_save(yaml_text: str = Form(...), _: str = Depends(require_admin)):
    try:
        yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        return HTMLResponse(f"YAML error: {e}", status_code=400)
    CONFIG_PATH.write_text(yaml_text)
    return RedirectResponse("/admin?saved=1", status_code=303)


@app.post("/admin/run")
async def admin_run(background: BackgroundTasks, _: str = Depends(require_admin)):
    global _running
    if _running:
        return RedirectResponse("/admin", status_code=303)
    _running = True
    background.add_task(_do_run)
    return RedirectResponse("/admin", status_code=303)


def _do_run() -> None:
    global _running
    try:
        run_delivery_cycle(verbose=True)
    finally:
        _running = False
