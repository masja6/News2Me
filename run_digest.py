"""One-shot: build today's digest and deliver to all enabled channels."""
from newstome.config import load_config, secrets
from newstome.email_send import send_email
from newstome.pipeline import build_digest
from newstome.telegram import send_digest


def deliver(summaries, cfg) -> None:
    title = cfg.telegram.digest_title
    channels = cfg.delivery.channels

    if "telegram" in channels:
        print("  → Telegram")
        send_digest(summaries, title=title)

    if "email" in channels:
        if not secrets.gmail_address or not secrets.gmail_app_password:
            print("  → Email: skipped (GMAIL_ADDRESS or GMAIL_APP_PASSWORD not set)")
        else:
            to = cfg.delivery.email_to or secrets.gmail_address
            print(f"  → Email to {to}")
            send_email(summaries, title=title, to=to)


def main() -> None:
    cfg = load_config()
    summaries, report = build_digest()
    if not summaries:
        print("Nothing to send.")
        return
    print(f"Delivering {len(summaries)} stories via: {cfg.delivery.channels}")
    deliver(summaries, cfg)
    if report and not report.ok:
        print("QC errors — check admin UI for details.")
    print("Done.")


if __name__ == "__main__":
    main()
