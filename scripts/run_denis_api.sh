#!/bin/bash
# Run Denis API server with middleware endpoints
# Usage: ./run_denis_api.sh [port]

PORT=${1:-19000}
cd /media/jotah/SSD_denis/home_jotah/denis_unified_v1

export PYTHONPATH="${PYTHONPATH}:$(pwd)"
export OPENCODE_DENIS_TIMEOUT_MS=800

echo "Starting Denis API on port $PORT..."
python3 -m uvicorn api.fastapi_server:create_app --factory --host 127.0.0.1 --port $PORT --log-level info
