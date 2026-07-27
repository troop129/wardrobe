# AI provider plan (Ollama-first)

Goal: free/local AI (Ollama) wherever it's good enough, with paid APIs
(OpenAI, etc.) as a fallback only where it's meaningfully better, or for
ingestion only.

## The app's AI config model

[`backend/app/config.py`](../../backend/app/config.py) exposes one
OpenAI-compatible provider config used for both capabilities:

- `AI_BASE_URL` / `AI_API_KEY`
- `AI_VISION_MODEL` — used for tagging photos (colors, type, pattern, etc.)
- `AI_TEXT_MODEL` — used for outfit suggestions/pairings

Important limitation: there is currently **one** `AI_BASE_URL`/`AI_API_KEY` for
both capabilities — you can pick different *model names* for vision vs. text,
but not different *providers/endpoints* for each, without adding a small proxy
in front (see "Mixed provider option" below).

Per-capability switches also exist (`AI_INTERNAL_ENABLED`, `AI_VISION_ENABLED`,
`AI_TEXT_ENABLED`) to disable internal AI entirely and defer to an external
agent (via the `tagging_status` lifecycle in
[`backend/app/models/item.py`](../../backend/app/models/item.py)) — not needed
for the initial setup, but useful if we ever want an agentic import flow.

## Hardware

- GPU: RTX 3070 Ti — **8GB VRAM**, the binding constraint.
- RAM: 32GB DDR4 @2666MHz — plenty of capacity, but slow; models that spill out
  of VRAM into system RAM will be noticeably slower than on faster RAM.
- CPU: Ryzen 7 3700X — not the bottleneck for GPU-accelerated inference.
- Usage pattern is bursty/occasional (tag a photo on upload, generate a
  suggestion once a day), not continuous/batch — so a model that fits fully in
  8GB VRAM will feel fast enough even though it's a "small" model by general
  LLM standards.

## Recommended starting models

Install Ollama **natively on Windows** (not inside Docker) — the compose files
already default `AI_BASE_URL` to `http://host.docker.internal:11434/v1` and add
`extra_hosts: host.docker.internal:host-gateway`, which works out of the box
with Docker Desktop on Windows.

- **Vision** (tagging): `llava:7b` or `qwen2.5vl:7b` — both comfortably fit in
  8GB VRAM.
- **Text** (suggestions/pairings): `gemma3:latest` (4B) or `qwen2.5:7b` — small
  and fast; Ollama loads one model at a time per request so this coexists fine
  with the vision model.

```bash
ollama pull llava:7b
ollama pull gemma3:latest
```

`.env` (already the default in [`.env.example`](../../.env.example)):

```env
AI_BASE_URL=http://host.docker.internal:11434/v1
AI_API_KEY=not-needed
AI_VISION_MODEL=llava:7b
AI_TEXT_MODEL=gemma3:latest
```

## If quality/speed disappoints

Try in this order before reaching for a paid API:

1. Swap the vision model only — try `qwen2.5vl:7b` or a combined multimodal
   model like `gemma3:12b` (still fits in 8GB at Q4 quantization).
2. Increase `AI_TIMEOUT` (local models can be slower than cloud APIs;
   `.env.example` notes worst case is `AI_TIMEOUT * AI_MAX_RETRIES`).
3. Only then consider OpenAI (`gpt-4o-mini` for vision is cheap and fast) —
   either fully switching `AI_BASE_URL`/keys to OpenAI, or via the mixed-mode
   option below if you want to keep suggestions free/local.

## Mixed provider option (Ollama for text, OpenAI for vision only)

Not needed initially, but documented since it maps to goal 4's "or for
ingestion only" — since the app only supports one `AI_BASE_URL` for both
capabilities today, true mixing needs a small local OpenAI-compatible proxy
(e.g. [LiteLLM](https://github.com/BerriAI/litellm) running as an extra
container) that routes a vision-model alias to OpenAI and a text-model alias to
local Ollama, with the app's `AI_BASE_URL` pointed at the proxy instead of
either backend directly. Treat as a later optimization if/when it's worth the
extra moving part.

## Virtual try-on (separate concern)

The tandpfun-style modeled/virtual-try-on feature (see
[audit.md](./audit.md), [roadmap.md](./roadmap.md)) uses an OpenAI
*image-generation* model (`gpt-image`), which has no local/free equivalent.
This would be a second, independent `AI_IMAGE_*`-style config block used only
by that feature — it does not affect the Ollama setup for tagging/suggestions
above.
