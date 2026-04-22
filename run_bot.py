"""Long-running Telegram bot. Listens for /digest, /status, /start."""
from newstome.bot import build_app


def main() -> None:
    app = build_app()
    print("Bot running. Send /digest in Telegram. Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
