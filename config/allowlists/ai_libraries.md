# Tracked AI Libraries

Drives PyPI / npm release polling for the `ai_libraries` section, and the
onboarding picker for `trackers.libraries`.

Format: `- name (ecosystem) — purpose`

Where `ecosystem` is `pypi` or `npm`. The slug we store in `trackers.libraries`
is `ecosystem:name` (e.g. `pypi:transformers`, `npm:ai`).

## Frameworks & orchestration

- langchain (pypi) — LLM application framework
- langgraph (pypi) — Stateful graphs for agents
- llama-index (pypi) — RAG / data framework
- haystack-ai (pypi) — RAG framework (deepset)
- autogen-agentchat (pypi) — Multi-agent conversations
- crewai (pypi) — Role-based agent crews
- dspy-ai (pypi) — Declarative LM programs
- pydantic-ai (pypi) — Pydantic-native agent framework
- instructor (pypi) — Structured outputs
- guardrails-ai (pypi) — Output validation
- ai (npm) — Vercel AI SDK
- @langchain/core (npm) — JS/TS LangChain core
- llamaindex (npm) — JS port of LlamaIndex

## Foundation & training

- transformers (pypi) — Hugging Face Transformers
- accelerate (pypi) — Distributed training
- peft (pypi) — Parameter-efficient fine-tuning
- trl (pypi) — RLHF / DPO trainers
- datasets (pypi) — HF Datasets
- tokenizers (pypi) — Fast tokenizers
- diffusers (pypi) — Image / video diffusion
- sentence-transformers (pypi) — Embedding models
- unsloth (pypi) — Memory-efficient fine-tuning

## Inference & serving

- vllm (pypi) — High-throughput serving
- sglang (pypi) — Structured-generation serving
- llama-cpp-python (pypi) — GGUF / CPU inference
- exllamav2 (pypi) — Quantized GPU inference
- mlx-lm (pypi) — Apple Silicon inference
- text-generation-inference (pypi) — Hugging Face TGI

## Vector / RAG infrastructure

- chromadb (pypi) — Vector DB
- qdrant-client (pypi) — Qdrant client
- pinecone (pypi) — Pinecone client
- weaviate-client (pypi) — Weaviate client
- lancedb (pypi) — LanceDB
- faiss-cpu (pypi) — FAISS

## Eval & observability

- ragas (pypi) — RAG evaluation
- trulens-eval (pypi) — LLM eval
- langsmith (pypi) — LangChain observability
- mlflow (pypi) — Experiment tracking
- arize-phoenix (pypi) — LLM observability
- braintrust (pypi) — Eval / observability
- langfuse (pypi) — Tracing / observability

## Vendor SDKs

- anthropic (pypi) — Anthropic Python SDK
- openai (pypi) — OpenAI Python SDK
- google-generativeai (pypi) — Gemini SDK
- mistralai (pypi) — Mistral SDK
- cohere (pypi) — Cohere SDK
- together (pypi) — Together AI SDK
- @anthropic-ai/sdk (npm) — Anthropic JS SDK
- openai (npm) — OpenAI JS SDK

## Agent runtime / tools

- browser-use (pypi) — LLM-controlled browser
- e2b (pypi) — Code-interpreter sandbox
- modal (pypi) — Serverless GPU runtime

## Notes

- Major and minor releases are always considered. Patch releases enter the
  digest only when the user has the lib in `trackers.libraries`.
- Pre-releases (a/b/rc/dev) are skipped by default.
- Alert rate cap: at most 1 release/lib/day, unless a breaking change is
  detected in the release notes.
