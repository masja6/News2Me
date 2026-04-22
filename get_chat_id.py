"""
Print the Telegram chat IDs that have messaged your bot.

Usage:
  1. Put TELEGRAM_BOT_TOKEN in .env
  2. On Telegram, open your bot and send it any message (e.g. "hi")
  3. python get_chat_id.py
  4. Copy the chat_id into .env as TELEGRAM_CHAT_ID
"""
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

token = os.environ.get("TELEGRAM_BOT_TOKEN")
if not token:
    raise SystemExit("Set TELEGRAM_BOT_TOKEN in .env first.")

resp = httpx.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=10)
resp.raise_for_status()
data = resp.json()

if not data.get("ok"):
    raise SystemExit(f"Telegram error: {data}")

updates = data.get("result", [])
if not updates:
    raise SystemExit(
        "No messages yet. Send your bot a message on Telegram first, then re-run."
    )

seen: set[tuple[int, str, str]] = set()
for upd in updates:
    msg = upd.get("message") or upd.get("edited_message")
    if msg and "chat" in msg:
        chat = msg["chat"]
        seen.add((chat["id"], chat.get("first_name", ""), chat.get("type", "")))

print("Chats that have messaged your bot:")
for cid, name, ctype in seen:
    print(f"  chat_id={cid}  ({ctype}, {name})")
print("\nCopy the chat_id into .env as TELEGRAM_CHAT_ID")
