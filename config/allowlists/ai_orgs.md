# Tracked Hugging Face Orgs

Filters the firehose of HF model uploads down to orgs we actually care about.
Also seeds the `trackers.orgs` onboarding picker.

A model upload is admitted to the pipeline if **any** is true:
1. The org is in this list, OR
2. The model gathered ≥ 50 likes within 7 days of publish, OR
3. ≥ 5,000 downloads in the last 24 hours, OR
4. The org or specific model is in some user's `trackers.orgs`.

Format: `- org_slug — note`

`org_slug` must match the Hugging Face URL slug exactly (case-sensitive).

## Foundation model labs

- meta-llama — Meta Llama family
- mistralai — Mistral
- google — Google (Gemma, T5, etc.)
- microsoft — Phi, Florence, etc.
- deepseek-ai — DeepSeek
- Qwen — Alibaba Qwen
- 01-ai — Yi
- THUDM — Tsinghua / GLM
- nvidia — Nemotron and friends
- ibm-granite — IBM Granite
- allenai — AI2 (OLMo, Tülu)
- stabilityai — Stable Diffusion / SD3
- xai-org — xAI / Grok weights
- CohereForAI — Aya, Command R
- HuggingFaceTB — SmolLM
- openai-community — Legacy OpenAI weights (GPT-2 etc.)

## Specialized

- bigcode — StarCoder family
- codellama — Code Llama
- WizardLMTeam — WizardCoder / WizardMath
- BAAI — BGE embeddings
- mixedbread-ai — Embeddings, rerankers
- jinaai — Embeddings, rerankers
- nomic-ai — Embeddings, Atlas
- llava-hf — LLaVA multimodal
- black-forest-labs — Flux image models
- runwayml — Image / video

## Community / fine-tunes

- HuggingFaceH4 — Zephyr, alignment work
- NousResearch — Hermes line
- teknium — Open finetunes
- togethercomputer — RedPajama, OpenChatKit
- openchat — OpenChat models

## Notes

- Variant collapsing (Llama-3-70B-Instruct vs -GGUF-Q4 etc.) happens before
  ranking — we surface the canonical base release and mention notable variants
  in the body.
- Org renames are handled via an alias table maintained alongside the loader.
