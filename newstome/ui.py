import json
from datetime import datetime, timezone
from pathlib import Path

import yaml
from fastapi import BackgroundTasks, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .config import CONFIG_PATH, load_config, save_config, secrets
from .pipeline import build_digest, build_user_digest, load_last_digest, prepare_clusters
from .telegram import send_digest as tg_send
from .email_send import send_email

app = FastAPI(title="NewsToMe Admin")
templates = Jinja2Templates(directory="templates")
from .db import load_subscribers, save_subscriber


_running = False


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "onboard.html")


@app.post("/subscribe")
async def subscribe(request: Request):
    data = await request.json()
    data["setup_complete"] = True
    data["created_at"] = datetime.now(timezone.utc).isoformat()
    save_subscriber(data)
    return {"status": "ok"}


@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request):
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
    })


@app.post("/admin/save")
def admin_save(yaml_text: str = Form(...)):
    try:
        yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        return HTMLResponse(f"YAML error: {e}", status_code=400)
    CONFIG_PATH.write_text(yaml_text)
    return RedirectResponse("/admin?saved=1", status_code=303)


@app.post("/admin/run")
async def admin_run(background: BackgroundTasks):
    global _running
    if _running:
        return RedirectResponse("/admin", status_code=303)
    _running = True
    background.add_task(_do_run)
    return RedirectResponse("/admin", status_code=303)


def _do_run() -> None:
    global _running
    try:
        cfg = load_config()
        ranked = prepare_clusters(verbose=True)
        if not ranked:
            return
            
        title = cfg.telegram.digest_title
        if "telegram" in cfg.delivery.channels:
            summaries, _ = build_user_digest(ranked, {}, verbose=True)
            if summaries:
                tg_send(summaries, title=title)
                
        if "email" in cfg.delivery.channels and secrets.gmail_address and secrets.gmail_app_password:
            subs = load_subscribers()
            if cfg.delivery.email_to:
                summaries, _ = build_user_digest(ranked, {}, verbose=True)
                if summaries:
                    send_email(summaries, title=title, to=cfg.delivery.email_to)
            elif subs:
                for sub in subs:
                    print(f"  → Generating configured digest for {sub.get('email')}...")
                    sub_sums, _ = build_user_digest(ranked, sub, verbose=True)
                    if sub_sums:
                        send_email(sub_sums, title=title, to=sub["email"])
            else:
                summaries, _ = build_user_digest(ranked, {}, verbose=True)
                if summaries:
                    send_email(summaries, title=title)
    finally:
        _running = False
