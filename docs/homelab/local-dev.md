# Fast local test loop (Mac, no Docker builds)

`docker compose -f docker-compose.yml -f docker-compose.dev.yml up` (see the
root [README](../../README.md#development-mode)) already gives hot reload
once it's built. The problem is the *build* itself: on the Mac, building the
backend image (compiles/installs `onnxruntime`+`rembg` for background
removal, apt packages, etc.) and the frontend image can take a long time, and
anything that touches a `Dockerfile` or dependency file forces another one.

`scripts/dev-local.sh` skips Docker for the app code entirely:

- **Postgres + Redis** run in their normal small pre-built Alpine images
  (`postgres:15-alpine` / `redis:7-alpine`) — no build step, seconds to start.
- **Backend** runs directly on the Mac in a venv managed with
  [`uv`](https://docs.astral.sh/uv/) (this repo's `backend/uv.lock` is
  already uv-managed - install uv first if you don't have it):
  `uvicorn app.main:app --reload`.
- **Frontend** runs directly on the Mac: `next dev` (already hot-reloads).

Nothing here touches the real deployment on the Windows host or its `.env`.
Postgres/Redis run as two plain `docker run` containers with dedicated names
and ports (`wardrobe-devlocal-postgres`/`-redis`, ports 55432/56379) —
**deliberately not** `docker-compose.yml`, which pins fixed
`container_name`s (`wardrobe-db`/`wardrobe-redis`). Reusing that file under a
different Compose project name still collides on those names: `docker
compose -p <anything-else> down` will happily stop/remove a same-named
container from a *different* project, including a real stack you already
have running locally. Everything else lives under a gitignored `.dev-local/`
directory plus a gitignored `backend/.env` for local secrets.

## Usage

```bash
./scripts/dev-local.sh
```

First run: creates `backend/.venv`, installs `backend/requirements.txt`,
installs frontend `node_modules`, starts Postgres/Redis, runs Alembic
migrations, writes a default `backend/.env` (AI disabled — see below). Then:

- App: <http://localhost:3000>
- API docs: <http://127.0.0.1:8000/docs>
- Logs: `tail -f .dev-local/logs/*.log`

Every run after that is just starting three already-installed processes —
no rebuild, no reinstall (`pip`/`npm` are re-run but no-op when nothing
changed). Ctrl+C stops the backend/frontend/worker; Postgres/Redis are left
running so the *next* invocation is instant. Stop them when you're done for
the day:

```bash
./scripts/dev-local-down.sh          # keeps the data volume
./scripts/dev-local-down.sh -v       # also wipes it (fresh DB next time)
```

### Flags

| Flag | What it adds | When you need it |
|---|---|---|
| *(none)* | backend + frontend, `AI_INTERNAL_ENABLED=false` | UI/API work that doesn't touch AI tagging/suggestions — fastest, free |
| `--worker` | also runs the `arq` background worker | testing AI tagging/suggestion jobs actually processing |
| `--extras` | installs `requirements-extras.txt` (`rembg`, ~500MB) | testing background-removal cutouts |
| `--full` | both of the above | full feature parity with the real deployment |

## Testing AI features locally

By default `backend/.env` (generated on first run) sets
`AI_INTERNAL_ENABLED=false` so uploads work but tagging/suggestions are
skipped — no API key needed, nothing to wait on. To test the real thing,
edit `backend/.env` (it's gitignored, safe to put a real key in) using the
same options as the root [`.env.example`](../../.env.example), e.g.:

```env
AI_INTERNAL_ENABLED=true
AI_BASE_URL=https://api.openai.com/v1
AI_API_KEY=sk-...
AI_VISION_MODEL=gpt-5.6-terra
AI_TEXT_MODEL=gpt-5.6-luna
```

Then re-run with `--worker` (tagging/suggestion jobs run in the worker, not
the API process). This can reuse the same OpenAI key used on the Windows
deployment — it's a separate `.env` file, not shared state, so there's no
risk of the two setups fighting over config.

## When you still want the Docker route

- Confirming the actual `Dockerfile`s build cleanly (this script never
  exercises them) — do this before pushing if you touched either Dockerfile
  or a dependency file; `ci.yml`'s `docker-build` job also checks this on
  every push/PR.
- Reproducing something environment-specific to the container (file
  permissions via `PUID`/`PGID`, the entrypoint scripts, etc).

For everything else — UI changes, API endpoints, most backend logic — this
script is the faster loop.
