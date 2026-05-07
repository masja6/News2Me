import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

import yaml
from fastapi import BackgroundTasks, Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from .config import CONFIG_PATH, load_config, save_config, secrets
from .pipeline import build_digest, build_user_digest, load_last_digest, prepare_clusters
from .telegram import send_digest as tg_send
from .email_send import send_email
from .auth import require_admin, verify_unsubscribe_token, create_session_token, verify_session_token

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="NewsToMe Admin")
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
def _ratelimit_handler(request: Request, exc: RateLimitExceeded):
    return HTMLResponse("Too many requests. Please try again in a moment.", status_code=429)


templates = Jinja2Templates(directory="templates")
from .db import (
    load_subscribers,
    save_subscriber,
    load_delivery_logs,
    log_click,
    set_unsubscribed,
    load_digest_archive,
    list_digest_archive,
    aggregate_clicks,
    get_cache_stats,
)


from .delivery import run_delivery_cycle


_running = False


# ── Auth & Session Helpers ──────────────────────────────────────────────────

def get_current_user(request: Request) -> str | None:
    token = request.cookies.get("session")
    if not token:
        return None
    return verify_session_token(token)

@app.post("/auth/google")
async def auth_google(request: Request):
    data = await request.json()
    token = data.get("credential")
    if not token:
        return JSONResponse({"error": "No token provided"}, status_code=400)
    
    try:
        idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), secrets.google_client_id)
        email = idinfo.get("email")
        if not email:
            return JSONResponse({"error": "No email in token"}, status_code=400)

        subs = load_subscribers()
        is_existing = any(s.get("email") == email for s in subs)

        session_token = create_session_token(email)
        response = JSONResponse({"success": True, "redirect": "/manage" if is_existing else "/onboard"})
        is_prod = secrets.app_url.startswith("https://")
        response.set_cookie(key="session", value=session_token, httponly=True, secure=is_prod, samesite="lax", max_age=86400 * 30)
        return response
    except ValueError as e:
        return JSONResponse({"error": f"Invalid token: {e}"}, status_code=400)
    except Exception as e:
        logger.exception("Unexpected error in /auth/google")
        return JSONResponse({"error": f"Server error: {e}"}, status_code=500)


@app.get("/logout")
def logout():
    response = RedirectResponse(url="/")
    response.delete_cookie("session")
    return response


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    user_email = get_current_user(request)
    if user_email:
        return RedirectResponse(url="/manage")
    return templates.TemplateResponse(request, "landing.html", {"google_client_id": secrets.google_client_id})


@app.get("/r")
@limiter.limit("60/minute")
async def track_redirect(request: Request, url: str, cat: str, u: str):
    """Tracks a click and redirects to the article."""
    if u:
        log_click(u, cat, url)
    return RedirectResponse(url)


@app.get("/d", response_class=HTMLResponse)
async def digest_index(request: Request):
    archives = list_digest_archive(60)
    return templates.TemplateResponse(request, "archive_index.html", {"archives": archives})


@app.get("/d/{date_key}", response_class=HTMLResponse)
async def digest_archive(request: Request, date_key: str):
    digest = load_digest_archive(date_key)
    if not digest:
        return HTMLResponse(
            f"<h2>No digest for {date_key}</h2>"
            "<p><a href='/d'>See recent digests</a></p>",
            status_code=404,
        )
    return templates.TemplateResponse(
        request, "archive.html", {"digest": digest, "date_key": date_key}
    )


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


@app.get("/onboard", response_class=HTMLResponse)
def onboard(request: Request):
    user_email = get_current_user(request)
    if not user_email:
        return RedirectResponse(url="/")
    return templates.TemplateResponse(request, "onboard.html", {"email": user_email})


@app.get("/edit", response_class=HTMLResponse)
def edit(request: Request):
    user_email = get_current_user(request)
    if not user_email:
        return RedirectResponse(url="/")
    subs = load_subscribers()
    user_data = next((s for s in subs if s.get("email") == user_email), None)
    if not user_data:
        return RedirectResponse(url="/onboard")
    return templates.TemplateResponse(request, "edit.html", {"user": user_data, "user_json": json.dumps(user_data)})


@app.get("/manage", response_class=HTMLResponse)
def manage(request: Request):
    user_email = get_current_user(request)
    if not user_email:
        return RedirectResponse(url="/")
    
    subs = load_subscribers()
    user_data = next((s for s in subs if s.get("email") == user_email), None)
    if not user_data:
        # If somehow they have a session but no DB entry, redirect to onboard
        return RedirectResponse(url="/onboard")

    from .auth import unsubscribe_token
    user_data["token"] = unsubscribe_token(user_email)

    latest_digest = None
    archives = list_digest_archive(limit=1)
    if archives:
        latest_digest = load_digest_archive(archives[0].get("_id") or archives[0].get("date"))

    return templates.TemplateResponse(request, "manage.html", {"user": user_data, "latest": latest_digest})


