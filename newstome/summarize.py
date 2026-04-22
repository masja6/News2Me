import json
import re
import time
from dataclasses import dataclass

import anthropic
from anthropic import Anthropic

from .config import Summarizer, secrets
from .fetch import Article

_client = Anthropic(api_key=secrets.anthropic_api_key)

SYSTEM = """You write Inshorts-style news summaries.

Return JSON with exactly two fields:
- "headline": a COMPLETE 6-10 word headline. It must read as a finished phrase. No trailing punctuation. Never cut mid-word or mid-number.
- "body": EXACTLY 30-40 words. A factual summary. Count the words before responding.

Rules:
- No emojis, exclamation marks, or clickbait wording.
- Preserve names, numbers, dates from the source.
- Lead with the fact. Skip filler like "In a recent development".
- Output ONLY the JSON object. No preamble, no markdown fences."""


@dataclass
class Summary:
    headline: str
    body: str
    url: str
    source: str
    category: str


def _extract_json(text: str) -> dict:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return json.loads(t)


def summarize(article: Article, cfg: Summarizer, tone: str = "Standard", jargon_busting: bool = False) -> Summary:
    content = (article.content or "")[: cfg.max_article_chars]
    prompt = f"Title: {article.title}\n\nArticle:\n{content}"

    system_prompt = SYSTEM
    if tone and tone.lower() != "standard":
        system_prompt += f"\n- Tone adjustment: Adopt the following tone in your body perfectly: {tone}."
    if jargon_busting:
        system_prompt += "\n- Jargon busting: Identify any complex finance, technical, or policy jargon and wrap them cleanly in HTML <abbr title='simple definition'>term</abbr> tags."

    response = None
    for attempt in range(4):
        try:
            response = _client.messages.create(
                model=secrets.summary_model,
                max_tokens=400,
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )
            break
        except (anthropic.RateLimitError, anthropic.APIStatusError) as e:
            code = getattr(e, "status_code", None)
            if code in (429, 500, 502, 503, 529) and attempt < 3:
                delay = 5 * (attempt + 1)
                print(f"    {code}, waiting {delay}s (attempt {attempt + 1}/4)...")
                time.sleep(delay)
                continue
            raise

    text = "".join(block.text for block in response.content if block.type == "text").strip()
    data = _extract_json(text)

    return Summary(
        headline=str(data.get("headline", "")).strip().rstrip(".,;:"),
        body=_trim_body(str(data.get("body", "")).strip()),
        url=article.url,
        source=article.source,
        category=article.category,
    )


def _trim_body(text: str, max_words: int = 40) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    # Cut at last sentence boundary within max_words
    truncated = " ".join(words[:max_words])
    last_stop = max(truncated.rfind("."), truncated.rfind("!"), truncated.rfind("?"))
    if last_stop > len(truncated) // 2:
        return truncated[: last_stop + 1]
    return truncated + "."
