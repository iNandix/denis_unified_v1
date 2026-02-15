#!/bin/bash
# Denis Sync Dashboard + Tunnel Startup

REPO_DIR="/media/jotah/SSD_denis/home_jotah/denis_unified_v1"
DASHBOARD_PORT=8899
SERVER_PORT=8090

cd "$REPO_DIR"

# Kill existing processes
pkill -f "sync_dashboard.py" 2>/dev/null
pkill -f "localtunnel" 2>/dev/null
pkill -f "port $SERVER_PORT" 2>/dev/null

sleep 1

# Start dashboard
echo "[$(date)] Starting dashboard..."
nohup python3 scripts/sync_dashboard.py > /tmp/dashboard.log 2>&1 &
sleep 2

# Start server
echo "[$(date)] Starting unified server..."
DENIS_CONTRACT_TEST_MODE=1 nohup python3 -m uvicorn api.fastapi_server:create_app --factory --host 0.0.0.0 --port $SERVER_PORT --log-level error >> /tmp/server.log 2>&1 &

sleep 2

# Start localtunnel
echo "[$(date)] Starting tunnel..."
nohup npx --yes localtunnel --port $DASHBOARD_PORT > /tmp/tunnel.log 2>&1 &
sleep 5

# Get URL
TUNNEL_URL=$(grep -o "https://[^ ]*" /tmp/tunnel.log | head -1)
echo "[$(date)] 🚀 Dashboard: $TUNNEL_URL"
echo "$TUNNEL_URL" > /tmp/dashboard_url.txt
