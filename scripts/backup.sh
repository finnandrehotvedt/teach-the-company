#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
BACKUP_DIR="$PROJECT_DIR/backups"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
TARGET="$BACKUP_DIR/teach-the-company-$STAMP.sql.gz"
PRIVATE_TARGET="$BACKUP_DIR/teach-the-company-$STAMP-private-data.tar.gz"
MANIFEST="$BACKUP_DIR/teach-the-company-$STAMP.sha256"

cd "$PROJECT_DIR"
test -f .env || { echo "Missing .env; run scripts/init_env.py first" >&2; exit 1; }
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
mkdir -p "$BACKUP_DIR"
chmod 0700 "$BACKUP_DIR"
umask 077
RAW_TARGET=$(mktemp "$BACKUP_DIR/.teach-the-company-$STAMP.XXXXXX.sql")
cleanup_raw() {
  rm -f -- "$RAW_TARGET"
}
trap cleanup_raw EXIT

compose exec -T db pg_dump \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --no-owner --no-privileges > "$RAW_TARGET"
[ -s "$RAW_TARGET" ] || { echo "Database dump is empty" >&2; exit 1; }
gzip -9 -c "$RAW_TARGET" > "$TARGET"
chmod 0600 "$TARGET"
gzip -t "$TARGET"
compose exec -T app tar -C /app/private-data -czf - . > "$PRIVATE_TARGET"
chmod 0600 "$PRIVATE_TARGET"
gzip -t "$PRIVATE_TARGET"
tar -tzf "$PRIVATE_TARGET" >/dev/null
(cd "$BACKUP_DIR" && sha256sum "$(basename "$TARGET")" "$(basename "$PRIVATE_TARGET")" > "$(basename "$MANIFEST")")
chmod 0600 "$MANIFEST"
cleanup_raw
trap - EXIT
echo "Backup verified: $TARGET"
echo "Private files verified: $PRIVATE_TARGET"
echo "Checksums: $MANIFEST"
