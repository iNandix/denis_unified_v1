#!/bin/bash
# Start llama.cpp inference engines for DENIS (CPU fallback)

LLAMA_SERVER="/media/jotah/SSD_denis/core/inference/llama.cpp/build/bin/llama-server"
MODEL_DIR="/media/jotah/SSD_denis/models"
NGL=0  # CPU only - no GPU layers

start_engine() {
    local port=$1
    local model=$2
    local name=$3
    local extra=$4
    
    if [ ! -f "$MODEL_DIR/$model" ]; then
        echo "❌ Model $model not found"
        return 1
    fi
    
    # Kill existing on port
    fuser -k $port/tcp 2>/dev/null
    sleep 1
    
    echo "🚀 Starting $name on port $port (CPU)..."
    nohup $LLAMA_SERVER \
        -m "$MODEL_DIR/$model" \
        --host 127.0.0.1 \
        --port $port \
        -ngl $NGL \
        -c 2048 \
        --parallel 2 \
        --threads 6 \
        --mlock \
        $extra \
        > /tmp/llama-$port.log 2>&1 &
    
    sleep 3
    
    if curl -sf "http://127.0.0.1:$port/v1/models" >/dev/null 2>&1; then
        echo "✅ $name running on port $port"
    else
        echo "❌ $name failed (check /tmp/llama-$port.log)"
        tail -3 /tmp/llama-$port.log 2>/dev/null
    fi
}

echo "=== DENIS llama.cpp Engines (CPU) ==="

# 8081: Main model (qwen2.5-3b)
start_engine 8081 "qwen2.5-3b-instruct-q6_k.gguf" "qwen2.5-3b" "-b 512"

# 8082: Coder - usar modelo más pequeño
start_engine 8082 "qwen2.5-1.5b-instruct-q8_0.gguf" "qwen1.5b" "-b 256"

# 8083: phi-2 (small)
start_engine 8083 "phi-2.Q4_K_M.gguf" "phi-2" "-b 256"

# 8084: Already running (skip)

# 8085: mistral (small)
start_engine 8085 "mistral-7b-instruct-v0.3-q3_k_m.gguf" "mistral" "-b 512"

# 8086: Already running (skip)

echo ""
echo "=== Health Check ==="
for port in 8081 8082 8083 8084 8085 8086; do
    if curl -sf "http://127.0.0.1:$port/v1/models" >/dev/null 2>&1; then
        echo "✅ $port OK"
    else
        echo "❌ $port FAIL"
    fi
done
