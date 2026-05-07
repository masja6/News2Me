import json
import re
import time
from dataclasses import dataclass

import anthropic
from anthropic import Anthropic

from .config import Summarizer, secrets
from .fetch import Article
from .db import get_cached_summary, set_cached_summary
from . import observe
import dataclasses

_client = Anthropic(api_key=secrets.anthropic_api_key)

# Rough Haiku 4.5 pricing (USD / 1M tokens). Used only for operator estimates.
_PRICE_IN = 1.00 / 1_000_000
_PRICE_OUT = 5.00 / 1_000_000

# Per-run counters. Reset with reset_metrics() at the start of each pipeline run.
_metrics = {
    "cache_hits": 0,
    "cache_misses": 0,
    "input_tokens": 0,
    "output_tokens": 0,
}


def reset_metrics() -> None:
    for k in _metrics:
        _metrics[k] = 0


def get_metrics() -> dict:
    est_cost = _metrics["input_tokens"] * _PRICE_IN + _metrics["output_tokens"] * _PRICE_OUT
    total = _metrics["cache_hits"] + _metrics["cache_misses"]
    hit_rate = (_metrics["cache_hits"] / total) if total else 0.0
    return {**_metrics, "est_cost_usd": round(est_cost, 4), "hit_rate": round(hit_rate, 3)}

SYSTEM_NEWS = """You write Inshorts-style news summaries.

Return JSON with exactly two fields:
- "headline": a COMPLETE 6-10 word headline. It must read as a finished phrase. No trailing punctuation. Never cut mid-word or mid-number.
- "body": EXACTLY 30-40 words. A factual summary. Count the words before responding.

Rules:
- No emojis, exclamation marks, or clickbait wording.
- Preserve names, numbers, dates from the source.
- Lead with the fact. Skip filler like "In a recent development".
- Output ONLY the JSON object. No preamble, no markdown fences."""

SYSTEM_PAPER = """You summarize academic papers for ML practitioners.

Return JSON with exactly two fields:
- "headline": 8-12 words capturing the key contribution. No clickbait.
- "body": 50-70 words structured as: Problem → Method → Result. Preserve model names, benchmark numbers, and percentage improvements exactly. If the paper introduces a named method or model, lead with it.

Rules:
- No emojis, no filler.
- Preserve all numbers, metric names, and comparisons.
- Output ONLY the JSON object. No preamble, no markdown fences."""

SYSTEM_MODEL = """You summarize AI model releases for practitioners.

Return JSON with exactly two fields:
- "headline": The model name plus a one-line capability (8-12 words).
- "body": 30-50 words. Always state: releasing org, parameter count if known, license, primary task, and what it outperforms (if any).

Rules:
- Preserve exact benchmark numbers and comparisons.
- Output ONLY the JSON object. No preamble, no markdown fences."""

SYSTEM_RELEASE = """You summarize software library release notes for developers.

Return JSON with exactly four fields:
- "headline": "<library> v<version>: <one-line theme>" (under 12 words).
- "body": 40-80 words. Lead with breaking changes if any. Then list up to 3 notable new features. Mention deprecations.
- "breaking_changes": a JSON array of strings (empty array if none).
- "migration_required": boolean — true if any breaking changes need code updates.

Rules:
- Be specific about what changed, not vague ("improved performance").
- Output ONLY the JSON object. No preamble, no markdown fences."""

SYSTEM_ESSAY = """You summarize long-form analysis for busy readers.

Return JSON with exactly two fields:
- "headline": The author's core thesis in one line (8-14 words).
- "body": 100-180 words. Capture the argument arc: what claim is made, what evidence supports it, what conclusion is drawn. Preserve the author's key insight — don't flatten to a topic label.

Rules:
- First sentence should state the thesis, not describe the article.
- No emojis, no filler.
- Output ONLY the JSON object. No preamble, no markdown fences."""

