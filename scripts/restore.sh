#!/usr/bin/env bash
# Restore a backup made by scripts/backup.sh into a running docker compose stack.
# THIS REPLACES the current database and files.
#
#   scripts/restore.sh backups/investpad-<timestamp>.dump backups/investpad-<timestamp>-files.tgz
set -euo pipefail
dump="$1"; files="$2"
[ -f "$dump" ] && [ -f "$files" ] || { echo "usage: $0 <dump> <files.tgz>"; exit 1; }
read -r -p "This replaces the current Invest-pad data. Type 'restore' to continue: " ok
[ "$ok" = "restore" ] || { echo "Stopped."; exit 1; }
docker compose stop api web
docker compose exec -T db pg_restore -U investpad_owner -d investpad --clean --if-exists --no-owner \
  --role=investpad_owner < "$dump"
docker compose run --rm -T --entrypoint sh api -c 'rm -rf /data/files && tar -C /data -xzf -' < "$files"
docker compose start api web
echo "Restored. Sign in and check a company you know."
