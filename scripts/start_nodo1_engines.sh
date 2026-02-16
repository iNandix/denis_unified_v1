#!/bin/bash
# Script para iniciar llama-servers en nodo1 (PC con RTX 3080)
# 2x response engines

set -e

LLAMA_SERVER="$HOME/.local/bin/llama-server"

MODEL_RESPONSE_A="/media/jotah/SSD_denis/models/qwen2.5-3b-instruct-q6_k.gguf"
MODEL_RESPONSE_B="/media/jotah/SSD_denis/models/mistral-7b-instruct-v0.3-q3_k_m.gguf"

echo "=== Starting llama-servers on nodo1 (RTX 3080) ==="

# Engine A: response
echo "Starting llama-server on port 9001..."
nohup $LLAMA_SERVER \
    --model "$MODEL_RESPONSE_A" \
    --port 9001 \
    --ctx-size 4096 \
    --threads 8 \
    --gpu-layers 32 \
    --parallel 4 \
    > /tmp/llama-9001.log 2>&1 &

echo "PID: $!"

# Engine B: response
echo "Starting llama-server on port 9002..."
nohup $LLAMA_SERVER \
    --model "$MODEL_RESPONSE_B" \
    --port 9002 \
    --ctx-size 4096 \
    --threads 8 \
    --gpu-layers 32 \
    --parallel 4 \
    > /tmp/llama-9002.log 2>&1 &

echo "PID: $!"

echo "=== Servers started ==="
echo "Check health: curl http://127.0.0.1:9001/health"