_SYSTEM_PROMPTS = {
    "news": SYSTEM_NEWS,
    "paper": SYSTEM_PAPER,
    "model": SYSTEM_MODEL,
    "release": SYSTEM_RELEASE,
    "essay": SYSTEM_ESSAY,
}

_MAX_BODY_WORDS = {
    "news": 40,
    "paper": 70,
    "model": 50,
    "release": 80,
    "essay": 180,
}


@dataclass
class Summary:
    headline: str
    body: str
    url: str
    source: str
    category: str
    date: str
    content_type: str = "news"
    authors: list[str] | None = None
    extra: dict | None = None


def _extract_json(text: str) -> dict:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return json.loads(t)


def summarize(article: Article, cfg: Summarizer, tone: str = "Standard", jargon_busting: bool = False) -> Summary:
    tone_str = str(tone) if tone else "Standard"
    cached_data = get_cached_summary(article.url, tone_str, jargon_busting)

    if cached_data:
        _metrics["cache_hits"] += 1
        return Summary(**cached_data)
    _metrics["cache_misses"] += 1

    ct = article.content_type or "news"
    max_chars = cfg.max_article_chars
    if ct == "essay":
        max_chars = min(max_chars * 2, 12000)

    content = (article.content or "")[:max_chars]

    if ct == "paper" and article.authors:
        prompt = f"Title: {article.title}\nAuthors: {', '.join(article.authors)}\n\nAbstract:\n{content}"
    elif ct == "release" and article.extra:
        lib_name = article.extra.get("library", article.title)
        prompt = f"Library: {lib_name}\n\nRelease Notes:\n{content}"
    else:
        prompt = f"Title: {article.title}\n\nArticle:\n{content}"

    system_prompt = _SYSTEM_PROMPTS.get(ct, SYSTEM_NEWS)
    if tone and tone.lower() != "standard":
        system_prompt += f"\n- Tone adjustment: Adopt the following tone in your body perfectly: {tone}."
    if jargon_busting:
        system_prompt += "\n- Jargon busting: Identify any complex finance, technical, or policy jargon and wrap them cleanly in HTML <abbr title='simple definition'>term</abbr> tags."

    max_tokens = 400 if ct != "essay" else 800

    response = None
    for attempt in range(4):
        try:
            response = _client.messages.create(
                model=secrets.summary_model,
                max_tokens=max_tokens,
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

    usage = getattr(response, "usage", None)
    in_tok = getattr(usage, "input_tokens", 0) or 0 if usage else 0
    out_tok = getattr(usage, "output_tokens", 0) or 0 if usage else 0
    _metrics["input_tokens"] += in_tok
    _metrics["output_tokens"] += out_tok

    text = "".join(block.text for block in response.content if block.type == "text").strip()

    observe.log_generation(
        name="summarize",
        model=secrets.summary_model,
        prompt=prompt,
        completion=text,
        input_tokens=in_tok,
        output_tokens=out_tok,
        metadata={"tone": tone_str, "jargon_busting": jargon_busting, "url": article.url, "content_type": ct},
    )

    data = _extract_json(text)

    summary_extra = {}
    if ct == "release":
        bc = data.get("breaking_changes", [])
        summary_extra["breaking_changes"] = bc if isinstance(bc, list) else []
        summary_extra["migration_required"] = bool(data.get("migration_required", False))

    max_words = _MAX_BODY_WORDS.get(ct, 40)

    summary = Summary(
        headline=str(data.get("headline", "")).strip().rstrip(".,;:"),
        body=_trim_body(str(data.get("body", "")).strip(), max_words=max_words),
        url=article.url,
        source=article.source,
        category=article.category,
        date=article.published or "",
        content_type=ct,
        authors=article.authors,
        extra=summary_extra or None,
    )

    set_cached_summary(article.url, tone_str, jargon_busting, dataclasses.asdict(summary))
    return summary


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
