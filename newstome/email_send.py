import smtplib
import json
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .config import secrets
from .summarize import Summary
from .auth import unsubscribe_token

SUBSCRIBERS_PATH = Path("data/subscribers.json")

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

CATEGORY_LABELS = {
    "india_politics": "🏛 Politics",
    "india_markets": "📈 Markets",
    "india_business": "💼 Business",
    "india_policy": "📋 Policy",
    "india_sports": "🏏 Sports",
    "india_science": "🔬 Science",
    "india_entertainment": "🎬 Entertainment",
    "india_geopolitics": "🌏 Geopolitics",
    "india_other": "🇮🇳 India",
    "global_ai": "🤖 AI",
    "global_bigtech": "💻 Big Tech",
    "global_startups": "🚀 Startups",
    "global_security": "🔐 Security",
    "global_oss": "⚙️ Open Source",
    "global_hardware": "🖥 Hardware",
    "global_policy": "🌐 Global Policy",
    "global_space": "🌌 Space",
    "global_other": "🌍 Global",
    "other": "📰 News",
}


def _fmt_date(date_str: str) -> str:
    """Minimal DD MMM formatter for RSS dates."""
    if not date_str: return ""
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(date_str)
        return dt.strftime("%d %b")
    except:
        return date_str.split()[0:4][-1] if date_str else ""


def _unsubscribe_url(base_url: str, email: str | None) -> str | None:
    if not email:
        return None
    import urllib.parse
    q = urllib.parse.urlencode({"u": email, "t": unsubscribe_token(email)})
    return f"{base_url}/unsubscribe?{q}"


def _html_body(summaries: list[Summary], title: str, email: str | None = None) -> str:
    items = ""
    base_url = secrets.app_url.rstrip("/")
    unsub_html = ""
    if email:
        unsub_link = _unsubscribe_url(base_url, email)
        unsub_html = (
            '<div style="font-size:11px;color:#aaa;margin-top:4px;">'
            "Don&#39;t want these? "
            f'<a href="{unsub_link}" style="color:#888;text-decoration:underline;">Unsubscribe</a>.'
            "</div>"
        )
    for s in summaries:
        label = CATEGORY_LABELS.get(s.category, s.category)
        date_chip = _fmt_date(s.date)
        
        # Tracking link
        link = s.url
        if email:
            import urllib.parse
            q = urllib.parse.urlencode({"url": s.url, "cat": s.category, "u": email})
            link = f"{base_url}/r?{q}"

        items += f"""
        <tr>
          <td style="padding:16px 0;border-bottom:1px solid #eee;">
            <div style="font-size:11px;color:#888;margin-bottom:4px;">{label} &nbsp;·&nbsp; {s.source} &nbsp;·&nbsp; {date_chip}</div>
            <div style="font-size:16px;font-weight:700;color:#111;margin-bottom:6px;line-height:1.3">{s.headline}</div>
            <div style="font-size:14px;color:#444;line-height:1.6;margin-bottom:8px">{s.body}</div>
            <a href="{link}" style="font-size:12px;color:#1b4aef;text-decoration:none;">Read more →</a>
          </td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;padding:24px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:8px;overflow:hidden;">
        <tr>
          <td style="background:#111;padding:20px 24px;">
            <div style="color:#fff;font-size:22px;font-weight:700;">{title}</div>
            <div style="color:#aaa;font-size:12px;margin-top:4px;">Your personalised morning brief</div>
          </td>
        </tr>
        <tr>
          <td style="padding:0 24px;">
            <table width="100%" cellpadding="0" cellspacing="0">{items}</table>
          </td>
        </tr>
        <tr>
          <td style="padding:16px 24px;background:#f9f9f9;border-top:1px solid #eee;">
            <div style="font-size:11px;color:#aaa;">Delivered by NewsToMe · Powered by Shelby Co.</div>
            {unsub_html}
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _text_body(summaries: list[Summary], title: str, email: str | None = None) -> str:
    lines = [title, "=" * len(title), ""]
    for i, s in enumerate(summaries, 1):
        lines += [f"{i}. {s.headline}", s.body, f"Source: {s.source}", f"Link: {s.url}", ""]
    unsub = _unsubscribe_url(secrets.app_url.rstrip("/"), email)
    if unsub:
        lines += ["--", f"Unsubscribe: {unsub}"]
    return "\n".join(lines)


def send_email(summaries: list[Summary], title: str, to: str | list[str] | None = None) -> tuple[bool, str | None]:
    if not summaries:
        return False, "No summaries to send"

    recipients = []
    if to:
        recipients = [to] if isinstance(to, str) else to
    else:
        if SUBSCRIBERS_PATH.exists():
            try:
                subs = json.loads(SUBSCRIBERS_PATH.read_text())
                recipients = [s["email"] for s in subs if "email" in s]
            except Exception:
                pass
        
        if not recipients:
            recipients = [secrets.gmail_address]

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = title
        msg["From"] = secrets.gmail_address
        msg["To"] = "undisclosed-recipients:;"

        # Use the first recipient's email for tracking if it's a single-user send
        tracking_email = recipients[0] if len(recipients) == 1 else None
        msg.attach(MIMEText(_text_body(summaries, title, email=tracking_email), "plain"))
        msg.attach(MIMEText(_html_body(summaries, title, email=tracking_email), "html"))

        # RFC 8058 one-click unsubscribe header (Gmail/Outlook compliance)
        if tracking_email:
            unsub_url = _unsubscribe_url(secrets.app_url.rstrip("/"), tracking_email)
            msg["List-Unsubscribe"] = f"<{unsub_url}>"
            msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(secrets.gmail_address, secrets.gmail_app_password)
            smtp.sendmail(secrets.gmail_address, recipients, msg.as_string())
        return True, None
    except Exception as e:
        return False, str(e)