@app.post("/subscribe")
@limiter.limit("5/minute")
async def subscribe(request: Request, background: BackgroundTasks):
    user_email = get_current_user(request)
    if not user_email:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
        
    data = await request.json()
    data["email"] = user_email
    data["setup_complete"] = True

    subs = load_subscribers()
    existing = next((s for s in subs if s.get("email") == user_email), None)
    is_new = existing is None

    if is_new:
        data["created_at"] = datetime.now(timezone.utc).isoformat()
    else:
        # Preserve locked fields and original metadata on edit
        data["name"] = existing.get("name", data.get("name", ""))
        data["created_at"] = existing.get("created_at")
        if "clicks" in existing:
            data["clicks"] = existing["clicks"]

    save_subscriber(data)
    
    # Trigger first digest immediately if new
    if is_new:
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


@app.get("/archive", response_class=HTMLResponse)
def archive(request: Request):
    digests = list_digest_archive(limit=50)
    return templates.TemplateResponse(request, "archive.html", {
        "digests": digests,
    })


@app.get("/d/{date_key}", response_class=HTMLResponse)
def view_digest(request: Request, date_key: str):
    digest = load_digest_archive(date_key)
    if not digest:
        return HTMLResponse("Digest not found", status_code=404)
    
    # Format the date for display
    try:
        dt = datetime.fromisoformat(digest["date"])
        display_date = dt.strftime("%B %d, %Y")
    except:
        display_date = digest["date"]

    return templates.TemplateResponse(request, "digest_view.html", {
        "digest": digest,
        "display_date": display_date,
    })


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

    # Run metrics (cache hit rate, token spend) from last digest
    metrics = last.get("metrics") if last else None

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
        "click_stats": aggregate_clicks(),
        "metrics": metrics,
        "cache_stats": get_cache_stats(),
    })


@app.post("/admin/save")
def admin_save(yaml_text: str = Form(...), _: str = Depends(require_admin)):
    try:
        yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        return HTMLResponse(f"YAML error: {e}", status_code=400)
    CONFIG_PATH.write_text(yaml_text)
    return RedirectResponse("/admin?saved=1", status_code=303)


@app.post("/cron/deliver")
async def cron_deliver(request: Request, background: BackgroundTasks):
    """Called by GitHub Actions every hour. Protected by CRON_SECRET token."""
    token = request.headers.get("X-Cron-Secret", "")
    if not secrets.cron_secret or token != secrets.cron_secret:
        return HTMLResponse("Unauthorized", status_code=401)
    global _running
    if _running:
        return {"status": "already_running"}
    _running = True
    background.add_task(_do_run)
    return {"status": "started"}


@app.post("/admin/run")
async def admin_run(background: BackgroundTasks, _: str = Depends(require_admin)):
    """Preview-only: generates a digest and saves it for admin viewing.
    Does NOT send to any subscribers."""
    global _running
    if _running:
        return RedirectResponse("/admin", status_code=303)
    _running = True
    background.add_task(_do_preview_run)
    return RedirectResponse("/admin?ran=1", status_code=303)


def _do_preview_run() -> None:
    """Fetch → classify → rank → summarize → save. No delivery."""
    global _running
    try:
        ranked = prepare_clusters(verbose=True)
        if not ranked:
            print("Admin run: no stories found.")
            return
        cfg = load_config()
        summaries, report = build_user_digest(
            ranked, {"max_items": cfg.ranking.max_items}, verbose=True
        )
        if summaries:
            from dataclasses import asdict
            date_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            from .db import save_digest_archive
            save_digest_archive(
                date_key,
                [asdict(s) for s in summaries],
                title=cfg.telegram.digest_title,
            )
            print(f"Admin run: {len(summaries)} stories generated and archived for {date_key}.")
    except Exception as e:
        print(f"Admin run failed: {e}")
    finally:
        _running = False


@app.post("/admin/deliver")
async def admin_deliver(background: BackgroundTasks, _: str = Depends(require_admin)):
    """Actually send the digest to all subscribers. Separate from preview."""
    global _running
    if _running:
        return RedirectResponse("/admin", status_code=303)
    _running = True
    background.add_task(_do_deliver)
    return RedirectResponse("/admin?delivered=1", status_code=303)


def _do_deliver() -> None:
    global _running
    try:
        run_delivery_cycle(verbose=True)
    finally:
        _running = False


@app.post("/admin/backfill")
async def admin_backfill(background: BackgroundTasks, _: str = Depends(require_admin)):
    """Generate a digest for today and archive it without sending."""
    global _running
    if _running:
        return RedirectResponse("/admin", status_code=303)
    _running = True
    background.add_task(_do_preview_run)
    return RedirectResponse("/admin?backfilled=1", status_code=303)
