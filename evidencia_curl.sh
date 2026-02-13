#!/bin/bash
# EVIDENCIA CURL - DENIS Unified v1
# Fecha: 2026-02-13

echo "=========================================="
echo "EVIDENCIA CURL - DENIS Unified v1"
echo "Fecha: $(date)"
echo "=========================================="
echo ""

echo "1. Health Check del Servidor"
echo "---"
curl -s http://localhost:8085/health | jq '{status, version, timestamp_utc}'
echo ""

echo "2. API Metacognitiva - /status"
echo "---"
curl -s http://localhost:8085/metacognitive/status | jq '{status, layers, coherence_score: .coherence.coherence_score}'
echo ""

echo "3. API Metacognitiva - /metrics"
echo "---"
curl -s http://localhost:8085/metacognitive/metrics | jq '{operations_count: (.operations | length), timestamp}'
echo ""

echo "4. API Metacognitiva - /attention"
echo "---"
curl -s http://localhost:8085/metacognitive/attention | jq '{attention_mode, focused_patterns_count: (.focused_patterns | length)}'
echo ""

echo "5. API Metacognitiva - /coherence"
echo "---"
curl -s http://localhost:8085/metacognitive/coherence | jq '{coherence_score, complete_paths, orphan_patterns, status}'
echo ""

echo "6. Autopoiesis - /status"
echo "---"
curl -s http://localhost:8085/autopoiesis/status | jq '{cycle_status: .cycle.status, gaps_detected: .cycle.gaps_detected, proposals_generated: .cycle.proposals_generated}'
echo ""

echo "7. Autopoiesis - /proposals"
echo "---"
curl -s http://localhost:8085/autopoiesis/proposals | jq '{proposals_count: (.proposals | length)}'
echo ""

echo "8. Dashboard HTML (verificar acceso)"
echo "---"
curl -s -o /dev/null -w "HTTP Status: %{http_code}\n" http://localhost:8085/static/dashboard.html
curl -s http://localhost:8085/static/dashboard.html | grep -o '<title>.*</title>'
echo ""

echo "=========================================="
echo "✅ EVIDENCIA COMPLETA GENERADA"
echo "=========================================="
