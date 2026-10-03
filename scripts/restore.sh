#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SOURCE=${1:-}
PRIVATE_SOURCE=${SOURCE%.sql.gz}-private-data.tar.gz
MANIFEST=${SOURCE%.sql.gz}.sha256

if [ -z "$SOURCE" ] || [ ! -f "$SOURCE" ]; then
  echo "Usage: ALLOW_DATABASE_REPLACE=yes scripts/restore.sh /absolute/backup.sql.gz" >&2
  exit 2
fi
if [ "${ALLOW_DATABASE_REPLACE:-no}" != "yes" ]; then
  echo "Restore refused: set ALLOW_DATABASE_REPLACE=yes after taking a current backup." >&2
  exit 3
fi

cd "$PROJECT_DIR"
if docker compose version >/dev/null 2>&1; then
  compose() { docker compose "$@"; }
elif command -v docker-compose >/dev/null 2>&1; then
  compose() { docker-compose "$@"; }
else
  echo "Docker Compose is required." >&2
  exit 1
fi
set -a
. ./.env
set +a
gzip -t "$SOURCE"
[ -f "$PRIVATE_SOURCE" ] || { echo "Missing paired private-file backup: $PRIVATE_SOURCE" >&2; exit 4; }
[ -f "$MANIFEST" ] || { echo "Missing checksum manifest: $MANIFEST" >&2; exit 4; }
gzip -t "$PRIVATE_SOURCE"
tar -tzf "$PRIVATE_SOURCE" >/dev/null
(cd "$(dirname "$SOURCE")" && sha256sum -c "$(basename "$MANIFEST")")
compose stop app
compose exec -T db psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set ON_ERROR_STOP=1 --command "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
gzip -dc "$SOURCE" | compose exec -T db psql \
  --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set ON_ERROR_STOP=1
compose run --rm --no-deps --user 0:0 --entrypoint sh -T app \
  -c 'find /app/private-data -mindepth 1 -delete; tar -xzf - -C /app/private-data; chown -R 10001:10001 /app/private-data' \
  < "$PRIVATE_SOURCE"
compose start app
attempt=0
state=unknown
while [ "$attempt" -lt 30 ]; do
  app_id=$(compose ps -q app)
  [ -n "$app_id" ] || { echo "Restore failed: app container is missing" >&2; exit 4; }
  state=$(docker inspect "$app_id" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}')
  [ "$state" = "healthy" ] && break
  attempt=$((attempt + 1))
  sleep 2
done
[ "$state" = "healthy" ] || { echo "Restore failed: app did not become healthy" >&2; exit 4; }
curl --fail --silent --show-error --max-time 5 "http://127.0.0.1:${TTC_HTTP_PORT:-18574}/healthz/" >/dev/null
echo "Restore completed from: $SOURCE"
