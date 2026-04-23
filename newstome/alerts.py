"""Operational alerts — sent to the admin via Telegram on failures.

Keep this module side-effect-free on import. Never raise from `alert()`;
a broken alert path must not take down the caller.
"""
import html
import logging
import traceback

import httpx

from .config import secrets

logger = logging.getLogger(__name__)
API = "https://api.telegram.org/bot{token}/sendMessage"


def alert(title: str, detail: str = "", exc: BaseException | None = None) -> None:
    """Send an operational alert to the admin. Never raises."""
    target = secrets.alert_chat_id or secrets.telegram_chat_id
    token = secrets.telegram_bot_token
    if not (token and target):
        logger.warning("alert() skipped: no Telegram chat configured. %s — %s", title, detail)
        return

    body = f"🚨 <b>{html.escape(title)}</b>"
    if detail:
        body += f"\n{html.escape(detail)}"
    if exc is not None:
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        body += f"\n<pre>{html.escape(tb[-1500:])}</pre>"

    try:
        httpx.post(
            API.format(token=token),
            json={"chat_id": target, "text": body, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=10,
        )
    except Exception as e:
        logger.error("alert delivery failed: %s", e)
