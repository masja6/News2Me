import json
import re

import anthropic

from .config import secrets
from .fetch import Article
from .summarize import _client

CLASSIFY_SYSTEM = """You are a news classifier. For each article, assign exactly one category from the provided taxonomy.

Rules:
- Match on the MAIN topic of the headline, not a side detail.
- Prefer the more specific category when unsure (e.g. "india_markets" over "india_business" for stock moves).
- Use "other" only if nothing fits.
- Return a JSON array with one object per article: {"id": int, "category": string}.
- Return EXACTLY as many items as you received, in the same order.
- Output ONLY the JSON array. No preamble, no markdown fences."""


def _extract_json_array(text: str) -> list:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return json.loads(t)


def classify_articles(articles: list[Article], categories: list[str]) -> list[Article]:
    if not articles:
        return articles

    lines = [f"{i}. {a.title}" for i, a in enumerate(articles)]
    user = f"Taxonomy: {', '.join(categories)}\n\nArticles:\n" + "\n".join(lines)

    try:
        response = _client.messages.create(
            model=secrets.classify_model,
            max_tokens=2000,
            system=CLASSIFY_SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
    except (anthropic.RateLimitError, anthropic.APIStatusError, Exception) as e:
        print(f"  classify failed ({e}); falling back to feed category")
        return articles

    text = "".join(block.text for block in response.content if block.type == "text").strip()
    try:
        items = _extract_json_array(text)
        mapping = {int(it["id"]): it["category"] for it in items}
    except Exception as e:
        print(f"  classify parse failed ({e}); falling back")
        return articles

    for i, a in enumerate(articles):
        cat = mapping.get(i)
        if cat and cat in categories:
            a.category = cat
    return articles
