# Windows hosting runbook

Target: run the full docker-compose stack on the Windows PC (`10.0.0.246` /
`desktop-lms2bct`), reachable from the bedroom tablet, phone, and Mac over the
LAN. See [remote-access.md](./remote-access.md) for how these commands get run
remotely from the Mac over SSH, and [ai-setup.md](./ai-setup.md) for the AI
model choices referenced below.

Status: **steps 1–5 done** (executed remotely over SSH — see gotchas below).
Only step 6 (log in from your actual client devices + validate AI quality)
remains, and that's on you rather than something to automate. Check the todo
list on the active Cursor plan (or this repo's task tracker, if promoted
there) for live progress.

## 1. Install host dependencies (on the Windows PC) — ✅ done

- **Docker Desktop** (WSL2 backend) — <https://www.docker.com/products/docker-desktop/>
  - Requires WSL2 enabled: `wsl --install` (may require a reboot).
- **Ollama** — <https://ollama.ai> (native Windows installer, not run inside Docker)
  - Then pull the models from [ai-setup.md](./ai-setup.md):
    ```powershell
    ollama pull llava:7b
    ollama pull gemma3:latest
    ```

Installed: Docker Desktop 4.83.0 (Docker Engine 29.6.2, WSL2 backend) and
Ollama 0.32.4, with `llava:7b` and `gemma3:latest` pulled and smoke-tested
(container run + a live chat completion). Both are registered to auto-start
on login (Docker Desktop does this itself; Ollama didn't, so a
`LaunchOllamaApp` Scheduled Task was added — see gotchas below).

### Gotchas hit doing this over SSH (relevant again for step 4)

- **`wsl --install`/`wsl --update` failed with "The Windows Subsystem for
  Linux is not installed"** even after enabling the
  `Microsoft-Windows-Subsystem-Linux` / `VirtualMachinePlatform` Windows
  optional features and rebooting. Fix: install the WSL package itself via
  `winget install --id Microsoft.WSL --source winget` (it's published on the
  regular winget source now, not just the Store).
- **`winget` prompted interactively for the MS Store source agreement** and
  hung over non-interactive SSH. Fix: always scope to
  `--source winget --accept-source-agreements --accept-package-agreements`.
- **GUI apps (Docker Desktop, Ollama's tray app) silently die when started
  via `Start-Process` over SSH**, even with an active RDP session open — SSH
  commands run in a non-interactive logon session that can't create windows.
  Fix: register a Scheduled Task with `-Principal ... -LogonType Interactive
  -UserId troop` targeting the real executable, then `Start-ScheduledTask`;
  it runs inside the actual interactive (RDP) session instead.
- **`docker pull`/`docker run` failed with `error getting credentials - err:
  exit status 1, out: 'A specified logon session does not exist.'`** even for
  fully public/anonymous images, and even after removing `credsStore` from
  `~/.docker/config.json`. Root cause: Docker Desktop's credential lookup is
  tied to the Windows logon session, and plain SSH creates a *different*
  logon session than the interactive RDP one for the same user — this is a
  DPAPI/logon-session mismatch, not a config problem. **Fix that actually
  works: run `docker`/`docker compose` commands the same way as the GUI-app
  workaround above** — via a Scheduled Task with `-LogonType Interactive`
  that executes inside the real interactive session. Plan on doing this for
  step 4's `docker compose pull` / `docker compose up -d` too, rather than
  running them directly over `ssh wardrobe-win '...'`.

## 2. Get the repo onto the Windows host — ✅ done

Either:
- `git clone https://github.com/Anyesh/wardrowbe.git` directly on the Windows
  host, or
- Push this working copy to your own remote/fork and clone that instead (do
  **not** push a real `.env` — it's already gitignored).

Done: installed Git (`winget install --id Git.Git`) and cloned
`https://github.com/troop129/wardrobe.git` (the personal fork, see
[README.md](./README.md)) to `C:\Users\troop\wardrowbe`.

## 3. Configure `.env` — ✅ done

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

Done: `.env` generated from `.env.example` with real random secrets for
`POSTGRES_PASSWORD`/`SECRET_KEY`/`NEXTAUTH_SECRET`, `DEBUG=true`,
`NEXTAUTH_URL=http://10.0.0.246:3000`, and the Ollama `AI_*` block left at its
defaults.

## 4. Start the stack — ✅ done

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

Done: all 5 containers (`db`, `redis`, `backend`, `worker`, `frontend`) came
up healthy, all Alembic migrations applied cleanly on first boot, and the
health check returned `{"status":"healthy"}`. Ran via the same
interactive-session Scheduled Task workaround as step 1's gotchas (needed for
`docker compose pull`'s credential lookup, not for `up`/`exec`, but simplest
to run the whole sequence that way).

## 5. Open the firewall for LAN clients — ✅ done

Only port **3000** (frontend) needs to be reachable from other devices — the
frontend proxies `/api/v1/*` to the backend internally over the Docker network
(see [`frontend/app/api/v1/[...path]/route.ts`](../../frontend/app/api/v1/%5B...path%5D/route.ts)),
so tablet/phone/Mac never need direct access to ports 8000/5432/6379.

```powershell
New-NetFirewallRule -DisplayName "Wardrobe Frontend" -Direction Inbound -Protocol TCP -LocalPort 3000 -Action Allow -Profile Private
```

(Scoped to `Private` to match the network-profile fix in
[remote-access.md](./remote-access.md); widen only if needed.)

Done: rule created, scoped to `Private`. Verified reachable from the Mac dev
machine over the LAN — `curl http://10.0.0.246:3000` returns the frontend's
`200 OK`, and `curl http://10.0.0.246:3000/api/v1/health` (through the
frontend's API proxy) returns `{"status":"healthy"}`. Not yet verified from
the actual tablet/phone — that's step 6, below.

## 6. Use it from client devices — not yet done (up to you)

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
