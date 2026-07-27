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

> Superseded by the "Quality decision" section below, which is what's actually
> deployed now. Kept here as the initial-setup history/rationale.

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

## Quality decision: mixed provider (OpenAI vision + local text)

Status: **decided and implemented** — first-upload sanity check (4 real items:
white cargo pants, brown hoodie, Air Jordan 1s, a t-shirt) found `llava:7b`
getting types wrong (jeans instead of pants, shirt instead of hoodie) and the
free-text description contradicting the structured tags on the same item.

Tried in order:

1. **Swapped to `qwen2.5vl:7b`** (still local/free) — fixed most of the type
   errors and made the tags/description passes consistent with each other, but
   still got material wrong (denim on cotton cargo pants) and subtype wrong
   (low-top on a high-top Jordan 1), and hallucinated at higher input
   resolution on one item.
2. **A/B tested `qwen2.5vl:7b` vs OpenAI `gpt-5.6-terra`** on the same 4 photos,
   same prompts, at both 512px (current preprocessing) and 1024px. Terra got
   every field right on every item, including the ones qwen2.5vl:7b missed
   (subtype, material), and stayed accurate at 1024px where qwen2.5vl:7b
   regressed.

Decision: since tagging only runs once per item, the cost of a paid vision
model is trivial for a whole wardrobe (roughly a fraction of a cent per item at
this prompt/image size), while suggestions/pairings run far more often and
should stay free/local. This is now wired natively in the app —
`AI_VISION_BASE_URL`/`AI_VISION_API_KEY` override the vision call only, falling
back to `AI_BASE_URL`/`AI_API_KEY` (used for text) when unset. **No LiteLLM
proxy needed** (see below for why one used to seem necessary).

Current config:

```env
# Text stays local/free
AI_BASE_URL=http://host.docker.internal:11434/v1
AI_API_KEY=not-needed
AI_TEXT_MODEL=qwen3.5:9b

# Vision goes to OpenAI (one-time cost per item, meaningfully better quality)
AI_VISION_BASE_URL=https://api.openai.com/v1
AI_VISION_API_KEY=sk-...
AI_VISION_MODEL=gpt-5.6-terra
```

`qwen3.5:9b` (~6.6GB at Q4) replaces the old `gemma3:latest` (4B) text model —
now that vision isn't sharing the 8GB VRAM with a local vision model, there's
room for a meaningfully stronger local text model for suggestions/pairings.

Note: newer OpenAI models (the gpt-5.x/gpt-5.6 family) reject the legacy
`max_tokens` param and require `max_completion_tokens` instead. The app
detects this from the error response and retries automatically — no config
needed, but worth knowing if you see it in logs on a fresh model swap.

If cost ever becomes a concern, `gpt-4o-mini` or `gpt-5.6-luna` are cheaper
fallbacks for `AI_VISION_MODEL` — quality wasn't tested for those specifically,
so re-run the same A/B comparison before switching.

### Why a proxy isn't needed (superseded)

