# Roadmap: after the base deployment is stable

These are deliberately sequenced *after* [deployment.md](./deployment.md) is
working end-to-end (LAN access, AI tagging validated). See
[audit.md](./audit.md) for why these specific items were chosen.

## 1. Gallery UI port (from tandpfun/wardrobe)

**Status: done** — wardrobe grid, item cards, item detail dialog, and a calmer
sidebar/header shell. Thumbnails use the existing free `rembg` pipeline:
automatic white-background cutouts on upload (`AUTO_BACKGROUND_REMOVAL`, default
on) plus a bulk “clean up backgrounds” action in the wardrobe toolbar.

- Scope: [`frontend/components`](../../frontend/components) — item cards, grid
  layout, item detail dialog, sidebar/header. Backend: arq job +
  `POST /items/bulk/remove-background` (no data-model changes).
- Paid OpenAI `gpt-image` product-shot regeneration (tandpfun import skill
  style) remains **deferred** — see item 2 and [ai-setup.md](./ai-setup.md).

## 2. Virtual try-on proof of concept (from tandpfun/wardrobe)

An opt-in "generate modeled photo" action on an item or outfit, using an
OpenAI image-generation model (`gpt-image-1`/`gpt-image-2`) to produce a
photorealistic preview of a person wearing it — tandpfun's standout feature.

Status: **explicitly a "try it and see" experiment** — build the smallest
useful version, judge quality and OpenAI cost, then decide whether to keep it.

Rough shape (to be refined into a real implementation plan before building):

- New, independent config block (e.g. `AI_IMAGE_BASE_URL` /
  `AI_IMAGE_API_KEY` / `AI_IMAGE_MODEL`) — kept separate from the existing
  `AI_BASE_URL` used for Ollama tagging/text, since this feature specifically
  needs a paid API regardless of the Ollama setup (see
  [ai-setup.md](./ai-setup.md)).
- A reference photo of the person (similar to tandpfun's
  `data/model-reference.png` convention) stored under the existing
  `STORAGE_PATH`.
- New backend endpoint/service that composes a prompt from the item(s) +
  reference photo and calls the image-generation model, storing the result
  as a new image variant alongside the existing cutout image
  (`backend/app/services/image_service.py`, `backend/app/models/item.py` /
  outfit models).
- A "Generate modeled photo" button in the item detail dialog / Studio outfit
  view, with a loading/regenerate/approve flow similar to the existing
  background-removal review flow.

## 3. Remote access for a second user (deferred)

Long-term goal: a second person (girlfriend) can access the app from outside
the home to manage her own wardrobe, with **minimal setup on her end** (no VPN
app to install).

Direction chosen when this comes up: **Cloudflare Tunnel** in front of the
`frontend` service, gated by **Cloudflare Access** (email one-time-code login
— no password management, no app install). This is additive:

- Add a `cloudflared` container/service to `docker-compose.yml` pointed at
  `frontend:3000`, using a tunnel token from the Cloudflare dashboard.
- Configure Cloudflare Access policies to allow only her email (and yours).
- Revisit auth at that point: LAN dev-credential login is fine while everything
  is LAN-only, but internet-facing access should move to OIDC or rely on
  Cloudflare Access as the auth boundary instead of the app's dev provider.
- No data-model changes needed — the existing `Family`/`FamilyInvite` model
  (see [audit.md](./audit.md)) already supports her having her own account or
  being invited into a shared family.

Not designed in further detail yet — pick this back up once the LAN deployment
and initial feature work above feel solid.
