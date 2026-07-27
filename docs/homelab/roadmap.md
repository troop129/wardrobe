# Roadmap: after the base deployment is stable

These are deliberately sequenced _after_ [deployment.md](./deployment.md) is
working end-to-end (LAN access, AI tagging validated). See
[audit.md](./audit.md) for why these specific items were chosen.

## 1. Gallery UI port (from tandpfun/wardrobe) — done

Frontend-only visual refresh of the wardrobe item grid/detail views to match
tandpfun's cleaner, card-based gallery look.

- Scope: [`frontend/components`](../../frontend/components) — item cards, grid
  layout, item detail dialog, plus the sidebar/header shell (fewer/quieter
  icons, calmer palette). No backend/data-model changes on the UI side.
- Approach: a design pass on existing components rather than a rewrite — kept
  all current functionality (bulk actions, filters, wash tracking badges,
  etc.), just restyled the presentation layer. New warm/quiet palette tokens
  live in [`frontend/app/globals.css`](../../frontend/app/globals.css); the
  item detail dialog's dense icon toolbar was regrouped into primary actions
  (favorite/edit/close) plus a secondary overflow menu.
- **AI thumbnails**: rather than a new paid image-generation feature, this
  extended the existing free/local `rembg`-based background-removal pipeline
  (`backend/app/services/image_service.py`) to run automatically on upload
  (`auto_background_removal` config flag, gated on
  `background_removal.is_available()`) and added a bulk "clean up
  backgrounds" action (`POST /items/bulk/remove-background`,
  `useBulkRemoveBackgroundItems`) so every item ends up on a neat, uniform
  white background at no extra cost. A paid AI-generated-thumbnail approach
  stays a deferred future option — same bucket as item 2 below.
- No dependency on any AI/API changes — this stayed safe to do without
  touching the paid-AI provider setup.

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
