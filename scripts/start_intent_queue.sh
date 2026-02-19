#!/usr/bin/env bash
set -e
cd /media/jotah/SSD_denis/home_jotah/denis_unified_v1
source .env.prod 2>/dev/null || true
echo "Starting Denis Intent Queue on port 8765..."
exec uvicorn control_plane.intent_queue_app:app \
  --host 0.0.0.0 \
  --port 8765 \
  --log-level info \
  --reload
