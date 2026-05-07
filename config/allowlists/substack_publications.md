# Curated Long-form Publications

Drives the `ai_essays` section and the `trackers.authors` onboarding picker.

Format: `- slug | feed_url — note`

`slug` is the canonical id we store in `trackers.authors`. Keep it short,
lowercase, no spaces. The feed URL is the RSS/Atom endpoint.

> Verify URLs before deploy. Substack patterns are stable; some independent
> blog feeds may have moved.

## Practitioner blogs

- simonwillison | https://simonwillison.net/atom/everything/ — Builds with LLMs daily; sharp short notes
- latent-space | https://www.latent.space/feed — Latent Space (swyx); essays + podcast notes
- eugeneyan | https://eugeneyan.com/rss/ — Applied ML, recsys, evals
- raschka | https://magazine.sebastianraschka.com/feed — Ahead of AI; tutorial-grade depth
- huyenchip | https://huyenchip.com/feed.xml — ML systems design
- hamel | https://hamel.dev/index.xml — Evals, prompting, fine-tuning
- jxnl | https://jxnl.co/index.xml — Structured outputs, agent eng

## Research analysis

- import-ai | https://jack-clark.net/feed/ — Jack Clark's weekly research roundup
- interconnects | https://www.interconnects.ai/feed — Nathan Lambert on RLHF / open models / policy
- lilianweng | https://lilianweng.github.io/index.xml — Deep technical writeups
- the-gradient | https://thegradient.pub/rss/ — Long-form research essays
- ai-snake-oil | https://www.aisnakeoil.com/feed — Critical lens on AI claims

## Strategy / industry

- stratechery | https://stratechery.com/feed/ — Ben Thompson on AI strategy
- one-useful-thing | https://www.oneusefulthing.org/feed — Ethan Mollick on AI in practice
- platformer | https://www.platformer.news/feed — Casey Newton; AI policy and culture
- the-batch | https://www.deeplearning.ai/the-batch/feed/ — Andrew Ng's weekly
- pragmatic-engineer | https://newsletter.pragmaticengineer.com/feed — Gergely Orosz; eng perspective on AI
- every | https://every.to/feed.xml — Dan Shipper; AI in product
- ai-news | https://buttondown.email/ainews/rss — Smol AI daily roundup

## Frontier lab official blogs

- anthropic | https://www.anthropic.com/news/rss.xml — Anthropic research and product
- openai | https://openai.com/blog/rss.xml — OpenAI announcements
- deepmind | https://deepmind.google/blog/rss.xml — Google DeepMind
- meta-ai | https://ai.meta.com/blog/rss/ — Meta AI / FAIR
- mistral | https://mistral.ai/news/feed.xml — Mistral
- cohere | https://cohere.com/blog/rss.xml — Cohere

## Notes

- Trust score is computed at runtime: 0.95 for lab blogs, 0.85 for established
  practitioner / analysis publications. Override per-source if needed.
- Per-publication rate cap: max 2 essays/week into ranking, regardless of how
  much they post.
