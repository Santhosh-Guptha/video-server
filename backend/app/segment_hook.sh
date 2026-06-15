#!/bin/sh
# Wrapper script for MediaMTX segment complete hook to avoid quoting/escaping issues
cd /opt/video-server/backend
/opt/video-backend-venv/bin/python3 -m app.record_complete "${MTX_PATH:-$RTSP_PATH}" "${MTX_SEGMENT_PATH:-$RECORD_PATH}" >> /opt/video-server/backend/data/hook.log 2>&1
