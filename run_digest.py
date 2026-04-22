"""One-shot: build today's digest and deliver to all enabled channels."""
from newstome.config import load_config, secrets
from newstome.email_send import send_email
from newstome.pipeline import build_user_digest, prepare_clusters
from newstome.telegram import send_digest


def main() -> None:
    cfg = load_config()
    ranked = prepare_clusters()
    if not ranked:
        print("Nothing to send.")
        return

    channels = cfg.delivery.channels
    title = cfg.telegram.digest_title

    if "telegram" in channels:
        print("  → Telegram (Global Default)")
        summaries, _ = build_user_digest(ranked, {})
        if summaries:
            send_digest(summaries, title=title)

    if "email" in channels:
        if not secrets.gmail_address or not secrets.gmail_app_password:
            print("  → Email: skipped (GMAIL_ADDRESS or GMAIL_APP_PASSWORD not set)")
        else:
            if cfg.delivery.email_to:
                print(f"  → Email to {cfg.delivery.email_to} (config override)")
                summaries, _ = build_user_digest(ranked, {})
                if summaries:
                    send_email(summaries, title=title, to=cfg.delivery.email_to)
            else:
                from newstome.db import load_subscribers
                subs = load_subscribers()
                
                if subs:
                    for sub in subs:
                        print(f"  → Generating configured digest for {sub.get('email')}... ({sub.get('tone', 'Standard')} tone, Jargon: {sub.get('jargon_busting', False)})")
                        sub_sums, _ = build_user_digest(ranked, sub)
                        if sub_sums:
                            send_email(sub_sums, title=title, to=sub["email"])
                else:
                    print("  → Email to secrets dummy via BCC (Global Default)")
                    summaries, _ = build_user_digest(ranked, {})
                    if summaries:
                        send_email(summaries, title=title)

    print("Done.")


if __name__ == "__main__":
    main()
