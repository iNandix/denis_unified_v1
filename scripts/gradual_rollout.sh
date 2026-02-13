#!/bin/bash
# Gradual rollout 8084 → 8085

set -e

NGINX_CONF="/etc/nginx/sites-available/denis-loadbalancer"

rollout_percentage() {
    local pct=$1
    local weight_8085=$pct
    local weight_8084=$((100 - pct))
    
    echo "🔄 Rollout: ${pct}% → 8085, $((100-pct))% → 8084"
    
    sudo sed -i "s/server 127.0.0.1:8085 weight=.*;/server 127.0.0.1:8085 weight=${weight_8085};/" $NGINX_CONF
    sudo sed -i "s/server 127.0.0.1:8084 weight=.*;/server 127.0.0.1:8084 weight=${weight_8084};/" $NGINX_CONF
    
    sudo nginx -t && sudo systemctl reload nginx
    
    echo "✅ Rollout ${pct}% completado"
}

check_health() {
    echo "🔍 Chequeando health de 8085..."
    
    # Métricas últimos 5 min
    local error_rate=$(curl -s http://localhost:8085/metacognitive/alerts | jq -r '.status')
    
    if [ "$error_rate" == "anomalies_detected" ]; then
        echo "❌ Anomalías detectadas en 8085"
        return 1
    fi
    
    echo "✅ 8085 healthy"
    return 0
}

# Rollout gradual
echo "=== INICIANDO ROLLOUT GRADUAL ==="

rollout_percentage 10
sleep 300  # 5 min

if check_health; then
    rollout_percentage 25
    sleep 600  # 10 min
else
    echo "❌ Rollback a 8084"
    rollout_percentage 0
    exit 1
fi

if check_health; then
    rollout_percentage 50
    sleep 900  # 15 min
else
    echo "❌ Rollback a 25%"
    rollout_percentage 25
    exit 1
fi

if check_health; then
    rollout_percentage 100
    echo "✅ ROLLOUT COMPLETO: 100% tráfico en 8085"
else
    echo "❌ Rollback a 50%"
    rollout_percentage 50
    exit 1
fi
