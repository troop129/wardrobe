#!/usr/bin/env bash
# Stops (and optionally removes) the Postgres/Redis containers started by
# scripts/dev-local.sh. These are plain `docker run` containers with
# dedicated names (wardrobe-devlocal-postgres/-redis) - deliberately not
# docker-compose.yml, which pins container_names that would collide with any
# regular stack you already have running locally.
#
# Usage:
#   scripts/dev-local-down.sh        # stop, keep data for next time
#   scripts/dev-local-down.sh -v     # stop, remove containers + wipe data volume

set -euo pipefail

PG_CONTAINER=wardrobe-devlocal-postgres
REDIS_CONTAINER=wardrobe-devlocal-redis
PG_VOLUME=wardrobe-devlocal-pgdata

docker stop "$PG_CONTAINER" "$REDIS_CONTAINER" > /dev/null 2>&1 || true

if [ "${1:-}" = "-v" ]; then
  docker rm -f "$PG_CONTAINER" "$REDIS_CONTAINER" > /dev/null 2>&1 || true
  docker volume rm "$PG_VOLUME" > /dev/null 2>&1 || true
  echo "Stopped and removed $PG_CONTAINER/$REDIS_CONTAINER, wiped $PG_VOLUME. Next dev-local.sh run starts fresh."
else
  echo "Stopped $PG_CONTAINER/$REDIS_CONTAINER (data volume kept). Pass -v to also remove them and wipe data."
fi
