#!/usr/bin/env bash
# Copy the raw AIS layer and ops logs from the collector server to this machine.
# Read-only on the server: pulls closed part files only (skips *.inprogress) and
# verifies each new part against its sha256 sidecar. Never deletes anything locally.
#
# Usage: scripts/sync_data.sh [ssh_host]   (default host alias: mlops-tcc)
set -euo pipefail

HOST="${1:-mlops-tcc}"
REMOTE_DIR="mlops-tcc/data/"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)/data/"

mkdir -p "$LOCAL_DIR"
rsync -a --itemize-changes \
  --exclude '*.inprogress' \
  --exclude 'heartbeat' \
  "$HOST:$REMOTE_DIR" "$LOCAL_DIR"

# Verify checksums of every closed part (cheap: a few MB per day).
cd "$LOCAL_DIR"
bad=0
while IFS= read -r -d '' sidecar; do
  (cd "$(dirname "$sidecar")" && sha256sum --quiet -c "$(basename "$sidecar")") || bad=$((bad + 1))
done < <(find raw -name '*.sha256' -print0)

parts=$(find raw -name '*.jsonl.gz' | wc -l)
echo "sync ok: $parts part files, $bad checksum failures, $(du -sh raw | cut -f1) raw"
[ "$bad" -eq 0 ]