Earlier draft of this doc assumed the app's single `AI_BASE_URL`/`AI_API_KEY`
pair meant mixing providers required a small OpenAI-compatible proxy (e.g.
[LiteLLM](https://github.com/BerriAI/litellm)) in front to route vision/text
model-aliases to different backends. Since this was a small, contained change
and we were already switching this deployment to build from source (see
[deployment.md](./deployment.md)), we added native capability-scoped endpoint
config to `AIService` instead — simpler, no extra container.

## Update: text moved off Ollama too (GPT-5.6 Luna)

Status: **decided and implemented** (host `.env` updated, rebuilt from source,
verified via `GET /api/v1/capabilities`).

The "mixed provider" setup above was documented but never actually deployed to
the host `.env` — it was still sitting at the original `llava:7b`/`gemma3:latest`
defaults from initial setup. When it finally got exercised, local text
generation on the 3070 Ti (`qwen3.5:9b`) felt noticeably slow for interactive
use (outfit suggestions/pairings while using the app), so before deploying it
for real we looked at free hosted-LLM options
([cheahjs/free-llm-api-resources](https://github.com/cheahjs/free-llm-api-resources))
as a speed fix, then decided to just use OpenAI for text too since credits
were already available for the account used for vision.

### Benchmark

Ran the real `recommendation.txt` prompt (a 20-item mock wardrobe, "dinner
date" / evening / 14°C context) against all three GPT-5.6 tiers, checking
wall-clock latency, JSON validity, and the outfit slot rules (exactly one
top/bottom/shoes, no duplicate items):

| Model | Time | Valid | Cost/call | Output tokens | Reasoning tokens |
|---|---|---|---|---|---|
| `gpt-5.6-luna` | **8.91s** | ✅ | **$0.0067** | 850 | 481 |
| `gpt-5.6-sol` | 11.97s | ✅ | $0.0235 | 510 | 262 |
| `gpt-5.6-terra` | 18.47s | ✅ | $0.0239 | 1322 | 1012 |

All three produced valid, correctly-structured outfits and picked essentially
the same strongest combo for outfit #1. Terra's copy was marginally more
observant (e.g. calling out "denim-on-denim" for a jeans + denim jacket pair,
weaving the exact temperature into a highlight), but it was also the
slowest *and* most expensive of the three here — it burned far more reasoning
tokens (1012) than Luna or even flagship Sol, the opposite of what its
mid-tier pricing would suggest. This was a single run per model, not a
rigorous statistical eval, but the gap is large enough to trust directionally.

Note: GPT-5.6 models require `max_completion_tokens` instead of the legacy
`max_tokens` (see the note above) — the app's auto-retry handles this in
production, but a standalone benchmark script needs to pass it explicitly.

Decision: **`gpt-5.6-luna` for text**, keep `gpt-5.6-terra` for vision (no
change there). Fallback path if Luna's quality disappoints on a real wardrobe
(the synthetic test items favor easy, distinct pieces) is `gpt-5.6-terra`.

Current config (both capabilities on one provider now, so the
`AI_VISION_BASE_URL`/`AI_VISION_API_KEY` override from the mixed-provider
setup above is no longer needed):

```env
AI_BASE_URL=https://api.openai.com/v1
AI_API_KEY=sk-...
AI_VISION_MODEL=gpt-5.6-terra
AI_TEXT_MODEL=gpt-5.6-luna
```

### Deployment gotcha hit doing this: CRLF-corrupted entrypoint scripts

Rebuilding `backend`/`worker`/`frontend` from source on the Windows host (per
the source-build compose change above) for the first time immediately crash-
looped all three containers with `exec /docker-entrypoint.sh: no such file or
directory`. Cause: this repo had no `.gitattributes`, so Windows git's default
`core.autocrlf=true` silently rewrote `backend/docker-entrypoint.sh` and
`frontend/docker-entrypoint.sh` to CRLF on checkout, which corrupts the
`#!/bin/sh` shebang once that file is `COPY`'d into the Linux container image.

Fix: added `.gitattributes` with `*.sh text eol=lf` to force LF regardless of
the checking-out platform. `git add --renormalize .` alone was **not**
sufficient to fix the already-checked-out working tree (it only affects what
gets staged/re-checked-out going forward, not existing on-disk bytes) — had to
explicitly strip the `\r` bytes from the two files in place before rebuilding
for the fix to actually take effect in that same session.

## Virtual try-on (separate concern)

The tandpfun-style modeled/virtual-try-on feature (see
[audit.md](./audit.md), [roadmap.md](./roadmap.md)) uses an OpenAI
*image-generation* model (`gpt-image`), which has no local/free equivalent.
This would be a second, independent `AI_IMAGE_*`-style config block used only
by that feature — it does not affect the Ollama setup for tagging/suggestions
above.
