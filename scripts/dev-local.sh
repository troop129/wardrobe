#!/usr/bin/env bash
# Fast native dev loop for the Mac dev machine.
#
# Why this exists: docker-compose.dev.yml is fine once it's built, but the
# *first* build (and any Dockerfile/dependency change after that) means
# waiting on `docker compose build` again, which is slow on Mac. This script
# skips Docker entirely for the app code: Postgres/Redis run in tiny
# pre-built containers (no build step), and the backend/frontend run
# directly on the host with --reload / next dev hot reload. Net effect:
# first run takes about as long as `pip install` + `npm install`, every run
# after that is seconds.
#
# This is for local iteration only - it does NOT touch the real deployment
# on the Windows host (see docs/homelab/deployment.md) and does NOT need to
# match its .env. State lives under .dev-local/ (gitignored) and two plain
# `docker run` containers with dedicated names/volumes/ports
# (wardrobe-devlocal-postgres/-redis) - deliberately NOT docker-compose.yml,
# since that file pins fixed container_names (wardrobe-db/wardrobe-redis)
# that would collide with (and `down` would delete) any regular stack you
# already have running locally under those same names.
#
# Usage:
#   scripts/dev-local.sh            # backend + frontend, AI tagging off
#   scripts/dev-local.sh --worker   # also run the arq worker (needed for AI tagging jobs)
#   scripts/dev-local.sh --extras   # also install requirements-extras.txt (rembg, ~500MB)
#   scripts/dev-local.sh --full     # both of the above
#
# Stop with Ctrl+C (kills backend/frontend/worker). Postgres/Redis containers
# are left running so the next run is instant; stop them with
# scripts/dev-local-down.sh when you're done for the day.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

WITH_WORKER=0
WITH_EXTRAS=0
for arg in "$@"; do
  case "$arg" in
    --worker) WITH_WORKER=1 ;;
    --extras) WITH_EXTRAS=1 ;;
    --full)
      WITH_WORKER=1
      WITH_EXTRAS=1
      ;;
    -h | --help)
      # Print the leading comment block (everything up to the first blank
      # non-comment line) rather than a hardcoded line range.
      awk '/^#!/{next} /^#/{sub(/^# ?/, ""); print; next} {exit}' "${BASH_SOURCE[0]}"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg (see --help)" >&2
      exit 1
      ;;
  esac
done

PG_CONTAINER=wardrobe-devlocal-postgres
REDIS_CONTAINER=wardrobe-devlocal-redis
PG_VOLUME=wardrobe-devlocal-pgdata
DB_PORT=55432
REDIS_PORT=56379
STATE_DIR="$ROOT_DIR/.dev-local"
LOG_DIR="$STATE_DIR/logs"
STORAGE_DIR="$STATE_DIR/storage"
mkdir -p "$LOG_DIR" "$STORAGE_DIR"

echo "==> Starting Postgres ($PG_CONTAINER, port $DB_PORT)"
if docker ps -a --format '{{.Names}}' | grep -qx "$PG_CONTAINER"; then
  docker start "$PG_CONTAINER" > /dev/null
else
  docker run -d --name "$PG_CONTAINER" \
    -e POSTGRES_USER=wardrobe -e POSTGRES_PASSWORD=wardrobe -e POSTGRES_DB=wardrobe \
    -p "${DB_PORT}:5432" \
    -v "${PG_VOLUME}:/var/lib/postgresql/data" \
    postgres:15-alpine > /dev/null
fi

echo "==> Starting Redis ($REDIS_CONTAINER, port $REDIS_PORT)"
if docker ps -a --format '{{.Names}}' | grep -qx "$REDIS_CONTAINER"; then
  docker start "$REDIS_CONTAINER" > /dev/null
else
  docker run -d --name "$REDIS_CONTAINER" -p "${REDIS_PORT}:6379" redis:7-alpine > /dev/null
fi

echo "==> Waiting for Postgres..."
until docker exec "$PG_CONTAINER" pg_isready -U wardrobe > /dev/null 2>&1; do
  sleep 1
done

BACKEND_ENV="$ROOT_DIR/backend/.env"
if [ ! -f "$BACKEND_ENV" ]; then
  echo "==> Writing $BACKEND_ENV (first run only - it's gitignored, edit freely after this)"
  cat > "$BACKEND_ENV" << EOF
DATABASE_URL=postgresql+asyncpg://wardrobe:wardrobe@localhost:${DB_PORT}/wardrobe
REDIS_URL=redis://localhost:${REDIS_PORT}/0
SECRET_KEY=dev-local-not-secret
DEBUG=true
STORAGE_PATH=${STORAGE_DIR}

# AI is off by default so this loop stays instant and free. To test tagging
# or suggestions, set this to true and fill in the same options documented
# in .env.example (Ollama, OpenAI, etc.):
AI_INTERNAL_ENABLED=false
# AI_BASE_URL=https://api.openai.com/v1
# AI_API_KEY=sk-...
# AI_VISION_MODEL=gpt-5.6-terra
# AI_TEXT_MODEL=gpt-5.6-luna
EOF
else
  echo "==> Reusing existing $BACKEND_ENV (delete it to regenerate defaults)"
fi

cd "$ROOT_DIR/backend"
if ! command -v uv > /dev/null 2>&1; then
  echo "This repo's backend is managed with uv (see backend/uv.lock)." >&2
  echo "Install it first: https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
fi

if [ ! -d .venv ]; then
  echo "==> Creating backend/.venv (uv)"
  uv venv --python 3.11 .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Installing backend deps (uv, cached after the first run)"
uv pip install --python .venv/bin/python -q -r requirements.txt
if [ "$WITH_EXTRAS" = 1 ]; then
  echo "==> Installing requirements-extras.txt (rembg)"
  uv pip install --python .venv/bin/python -q -r requirements-extras.txt
fi

echo "==> Running migrations"
alembic upgrade head

PIDS=()
cleanup() {
  echo ""
  echo "==> Stopping backend/frontend/worker ($PG_CONTAINER/$REDIS_CONTAINER stay up - scripts/dev-local-down.sh to stop them)"
  for pid in "${PIDS[@]:-}"; do
    kill "$pid" 2> /dev/null || true
  done
}
trap cleanup EXIT INT TERM

echo "==> Starting backend on http://127.0.0.1:8000 (--reload)"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 > "$LOG_DIR/backend.log" 2>&1 &
PIDS+=("$!")

if [ "$WITH_WORKER" = 1 ]; then
  echo "==> Starting arq worker (hot reload via watchfiles)"
  watchfiles --filter python "arq app.workers.worker.WorkerSettings" . > "$LOG_DIR/worker.log" 2>&1 &
  PIDS+=("$!")
fi

cd "$ROOT_DIR/frontend"
if [ ! -d node_modules ]; then
  echo "==> Installing frontend deps (first run only)"
  npm install
fi

echo "==> Starting frontend on http://localhost:3000"
BACKEND_URL=http://127.0.0.1:8000 \
  NEXTAUTH_URL=http://localhost:3000 \
  NEXTAUTH_SECRET=dev-local-not-secret \
  DEV_MODE=true \
  PERSONAL_ACCOUNT_EMAIL=dev@wardrobe.local \
  PERSONAL_ACCOUNT_NAME="Dev" \
  npm run dev > "$LOG_DIR/frontend.log" 2>&1 &
PIDS+=("$!")

cat << EOF

Ready:
  App:      http://localhost:3000
  API docs: http://127.0.0.1:8000/docs
  Logs:     tail -f $LOG_DIR/*.log

Ctrl+C to stop backend/frontend/worker.
EOF

wait
