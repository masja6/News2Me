# AI Brief Categories

The taxonomy used for AI Brief delivery sections and onboarding chips.
The pipeline reads this file at startup. Edit, restart, done.

Format: `- slug — emoji Display Label · short description`

`##` headings are for human grouping only — the parser ignores them.
Anything not a `- ` bullet is treated as a comment.

## Sections shown in the daily AI digest

- ai_models — 🤖 Models · New foundation models, fine-tunes, multimodal releases
- ai_papers — 📄 Papers · arXiv and conference papers worth a TLDR
- ai_libraries — 📦 Library updates · PyPI / npm releases for tooling you use
- ai_tools — 🔥 Trending tools · GitHub repos gaining momentum
- ai_essays — 🧠 Long reads · Curated long-form analysis
- ai_products — 🚀 Products · Product launches and notable feature drops
- ai_safety — 🛡 Safety & policy · Alignment, interpretability, governance

## Notes

- Slug is the canonical key — used in the database and in URLs. Don't rename without a migration.
- Emoji + label is what the user sees in onboarding and digest section headers.
- Adding a new category here makes it pickable in onboarding automatically.
- Removing a category here hides it from new signups but does not delete from existing subscribers.
