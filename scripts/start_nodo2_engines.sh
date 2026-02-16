#!/bin/bash
# Script para iniciar llama-servers en nodo2 (1050 Ti 4GB)
# 3x light engines: intent, safety, draft

set -e

MODEL_INTENT="/home/jotah/models/Gemma-3-Prompt-Coder-270m-it-Uncensored.Q4_K_M.gguf"
MODEL_SAFETY="/home/jotah/models/Llama-3.2-1B-Instruct-Uncensored.Q4_K_M.gguf"
MODEL_DRAFT="/home/jotah/models/Llama-3.2-1B-Instruct-Uncensored-port8006.Q4_K_M.gguf"

echo "=== Starting llama-servers on nodo2 (1050 Ti) ==="

# Engine 1: intent/router
echo "Starting llama-server on port 8081 (intent)..."
nohup llama-server \
    --model "$MODEL_INTENT" \
    --port 8081 \
    --ctx-size 2048 \
    --threads 4 \
    --gpu-layers 24 \
    --parallel 8 \
    > /tmp/llama-8081.log 2>&1 &

# Engine 2: safety/policy
echo "Starting llama-server on port 8082 (safety)..."
nohup llama-server \
    --model "$MODEL_SAFETY" \
    --port 8082 \
    --ctx-size 2048 \
    --threads 4 \
    --gpu-layers 24 \
    --parallel 8 \
    > /tmp/llama-8082.log 2>&1 &

# Engine 3: draft/speculative
echo "Starting llama-server on port 8083 (draft)..."
nohup llama-server \
    --model "$MODEL_DRAFT" \
    --port 8083 \
    --ctx-size 2048 \
    --threads 4 \
    --gpu-layers 24 \
    --parallel 8 \
    > /tmp/llama-8083.log 2>&1 &

echo "=== Servers started ==="
echo "Check health: curl http://10.10.10.2:8081/health"
