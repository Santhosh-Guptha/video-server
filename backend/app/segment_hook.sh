#!/bin/bash
# MediaMTX runOnRecordSegmentComplete hook script

# Determine the backend directory dynamically relative to this script's location
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
BACKEND_DIR="$(cd -- "$SCRIPT_DIR/.." &> /dev/null && pwd)"

LOG_FILE="$BACKEND_DIR/data/record_complete.log"

echo "[segment_hook] Started: stream_id='$1', file_path='$2' at $(date)" >> "$LOG_FILE" 2>&1
cd "$BACKEND_DIR"
/opt/video-backend-venv/bin/python3 -m app.record_complete "$1" "$2" >> "$LOG_FILE" 2>&1
echo "[segment_hook] Finished: status=$? at $(date)" >> "$LOG_FILE" 2>&1
