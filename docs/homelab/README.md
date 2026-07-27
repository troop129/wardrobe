# Homelab wardrobe deployment plan

This folder documents the plan (and running status) for turning this repo into a
self-hosted wardrobe app for personal use: hosted on a Windows PC, used from a
bedroom tablet/iPad and phones over the LAN now, with remote access for a second
user (girlfriend) as a later phase.

It exists so the setup is reproducible and debuggable later, without having to
reconstruct decisions from chat history.

## Documents in this folder


| Doc                                                                     | Contents                                                                                                                               |
| ----------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| [audit.md](./audit.md)                                                  | Comparison of this repo (`wardrowbe`) vs [tandpfun/wardrobe](https://github.com/tandpfun/wardrobe), and why we're building on this one |
| [remote-access.md](./remote-access.md)                                  | How the dev machine (Mac) gets SSH access to the Windows host, key locations, and troubleshooting steps already hit                    |
| [ai-setup.md](./ai-setup.md)                                            | Ollama model choices sized for the actual GPU/RAM, fallback options                                                                    |
| [deployment.md](./deployment.md)                                        | Step-by-step Windows hosting runbook (Docker, `.env`, firewall, LAN access)                                                            |
| [roadmap.md](./roadmap.md)                                              | Deferred/future work: gallery UI port, virtual try-on POC, remote access for a second user                                             |
| [reference/tandpfun-wardrobe/](./reference/tandpfun-wardrobe/README.md) | Read-only snapshot of tandpfun/wardrobe (skills, gallery UI source, screenshots) pulled in for the roadmap items above                 |




## This fork

This repo is a personal fork of upstream
[Anyesh/wardrowbe](https://github.com/Anyesh/wardrowbe), pushed to
[troop129/wardrobe](https://github.com/troop129/wardrobe). Maintainer-facing
files not relevant to a single-user personal deployment were removed
(release-please/CHANGELOG, `docker-publish`/`issue-context`/`pr-context`
GitHub Actions workflows, issue/PR templates, `FUNDING.yml`, `k8s/` manifests,
`CONTRIBUTING.md`, `SECURITY.md`, the Authelia OIDC test compose file). Kept:
`ci.yml` (still useful for catching breakage), `dependabot.yml`,
`.pre-commit-config.yaml`, all Docker Compose files, `nginx/`, `Caddyfile.dev`.

## Target environment (reference)

Filled in as facts were confirmed during setup — treat as the source of truth over
anything said earlier in chat.

- **Host machine**: Windows 11 Pro (build 26100), hostname `desktop-lms2bct`
- **CPU**: AMD Ryzen 7 3700X (8c/16t)
- **GPU**: NVIDIA RTX 3070 Ti (8GB VRAM) — the binding constraint for local AI model sizing
- **RAM**: 32GB DDR4 @2666MHz (slower than typical; avoid models that spill out of VRAM)
- **LAN**: home WiFi `RasheedFamily 4`, host currently at `10.0.0.246` (reclassified as a **Private** network profile — see [remote-access.md](./remote-access.md))
- **Dev machine**: macOS, running this Cursor session, reaches the host over SSH (see [remote-access.md](./remote-access.md))
- **Client devices**: bedroom Android tablet/iPad (primary interface), phone, Mac browser — all LAN-only for now



## Current status

See the todo list attached to the active plan for live status; as of this doc's
last edit:

- [x] Remote shell (SSH) access from Mac to the Windows host
- [x] Docker Desktop + Ollama installed on the Windows host
- [x] `.env` configured and stack deployed
- [x] Verified LAN access from the Mac (`curl` to `10.0.0.246:3000` + health
      check) — not yet verified from the actual tablet/phone
- [x] AI provider decided and deployed — OpenAI for both vision
      (`gpt-5.6-terra`) and text (`gpt-5.6-luna`), source-built and verified
      via `GET /api/v1/capabilities` (see [ai-setup.md](./ai-setup.md))
- [ ] AI output quality validated with a real upload/wardrobe (the provider
      choice above used a synthetic benchmark, not real items yet)
- [x] Gallery UI port (from tandpfun) — clean grid/cards, calmer shell, auto +
      bulk white-background thumbnails via rembg
- [ ] Virtual try-on POC (from tandpfun, OpenAI `gpt-image`)
- [ ] Remote access for second user (deferred — Cloudflare Tunnel direction)