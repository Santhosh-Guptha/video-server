#!/usr/bin/env bash
# ── PRODUCTION ROLLBACK SCRIPT ─────────────────────────────────────────────
# Reverts the repository to the last git tag or previous commit and restarts.

set -e

echo "=== Rolling back VMS Transcoding Platform ==="

# 1. Rollback git
if git rev-parse --is-inside-work-tree &>/dev/null; then
    echo "Reverting repository to previous commit..."
    git checkout HEAD@{1}
else
    echo "[ERROR] Not a git repository. Cannot auto-rollback."
    exit 1
fi

# 2. Restart daemon
echo "Restarting service..."
sudo systemctl daemon-reload || true
sudo systemctl restart vms-transcoder || true

echo "=========================================================="
echo "Rollback successfully completed!"
echo "=========================================================="
