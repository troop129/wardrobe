# Reference snapshot: tandpfun/wardrobe

This directory is a **read-only reference snapshot**, not integrated code. It
was pulled in to have concrete material to work from when building the
[gallery UI port](../../roadmap.md) and [virtual try-on POC](../../roadmap.md),
since [tandpfun/wardrobe](https://github.com/tandpfun/wardrobe) is a different
stack (Vite + plain React + Express-style scripts) than this project
(Next.js + FastAPI) — nothing here gets imported/run directly, it's for design
and prompt reference only.

- **Source**: <https://github.com/tandpfun/wardrobe>
- **Commit**: `f44006cce7e4779e595a35b25fbbc8dabc68d7e4` (2026-07-15)
- **License**: MIT (`LICENSE` in this folder) — compatible with this project's
  MIT license, but keep attribution if any code is adapted.

## What's here and why

| Path | Why it's useful |
|---|---|
| `images/gallery.png`, `images/editor.png` | Visual reference for the [gallery UI port](../../roadmap.md) — what "the cleaner gallery UI" actually looks like (moved out of the upstream `docs/screenshots/` path into `images/` here since this repo's `.gitignore` has a blanket `screenshots/` rule) |
| `src/App.jsx`, `src/styles.css`, `src/OptimizedImage.jsx` | Gallery grid/card markup and styling to reference when restyling `frontend/components` in this repo (not a direct port — different framework/styling system, Tailwind/shadcn here vs plain CSS there) |
| `src/import-flow.jsx`, `src/import-flow.css` | Their upload/review/approve UX flow — relevant reference for polishing our own upload flow and, later, a "generate modeled photo" review step |
| `.agents/skills/import-clothes/`, `.agents/skills/generate-outfits/` | Codex skill definitions showing exactly how they prompt `gpt-image` for cutouts and modeled/virtual-try-on photos (`SKILL.md`, `agents/openai.yaml`, `references/outfit-image-prompt.md`) — the most directly useful reference for the [virtual try-on POC](../../roadmap.md), since it documents their actual prompt engineering for that feature |
| `public/manifest.webmanifest`, `public/sw.js` | They ship a real installable PWA (manifest + service worker). This repo doesn't have one yet — worth considering separately for the tablet/phone experience (not currently in [roadmap.md](../../roadmap.md), noted here as a spotted opportunity) |
| `UPSTREAM_README.md` | Their README as of the commit above, for config/env var reference |

## Re-pulling a fresher snapshot later

```bash
git clone --depth 1 https://github.com/tandpfun/wardrobe.git /tmp/tandpfun-wardrobe
```

Then copy whatever's needed from `/tmp/tandpfun-wardrobe` — don't `git subtree`/submodule it in, this snapshot approach was deliberate so it doesn't drag in `node_modules`/build tooling or create a dependency on their repo staying available.
