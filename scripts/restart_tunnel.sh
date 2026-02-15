#!/bin/bash
# Restart tunnel periodically (URLs change)

pkill -f "localtunnel" 2>/dev/null
sleep 1

cd /media/jotah/SSD_denis/home_jotah/denis_unified_v1
nohup npx --yes localtunnel --port 8899 > /tmp/tunnel.log 2>&1 &
sleep 5

TUNNEL_URL=$(grep -o "https://[^ ]*" /tmp/tunnel.log | head -1)
echo "[$(date)] 🚀 Tunnel: $TUNNEL_URL"
echo "$TUNNEL_URL" > /tmp/dashboard_url.txt
