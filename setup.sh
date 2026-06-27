#!/usr/bin/env bash
# ── MAIN SETUP SCRIPT FOR TRANSCODING SERVER ────────────────────────────────
# Configures permissions, runs automated installation, and performs diagnostic check.

set -e

# Change directory to the setup script location
cd "$(dirname "$0")"

echo "=========================================================="
echo "    STARTING VMS TRANSCODING SERVER SETUP"
echo "=========================================================="

# Make all child scripts executable
chmod +x transcoding-server/scripts/*.sh

# Enter the transcoding-server directory to execute install and diagnostics
cd transcoding-server
./scripts/install.sh
./scripts/diagnostics.sh

echo "=========================================================="
echo "    SETUP COMPLETED SUCCESSFULLY"
echo "=========================================================="
