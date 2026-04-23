# NewsToMe

A self-hosted, multi-agent morning news digest system. Every morning it fetches articles from RSS feeds across Indian and global tech sources, classifies and clusters them with an LLM, ranks them for diversity, summarises each one in the Inshorts style (≤10-word headline + ≤40-word body), runs a quality check, and delivers via Telegram and Gmail.

---

## Table of Contents

- [Why we built this](#why-we-built-this)
- [Architecture overview](#architecture-overview)
- [Pipeline — step by step](#pipeline--step-by-step)
- [Project structure](#project-structure)
- [Configuration](#configuration)
- [Delivery channels](#delivery-channels)
- [Admin UI](#admin-ui)
- [Development history & version progression](#development-history--version-progression)
- [Setup guide](#setup-guide)
- [Running locally](#running-locally)
- [Roadmap](#roadmap)

---

## Why we built this

Most news aggregators either flood you with low-quality content or lock useful curation behind a paywall. The goal here was a **personal digest** — opinionated about sources, concise in format, and delivered to wherever you already are (Telegram or email) without any app to open.

The secondary goal was to make the entire pipeline inspectable and tweakable through a web admin panel rather than editing code or config files by hand.

---

## Architecture overview

```
RSS Feeds
    │
    ▼
┌─────────────┐    httpx + feedparser    ┌──────────────────┐
│  fetch.py   │──────────────────────────▶  Article objects  │
└─────────────┘    trafilatura extract   └────────┬─────────┘
                                                  │
                                         URL dedupe (SHA-256,
                                         7-day TTL seen.json)
                                                  │
                                                  ▼
                                        ┌──────────────────┐
                                        │  classify.py     │  Claude Haiku 4.5
                                        │  (LLM batch)     │  18-category taxonomy
                                        └────────┬─────────┘
                                                  │
                                                  ▼
                                        ┌──────────────────┐
                                        │  cluster.py      │  RapidFuzz
                                        │  (title fuzzy)   │  token_set_ratio ≥ 82
                                        └────────┬─────────┘
                                                  │
                                                  ▼
                                        ┌──────────────────┐
                                        │  rank.py         │  recency × trust ×
                                        │  + diversity     │  cluster-boost scoring
                                        └────────┬─────────┘
                                                  │
                                                  ▼
                                        ┌──────────────────┐
                                        │  summarize.py    │  Claude Haiku 4.5
                                        │  (per article)   │  JSON structured output
                                        └────────┬─────────┘
                                                  │
                                                  ▼
                                        ┌──────────────────┐
                                        │  qc.py           │  word counts, duplicates,
                                        │  (quality check) │  category balance
                                        └────────┬─────────┘
                                                  │
                              ┌───────────────────┴───────────────────┐
                              ▼                                         ▼
                    ┌──────────────────┐                    ┌──────────────────┐
                    │  telegram.py     │                    │  email_send.py   │
                    │  HTML message    │                    │  HTML newsletter │
                    └──────────────────┘                    └──────────────────┘
```

All pipeline logic lives in `newstome/pipeline.py`, which orchestrates the agents above in sequence and saves results to `data/last_digest.json` for the admin UI.

---

## Pipeline — step by step

### 1. Fetch (`fetch.py`)

- Iterates over every feed in `config.yaml`
- Fetches the RSS XML via **httpx** (bundled `certifi` certs, avoids macOS SSL issues)
- Parses with **feedparser**, takes up to 12 entries per feed
- For each entry, visits the article URL and extracts clean text with **trafilatura** (`favor_precision=True`, no comments/tables)
- Falls back to RSS `<summary>` if extraction fails
- Produces a list of `Article` dataclass objects with: `title`, `url`, `published`, `content`, `source`, `category`, `trust`

### 2. URL deduplication (`dedupe.py`)

- Hashes each URL with SHA-256 (first 16 hex chars) and checks against `data/seen.json`
- Entries older than **7 days** are pruned on every run
- `filter_unseen()` returns only articles not seen before
- `mark_seen()` is called only after successful delivery — if a run fails mid-way, the articles stay eligible for the next run

### 3. LLM classification (`classify.py`)

All articles are classified in a **single batched API call** to Claude Haiku 4.5. The prompt lists all 18 categories and asks for the best fit per article, returning a JSON array. Falls back to the feed's default category if the API call fails.

**18-category taxonomy:**

| India | Global |
|---|---|
| `india_politics` | `global_ai` |
| `india_markets` | `global_bigtech` |
| `india_business` | `global_startups` |
| `india_policy` | `global_security` |
| `india_geopolitics` | `global_oss` |
| `india_sports` | `global_hardware` |
| `india_science` | `global_policy` |
| `india_entertainment` | `global_other` |
| `india_other` | `other` |

Why per-article classification? The feed's declared category (e.g. `india_other`) is too coarse — the same feed covers politics, sports, and business. Without per-article classification the digest was dominated by a single category.

### 4. Fuzzy clustering (`cluster.py`)

Articles covering the same event from different sources are grouped into clusters using **RapidFuzz**:

- `token_set_ratio ≥ 82` (configurable as `dedupe_similarity`) between titles in the same category
- `partial_ratio ≥ 70` as a secondary check for partial title overlap

One cluster = one story. The representative article (highest trust score) is chosen for summarisation. Cluster size is a signal in ranking — bigger clusters mean more sources reported the event.

### 5. Ranking + diversity enforcement (`rank.py`)

Each cluster gets a composite score:

```
score = recency_weight  × exp(−age_hours / 12)
      + trust_weight    × max_trust_in_cluster
      + cluster_size_weight × log1p(n) / log(4)
```

Default weights: `0.5 / 0.3 / 0.2`. Recency uses a **12-hour half-life** exponential decay.

**Diversity enforcement** runs after sorting:

- `per_category_max = 2` — no category may contribute more than 2 stories
- `per_region_max = 6` — at most 6 India stories and 6 global stories (region inferred from `india_*` prefix)
- `max_items = 10` — digest cap

Without `per_region_max`, India sources (higher trust 0.85–0.9) consistently outscored global tech sources (0.82–0.88) and the digest had zero global stories.

### 6. Summarisation (`summarize.py`)

Each representative article is summarised by **Claude Haiku 4.5** with a strict JSON output prompt:

```json
{"headline": "6–10 word present-tense headline", "body": "30–40 word plain-English summary"}
```

- Retries on HTTP 429 / 500 / 502 / 503 / 529 with exponential backoff
- `_trim_body()` truncates at the last sentence boundary ≤ 40 words if the model overshoots
- Article content is capped at `max_article_chars = 6000` before sending to save tokens

Why Haiku 4.5? It's the cheapest Claude model, fast, and the summarisation task is well-defined enough that it doesn't need a larger model. A full 10-story digest costs roughly $0.001–0.003.

### 7. Quality check (`qc.py`)

After all summaries are produced, a QC report is generated:

| Check | Severity | Threshold |
|---|---|---|
| Headline word count | warn | 5–12 words |
| Body word count | warn | 28–45 words |
| Empty body | error | any |
| Near-duplicate headlines | warn | fuzz ratio > 75 |
| Minimum distinct categories | warn | ≥ 4 |
| Max share per category | warn | ≤ 50% |

Results are stored in `data/last_digest.json` and surfaced in the admin UI.

### 8. Delivery

**Telegram (`telegram.py`)** — uses `python-telegram-bot` v21 async API. Each story is formatted as HTML with a category label, bold headline, body text, and a "Read more" link. Sent as a single message per digest.

**Email (`email_send.py`)** — SMTP via Gmail (port 587, STARTTLS). Renders a full HTML newsletter with a dark header, per-story cards, and category emoji labels. Uses `smtplib` directly (no third-party email library needed).

---

## Project structure

```
NewsToMe/
├── newstome/
│   ├── config.py        # Pydantic models, secrets loading, load/save config
│   ├── fetch.py         # RSS fetch + full-text extraction
│   ├── classify.py      # LLM batch classification
│   ├── cluster.py       # Fuzzy title deduplication / clustering
│   ├── rank.py          # Scoring + diversity enforcement
│   ├── summarize.py     # LLM summarisation (Haiku 4.5, JSON output)
│   ├── qc.py            # Quality checks on digest
│   ├── dedupe.py        # URL seen-set with 7-day TTL
│   ├── pipeline.py      # Orchestrates all agents in sequence
│   ├── telegram.py      # Telegram delivery
│   ├── email_send.py    # Gmail HTML email delivery
│   ├── bot.py           # Telegram bot (/start /status /digest commands)
│   └── ui.py            # FastAPI admin UI routes
├── templates/
│   ├── onboard.html     # Typeform-style 7-step onboarding
│   └── admin.html       # Admin dashboard
├── config.yaml          # Runtime config (feeds, ranking weights, QC thresholds)
├── run_digest.py        # One-shot CLI: build + deliver
├── run_bot.py           # Run the Telegram bot process
├── run_ui.py            # Run the FastAPI admin server
├── get_chat_id.py       # Helper: print your Telegram chat ID
├── pyproject.toml
└── .env.example
```

---

## Configuration

All runtime behaviour is controlled by `config.yaml` — no code changes needed for day-to-day tuning. The admin UI has a live YAML editor that validates and saves changes.

```yaml
feeds:
  - name: The Hindu - National
    url: https://www.thehindu.com/news/national/feeder/default.rss
    category: india_other   # default, overridden by classifier
    trust: 0.9              # 0.0–1.0, affects ranking score

categories:
  - india_politics
  - india_markets
  # ... 18 total

ranking:
  max_items: 10
  per_category_max: 2       # max stories per category
  per_region_max: 6         # max india or global stories
  dedupe_similarity: 82     # RapidFuzz threshold
  recency_weight: 0.5
  trust_weight: 0.3
  cluster_size_weight: 0.2

summarizer:
  request_delay_sec: 0      # inter-request delay (increase to throttle)
  max_article_chars: 6000   # chars sent to LLM per article

qc:
  min_categories: 4
  max_share_per_category: 0.5

delivery:
  channels: [telegram, email]
  email_to: ""              # override recipient; defaults to GMAIL_ADDRESS

telegram:
  digest_title: "Morning Digest"
```

Secrets are stored in `.env` (never committed):

```
ANTHROPIC_API_KEY=sk-ant-...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
GMAIL_ADDRESS=you@gmail.com
GMAIL_APP_PASSWORD=...
GEMINI_API_KEY=...          # kept as fallback, not active
```

---

## Delivery channels

### Telegram
The bot supports interactive commands:
- `/start` — welcome message
- `/status` — when was the last digest sent
- `/digest` — trigger an on-demand digest (runs the full pipeline, sends result to requester)

### Gmail
Sends an HTML newsletter. Requires a Gmail App Password (not your account password) — enable 2FA, then create an App Password at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).

---

## Admin UI

Start with:
```bash
source .venv/bin/activate
uvicorn newstome.ui:app --reload
```

Then open `http://localhost:8000`.

**Onboarding flow** (`/`) — Typeform-style, one question at a time with CSS slide animations:
1. Welcome
2. Your name
3. Email address
4. India topic preferences (chip selector, pre-selected: politics, markets, policy, geopolitics)
5. Global topic preferences (chip selector, pre-selected: AI, BigTech, Startups, Security)
6. Stories per digest (slider, 5–20)
7. Done — animated checkmark + summary of selections

**Admin dashboard** (`/admin`):
- Run digest on demand (▶ Run digest now)
- Live status bar (idle / running / QC warning)
- Active feeds list with category and trust score
- Ranking parameters display
- QC report with category bar chart and per-issue log
- Delivery channel status
- Last digest — full story cards with category, headline, body, link
- Live YAML config editor — edit and save without restarting

---

## Development history & version progression

### v0.1 — Single-agent proof of concept
The first version had a single Python script that fetched from 3 RSS feeds, called the Gemini API for a summary, and sent a plain-text Telegram message. No classification, no deduplication, no ranking. The problem: Gemini's free tier had a 20-request/day cap per project and strict rate limits (5/min), making a 10-story digest unreliable.

**Key lesson:** Free tier LLM quotas are incompatible with per-article summarisation at volume. Need either batching or a paid tier.

### v0.2 — Switched to Claude Haiku 4.5
Replaced Gemini with Anthropic Claude Haiku 4.5 after loading $5 in API credits. This eliminated quota issues entirely. The summarisation quality also improved because Haiku follows strict JSON output instructions more reliably than Gemini 2.5 Flash in JSON mode (Gemini was leaking `<thinking>` tags into output with the Flash model).

Also fixed a critical env issue: Claude Code's shell exported `ANTHROPIC_API_KEY=` (empty string) which shadowed the `.env` file. Fixed with `load_dotenv(override=True)` in `config.py`.

**Key lesson:** Always use `override=True` with dotenv when running inside environments that pre-set variables.

### v0.3 — Per-article LLM classification + 18-category taxonomy
The original approach used the feed's declared category for all articles in that feed (e.g. everything from The Hindu was `india_other`). This made the digest heavily skewed — 8 of 10 stories in the same category.

Introduced a batched classification step: a single Claude API call classifies all articles in one request, returning a JSON array of category assignments. Expanded the taxonomy from 5 to 18 categories with `india_*` / `global_*` prefixes to enable region-aware diversity enforcement.

**Key lesson:** Feed-level categories are too coarse. LLM classification at article level is worth the extra API call because it unlocks meaningful diversity enforcement downstream.

### v0.4 — Fuzzy clustering + ranking overhaul
Without clustering, the same event (e.g. "RBI rate cut") would appear 3 times — once from each Indian news source. Added RapidFuzz title clustering (`token_set_ratio ≥ 82`) to group near-duplicate stories into a single cluster and pick the best representative.

Also reworked the ranking formula to a weighted composite score (recency × trust × cluster boost) and added `per_region_max` after noticing that India sources (trust 0.85–0.9) consistently beat global tech sources (0.82) — the digest had zero global tech stories despite TechCrunch and Hacker News being in the feed list.

**Key lesson:** Numeric ranking without diversity caps always degrades to the highest-trust region/source dominating. Caps are not optional.

### v0.5 — Email delivery + QC
Added Gmail SMTP delivery (HTML newsletter format) as a second channel. Added the QC module to validate every digest: word counts, near-duplicate headline detection, category balance. QC results are persisted in `data/last_digest.json` so they can be surfaced in the UI without re-running the pipeline.

Also added `_trim_body()` after noticing LLM body summaries were regularly 46–58 words despite the prompt saying 30–40 — truncates at the last sentence boundary ≤ 40 words.

**Key lesson:** LLMs don't reliably respect word count constraints in prompts. Post-processing trim is required.

### v0.6 — Admin UI + Onboarding (current)
Built a full web UI with FastAPI + Jinja2:
- Typeform-style onboarding with CSS slide animations
- Admin dashboard with live digest preview, QC report, and YAML config editor

Hit a breaking change: **Starlette 1.0.0** changed the `TemplateResponse` API — `request` moved from a context dict key to the first positional argument. Fixed across all routes.

Also fixed a Jinja2 template syntax bug in the nested ternary expression used for the status dot class (`'a' if x else ('b' if y) else ''` is invalid — correct form is `'a' if x else ('b' if y else '')`).

### v0.7 — Scale, Personalization & Superpowers
Transformed the system from a static aggregator into a scalable, learning product:
- **Click Tracking & Personalization**: Added a `GET /r` tracking redirect route. The system now learns which categories a user clicks on and applies a "Personalization Boost" to their ranking score in future digests.
- **Summary Caching**: Intercepted the LLM summarisation step with a MongoDB-backed cache (7-day TTL). If 100 users get the same story, the LLM is only called once. This dropped operational costs by >90%.
- **Scheduled Delivery**: Integrated `apscheduler` to automatically trigger the delivery cycle every day at 7:00 AM IST.
- **Superpowers Refactor**: Decoupled the monolithic pipeline by extracting delivery logic into `delivery.py` and established a rock-solid `pytest` automated testing foundation.

---

## Setup guide

### Prerequisites
- Python 3.11+
- A Telegram bot token (create via [@BotFather](https://t.me/BotFather))
- Your Telegram chat ID (run `python get_chat_id.py` after setting the bot token)
- An Anthropic API key with credits ([console.anthropic.com](https://console.anthropic.com))
- A Gmail account with an App Password

### Install

```bash
git clone https://github.com/masja6/News2Me.git
cd News2Me
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -e .
```

### Configure secrets

```bash
cp .env.example .env
# Edit .env and fill in all values
```

```env
ANTHROPIC_API_KEY=sk-ant-...
TELEGRAM_BOT_TOKEN=7xxxxxxxxx:AAF...
TELEGRAM_CHAT_ID=5xxxxxxxxx
GMAIL_ADDRESS=you@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
```

### Get your Telegram chat ID

```bash
python get_chat_id.py
# Send any message to your bot, then run this — it prints the chat ID
```

---

## Running locally

**One-shot digest** (fetch → summarise → deliver):
```bash
source .venv/bin/activate
python run_digest.py
```

**Telegram bot** (interactive /digest command):
```bash
source .venv/bin/activate
python run_bot.py
```

**Admin UI** (http://localhost:8000):
```bash
source .venv/bin/activate
uvicorn newstome.ui:app --reload
```

---

## Roadmap

### ✅ Done (through v0.7)
- Core pipeline: fetch → classify → cluster → rank → summarise → QC → deliver
- Telegram delivery + interactive `/digest` bot
- Gmail HTML newsletter with per-user tone + jargon-busting
- Admin UI + Typeform-style onboarding
- QC report with category bar charts
- URL deduplication (7-day TTL)
- 7 AM IST scheduled delivery (APScheduler)
- Per-user preferences + MongoDB persistence
- Click tracking + personalization boost (`/r` redirect)
- Summary caching (7-day TTL, >90% cost reduction)
- Welcome digest on signup
- Docker + docker-compose deployment
- Pytest foundation (basic, cache, rank, delivery)

### 🚨 P0 — Production hardening (next up)
Before we can safely invite real users.

| # | Item | Why |
|---|---|---|
| 1 | **Admin auth** | `/admin` is wide open — anyone with the URL can edit config, trigger runs, read subscriber list |
| 2 | **Unsubscribe link in emails** | Legal requirement (CAN-SPAM / GDPR) before any outbound sends |
| 3 | **Error alerts** | Scheduler currently fails silently — a broken 7 AM run produces zero user signal |
| 4 | **MongoDB health check + fallback logging** | Cached client goes stale if Mongo drops mid-run |
| 5 | **Rate-limit `/subscribe` and `/r`** | Open endpoints — trivially DoS-able or click-spammable |

### 🔧 P1 — Feature gaps
| # | Item | Why |
|---|---|---|
| 6 | Per-user timezone + send time | Scheduler is hardcoded 7 AM IST for everyone |
| 7 | Bounce handling | Capture SMTP bounces, auto-disable dead addresses |
| 8 | Concurrent feed fetching | `fetch_all()` is serial — slowest pipeline step |
| 9 | Click-analytics dashboard | Click data is logged but not visualized |
| 10 | Digest archive (public `/d/<date>` links) | Shareable digest pages |
| 11 | Notion archive (MCP) | Searchable digest archive in Notion |

### 🧪 P2 — Testing + observability
| # | Item | Why |
|---|---|---|
| 12 | CI (GitHub Actions) | Run `pytest` on PR |
| 13 | Integration test for full pipeline | Current tests mock each layer individually |
| 14 | Metrics: tokens/cost per run | Track cache hit/miss + cumulative spend |
| 15 | Wire up `scripts/test_variants.py` | A/B summarization tone experiments |

### 🚀 P3 — Growth features
| # | Item | Why |
|---|---|---|
| 16 | WhatsApp delivery (Meta Cloud API) | Third channel |
| 17 | Topic following (keyword match) | Beyond category filters — follow "RBI", "OpenAI" etc. |
| 18 | Digest preview before subscribe | Show sample digest during onboarding |
| 19 | Multi-language summaries | Hindi/Tamil via tone field prompt injection |

### 🏗️ P4 — Infra / scale (>100 users)
| # | Item | Why |
|---|---|---|
| 20 | Oracle Cloud VPS + systemd | Move off localhost onto Always Free VM |
| 21 | Split services (web/scheduler/bot/fetch-worker) | Separate containers behind Caddy/Traefik |
| 22 | Centralized fetch cache | Run fetch+classify+cluster once/hour, not per delivery |
| 23 | Queue for email sends | Gmail SMTP has ~500/day cap — switch to Resend/Postmark |
