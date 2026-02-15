#!/bin/bash
# Sync Denis repo from GitHub with auto-restart

REPO_DIR="/media/jotah/SSD_denis/home_jotah/denis_unified_v1"
SERVER_PORT=8090

cd "$REPO_DIR" || exit 1

# Fetch and check if there are changes
git fetch origin main

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" != "$REMOTE" ]; then
    echo "[$(date)] Changes detected: local=$LOCAL remote=$REMOTE"
    git pull origin main
    echo "[$(date)] Pull completed - restarting server..."
    
    # Restart server
    pkill -f "port $SERVER_PORT" 2>/dev/null
    sleep 1
    cd "$REPO_DIR"
    DENIS_CONTRACT_TEST_MODE=1 nohup python3 -m uvicorn api.fastapi_server:create_app --factory --host 0.0.0.0 --port $SERVER_PORT --log-level error >> /tmp/server.log 2>&1 &
    echo "[$(date)] Server restarted on port $SERVER_PORT"
else
    echo "[$(date)] Already up to date"
fi
