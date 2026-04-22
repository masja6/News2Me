import html

import httpx

from .config import secrets
from .summarize import Summary

API = "https://api.telegram.org/bot{token}/sendMessage"
MAX_LEN = 4000


def format_digest(summaries: list[Summary], title: str) -> str:
    parts = [f"<b>{html.escape(title)}</b>\n"]
    for i, s in enumerate(summaries, 1):
        headline = html.escape(s.headline)
        body = html.escape(s.body)
        url = html.escape(s.url, quote=True)
        source = html.escape(s.source)
        category = html.escape(s.category)
        parts.append(
            f"{i}. <b>{headline}</b>\n"
            f"{body}\n"
            f"<i>{source}</i> · <code>{category}</code> · <a href=\"{url}\">Read more</a>\n"
        )
    return "\n".join(parts)


def _chunk(text: str, size: int) -> list[str]:
    if len(text) <= size:
        return [text]
    chunks, current = [], ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > size:
            chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)
    return chunks


def send_message(text: str, chat_id: str | None = None) -> None:
    target = chat_id or secrets.telegram_chat_id
    api = API.format(token=secrets.telegram_bot_token)
    for chunk in _chunk(text, MAX_LEN):
        resp = httpx.post(
            api,
            json={
                "chat_id": target,
                "text": chunk,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        resp.raise_for_status()


def send_digest(summaries: list[Summary], title: str, chat_id: str | None = None) -> None:
    if not summaries:
        send_message("No new stories to send.", chat_id)
        return
    send_message(format_digest(summaries, title), chat_id)
