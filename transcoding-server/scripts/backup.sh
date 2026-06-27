#!/usr/bin/env bash
# ── CONFIGURATION & LOG BACKUP SCRIPT ──────────────────────────────────────
# Packages and compresses current configs and systemd scripts for rollback.

set -e

BACKUP_DIR=${1:-"./backups"}
mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
ARCHIVE="$BACKUP_DIR/vms_transcoder_backup_$TIMESTAMP.tar.gz"

echo "=== Packaging Current Configurations ==="
tar -czf "$ARCHIVE" \
    --exclude="venv" \
    --exclude="backups" \
    ../transcoding-server \
    /etc/systemd/system/vms-transcoder.service 2>/dev/null || true

echo "=========================================================="
echo "Backup successfully created: $ARCHIVE"
echo "=========================================================="
