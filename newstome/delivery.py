from .config import load_config, secrets
from .pipeline import prepare_clusters, build_user_digest
from .db import load_subscribers, save_delivery_log
from .email_send import send_email
from .telegram import send_digest

def run_delivery_cycle(verbose: bool = True) -> None:
    """Orchestrates a full fetch-summarize-deliver cycle for all users."""
    cfg = load_config()
    log = print if verbose else (lambda *a, **k: None)

    log("Starting delivery cycle...")
    ranked = prepare_clusters(verbose)
    if not ranked:
        log("No new stories found. Cycle complete.")
        return

    channels = cfg.delivery.channels
    title = cfg.telegram.digest_title

    # 1. Telegram (Global Default)
    if "telegram" in channels:
        log("Sending Telegram digest...")
        summaries, _ = build_user_digest(ranked, {}, verbose)
        if summaries:
            send_digest(summaries, title=title)

    # 2. Email (Per-user or Default)
    if "email" in channels:
        if not secrets.gmail_address or not secrets.gmail_app_password:
            log("Email skipped: GMAIL_ADDRESS or GMAIL_APP_PASSWORD not set")
        else:
            if cfg.delivery.email_to:
                log(f"Email override: {cfg.delivery.email_to}")
                summaries, _ = build_user_digest(ranked, {}, verbose)
                if summaries:
                    ok, err = send_email(summaries, title=title, to=cfg.delivery.email_to)
                    save_delivery_log(cfg.delivery.email_to, summaries, "Standard", 
                                      status="success" if ok else "fail", error=err)
            else:
                subs = load_subscribers()
                if subs:
                    for sub in subs:
                        email = sub.get("email")
                        if not email: continue
                        log(f"Processing user: {email}")
                        summaries, _ = build_user_digest(ranked, sub, verbose)
                        if summaries:
                            ok, err = send_email(summaries, title=title, to=email)
                            save_delivery_log(email, summaries, sub.get("tone", "Standard"),
                                              status="success" if ok else "fail", error=err)
                else:
                    log("No subscribers found. Sending to default address.")
                    summaries, _ = build_user_digest(ranked, {}, verbose)
                    if summaries:
                        ok, err = send_email(summaries, title=title)
                        save_delivery_log(secrets.gmail_address, summaries, "Standard",
                                          status="success" if ok else "fail", error=err)
    log("Delivery cycle complete.")
