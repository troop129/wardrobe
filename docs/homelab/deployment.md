# Windows hosting runbook

Target: run the full docker-compose stack on the Windows PC (`10.0.0.246` /
`desktop-lms2bct`), reachable from the bedroom tablet, phone, and Mac over the
LAN. See [remote-access.md](./remote-access.md) for how these commands get run
remotely from the Mac over SSH, and [ai-setup.md](./ai-setup.md) for the AI
model choices referenced below.

Status: **not yet executed** — this is the plan; check the todo list on the
active Cursor plan (or this repo's task tracker, if promoted there) for live
progress.

## 1. Install host dependencies (on the Windows PC)

- **Docker Desktop** (WSL2 backend) — <https://www.docker.com/products/docker-desktop/>
  - Requires WSL2 enabled: `wsl --install` (may require a reboot).
- **Ollama** — <https://ollama.ai> (native Windows installer, not run inside Docker)
  - Then pull the models from [ai-setup.md](./ai-setup.md):
    ```powershell
    ollama pull llava:7b
    ollama pull gemma3:latest
    ```

## 2. Get the repo onto the Windows host

Either:
- `git clone https://github.com/Anyesh/wardrowbe.git` directly on the Windows
  host, or
- Push this working copy to your own remote/fork and clone that instead (do
  **not** push a real `.env` — it's already gitignored).

## 3. Configure `.env`

Copy [`.env.example`](../../.env.example) to `.env` and set:

| Variable | Value | Why |
|---|---|---|
| `POSTGRES_PASSWORD` | a real secret | don't leave the placeholder |
| `SECRET_KEY` | `openssl rand -hex 32` (or PowerShell equivalent) | backend JWT signing |
| `NEXTAUTH_SECRET` | `openssl rand -hex 32` | NextAuth session encryption |
| `NEXTAUTH_URL` | `http://10.0.0.246:3000` (the host's LAN IP, **not** `localhost`) | NextAuth's callback logic needs to match the URL client devices actually use — see gotcha below |
| `DEBUG` | `true` (initially) | enables dev email/name login, no OIDC needed |
| `AI_BASE_URL` / `AI_VISION_MODEL` / `AI_TEXT_MODEL` | Ollama block from [ai-setup.md](./ai-setup.md) | already the default in `.env.example` |

> **Gotcha**: if `NEXTAUTH_URL` is left as `localhost`, login will appear to
> work on the host itself but silently break (redirect loops / cookie
> mismatches) from any other device on the LAN. Always set it to the LAN IP
> (or a stable hostname, if one is set up) that client devices will actually
> use.

Consider a **static LAN IP or DHCP reservation** for this PC in your router so
`10.0.0.246` (or whatever it becomes) doesn't change and break bookmarks/PWA
shortcuts on the tablet/phone.

## 4. Start the stack

```powershell
docker compose pull
docker compose up -d
docker compose exec backend alembic upgrade head
```

Verify:

```powershell
curl http://localhost:8000/api/v1/health
# Should return: {"status":"healthy"}
```

## 5. Open the firewall for LAN clients

Only port **3000** (frontend) needs to be reachable from other devices — the
frontend proxies `/api/v1/*` to the backend internally over the Docker network
(see [`frontend/app/api/v1/[...path]/route.ts`](../../frontend/app/api/v1/%5B...path%5D/route.ts)),
so tablet/phone/Mac never need direct access to ports 8000/5432/6379.

```powershell
New-NetFirewallRule -DisplayName "Wardrobe Frontend" -Direction Inbound -Protocol TCP -LocalPort 3000 -Action Allow -Profile Private
```

(Scoped to `Private` to match the network-profile fix in
[remote-access.md](./remote-access.md); widen only if needed.)

## 6. Use it from client devices

From the tablet, phone, and Mac browser: `http://10.0.0.246:3000` (or the
current LAN IP). Log in with dev credentials, complete onboarding, upload a
few items to sanity-check Ollama tagging quality/speed before relying on it.

On the tablet, "Add to Home Screen" (Chrome/Safari) gives an app-like
full-screen shortcut — no separate PWA build work needed for that.

## 7. Optional: HTTPS on the LAN

[`Caddyfile.dev`](../../Caddyfile.dev) already has a self-signed local TLS
config (`wardrobe.local`) if `https://` is wanted instead of plain `http://`
on the LAN. Not required for functionality.

## Follow-up after first login

- Validate AI tagging quality/speed with a real photo upload; see
  [ai-setup.md](./ai-setup.md) for what to try if it's unsatisfying.
- See [roadmap.md](./roadmap.md) for the gallery UI port, virtual try-on POC,
  and remote-access-for-a-second-user phases that come after this is stable.
