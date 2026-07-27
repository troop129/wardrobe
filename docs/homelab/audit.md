# Repo audit: wardrowbe vs tandpfun/wardrobe

## Goals this needs to satisfy

1. Runs on an always-on Windows PC at home.
2. Primary interface is a bedroom Android tablet/iPad, used over the LAN.
3. Usable from the LAN generally (any device on the home network).
4. AI should be free/local (Ollama) where possible; OpenAI (or similar) acceptable
   if meaningfully better, or for ingestion only.
5. Should combine the better parts of two repos: this one (`wardrowbe`) and
   [tandpfun/wardrobe](https://github.com/tandpfun/wardrobe).
6. Usable from a phone too.
7. Long-term: accessible outside the home, so a second person (girlfriend) can
   maintain her own wardrobe and use it independently.

## This repo: `wardrowbe`

Full self-hosted wardrobe app, already very close to the target:

- **Stack**: FastAPI backend + SQLAlchemy/Postgres, Redis + `arq` background
  worker, Next.js 14 frontend, wired together in
  [`docker-compose.yml`](../../docker-compose.yml).
- **AI is provider-agnostic today** — [`backend/app/config.py`](../../backend/app/config.py)
  takes an OpenAI-compatible `AI_BASE_URL` / `AI_API_KEY` / `AI_VISION_MODEL` /
  `AI_TEXT_MODEL`. Ollama, OpenAI, LocalAI, and Azure OpenAI all work by changing
  `.env` only ([`.env.example`](../../.env.example) has ready-made blocks for
  each). The default already targets `http://host.docker.internal:11434/v1`
  (Ollama), and `docker-compose.yml` already adds
  `extra_hosts: host.docker.internal:host-gateway`, which is exactly what's
  needed on Docker Desktop for Windows.
- **Multi-user / sharing is already built in** —
  [`backend/app/models/family.py`](../../backend/app/models/family.py) has
  `Family` + `FamilyInvite` with invite tokens/roles, and the frontend has an
  [invite](../../frontend/app/invite/page.tsx) +
  [onboarding](../../frontend/app/onboarding/page.tsx) flow. This is the
  mechanism a second user would use to join and manage their own wardrobe later
  — no rearchitecting needed for goal 7.
- **Auth** is pluggable: dev email/name login (no setup) or OIDC
  ([`frontend/lib/auth.ts`](../../frontend/lib/auth.ts)). Fine for LAN-only now;
  OIDC or forward-auth can be layered on for remote access later.
- **Mobile-friendly already**: `mobile-nav.tsx`, `mobile-sidebar.tsx`,
  responsive layout — works on phone/tablet browsers without extra work.
- **Features**: AI auto-tagging, weather-based outfit suggestions, wash
  tracking, wear history/analytics, pairings, a "Studio" outfit-builder canvas,
  ntfy/Mattermost/email notifications, k8s manifests, multi-arch images.
- **Extensibility hook for external tagging**: `tagging_status` lifecycle in
  [`backend/app/models/item.py`](../../backend/app/models/item.py) plus
  `AI_VISION_ENABLED=false` lets an external agent submit tags via API instead
  of the internal AI — could be reused for an agentic import flow similar to
  tandpfun's Codex skills, if ever wanted.

## Other repo: `tandpfun/wardrobe`

Much smaller, single-purpose tool — not a fit as a *base*, but has two features
worth porting in (see [roadmap.md](./roadmap.md)):

- Single Vite app, `data/library.json` as the "database" — no Postgres, no
  multi-user/auth, no Docker setup.
- Hard-wired to OpenAI (`OPENAI_API_KEY`, `OPENAI_VISION_MODEL`,
  `OPENAI_IMAGE_MODEL=gpt-image-2`) — **no Ollama/local-model support**,
  conflicting with goal 4 if used as the base.
- Standout feature: **modeled/virtual-try-on photos** generated with
  `gpt-image` — a photorealistic preview of a person wearing an item/outfit —
  plus a clean, card-based gallery UI. Genuinely nicer visually than
  wardrowbe's current wardrobe grid and flat-lay "Studio" canvas, but the
  try-on generation depends on a paid OpenAI image-generation model; no
  local/free equivalent exists today.
- Import flow is built around Codex CLI skills (agentic terminal import), not a
  tablet-friendly web upload flow.

## Decision

Build on **wardrowbe** (this repo). It already satisfies goals 1-3, 4
(partially — see [ai-setup.md](./ai-setup.md)), 6, and has the data model for
goal 7 ready to go. Two things get ported in from tandpfun rather than left as
"maybe later" — tracked in [roadmap.md](./roadmap.md):

1. **Gallery UI** — restyle wardrowbe's item grid/detail views to match
   tandpfun's cleaner card-gallery look. Frontend-only change.
2. **Virtual try-on** — opt-in "generate modeled photo" action using OpenAI's
   image-generation model, as a proof of concept to decide if it's worth the
   ongoing cost.
