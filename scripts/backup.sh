#!/usr/bin/env bash
# Back up an Invest-pad install run with docker compose: the database and the uploaded files.
#
#   scripts/backup.sh [output-dir]        (default ./backups)
#
# Writes investpad-<timestamp>.dump (pg_dump custom format) and investpad-<timestamp>-files.tgz.
# Run from the repo folder, with the stack up. Keep backups somewhere other than this machine.
# The files include .secret_key, which decrypts stored model keys: treat the backup as secret.
set -euo pipefail
out="${1:-backups}"
stamp="$(date -u +%Y%m%d-%H%M%S)"
mkdir -p "$out"
docker compose exec -T db pg_dump -U investpad_owner -d investpad -Fc > "$out/investpad-$stamp.dump"
docker compose exec -T api tar -C /data -czf - files > "$out/investpad-$stamp-files.tgz"
echo "Backed up to $out/investpad-$stamp.dump and $out/investpad-$stamp-files.tgz"
