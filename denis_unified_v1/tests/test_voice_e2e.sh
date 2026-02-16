#!/usr/bin/env bash
# =============================================================================
# RUNBOOK: Denis Voice Pipeline E2E Tests
# =============================================================================
# Prerequisites:
#   - nodo2 Piper TTS running on 10.10.10.2:8005
#   - nodo1 Persona running on 10.10.10.1:8084 (or localhost:8084)
#   - Neo4j on bolt://localhost:7687
#   - Redis on localhost:6379
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PIPER_URL="${PIPER_BASE_URL:-http://10.10.10.2:8005}"
PERSONA_URL="${SERVICE_PUBLIC_BASE_URL:-http://localhost:8084}"
NEO4J_PASS="${NEO4J_PASSWORD:-Leon1234\$}"

pass=0
fail=0

check() {
    local desc="$1"
    local result="$2"
    if [ "$result" = "ok" ]; then
        echo -e "${GREEN}[PASS]${NC} $desc"
        ((pass++))
    else
        echo -e "${RED}[FAIL]${NC} $desc — $result"
        ((fail++))
    fi
}

echo "============================================="
echo " Denis Voice Pipeline E2E Tests"
echo "============================================="
echo ""

# -----------------------------------------------
# T1: Nodo2 Piper health
# -----------------------------------------------
echo "--- T1: Nodo2 Piper Health ---"
health=$(curl -sf "$PIPER_URL/health" 2>/dev/null || echo '{}')
status=$(echo "$health" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")
check "Piper health endpoint" "$([ "$status" = "healthy" ] && echo ok || echo "status=$status")"

# -----------------------------------------------
# T2: Nodo2 streaming synthesis (PCM bytes > 0)
# -----------------------------------------------
echo ""
echo "--- T2: Streaming Synthesis ---"
bytes=$(curl -sf -X POST "$PIPER_URL/synthesize_stream" \
    -H 'Content-Type: application/json' \
    -d '{"text":"Hola, esto es una prueba de streaming.","request_id":"test_e2e_1"}' \
    --max-time 15 2>/dev/null | wc -c)
check "Streaming returns bytes" "$([ "$bytes" -gt 1000 ] && echo ok || echo "bytes=$bytes")"

# -----------------------------------------------
# T3: Nodo2 stats show completed stream
# -----------------------------------------------
echo ""
echo "--- T3: Stats ---"
stats=$(curl -sf "$PIPER_URL/stats" 2>/dev/null || echo '{}')
active=$(echo "$stats" | python3 -c "import sys,json; print(json.load(sys.stdin).get('active_streams_count', -1))" 2>/dev/null || echo "-1")
check "Stats endpoint works" "$([ "$active" -ge 0 ] && echo ok || echo "active=$active")"

# -----------------------------------------------
# T4: Nodo2 cancel
# -----------------------------------------------
echo ""
echo "--- T4: Cancel ---"
# Start a long stream in background
curl -sf -X POST "$PIPER_URL/synthesize_stream" \
    -H 'Content-Type: application/json' \
    -d '{"text":"Esta es una frase muy larga que debería tardar bastante en sintetizarse porque tiene muchas palabras y queremos probar la cancelación del stream activo.","request_id":"test_cancel_1"}' \
    --max-time 30 > /dev/null 2>&1 &
STREAM_PID=$!
sleep 1

cancel_result=$(curl -sf -X POST "$PIPER_URL/cancel" \
    -H 'Content-Type: application/json' \
    -d '{"request_id":"test_cancel_1"}' 2>/dev/null || echo '{}')
was_active=$(echo "$cancel_result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('was_active', False))" 2>/dev/null || echo "False")
check "Cancel returns was_active=true" "$([ "$was_active" = "True" ] && echo ok || echo "was_active=$was_active")"

kill $STREAM_PID 2>/dev/null || true
wait $STREAM_PID 2>/dev/null || true

# -----------------------------------------------
# T5: Nodo1 Persona meta
# -----------------------------------------------
echo ""
echo "--- T5: Persona Meta ---"
meta=$(curl -sf "$PERSONA_URL/meta" 2>/dev/null || echo '{}')
persona_status=$(echo "$meta" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")
check "Persona /meta responds" "$([ "$persona_status" = "ok" ] && echo ok || echo "status=$persona_status")"

# -----------------------------------------------
# T6: WS /chat with voice_enabled (requires websocat or wscat)
# -----------------------------------------------
echo ""
echo "--- T6: WS /chat E2E ---"
if command -v websocat &>/dev/null; then
    ws_result=$(echo '{"message":"Hola","voice_enabled":true,"request_id":"ws_test_1"}' | \
        timeout 15 websocat -t "ws://localhost:8084/chat" 2>/dev/null || echo "[]")

    has_text=$(echo "$ws_result" | grep -c "render.text" || echo "0")
    has_outcome=$(echo "$ws_result" | grep -c "render.outcome" || echo "0")
    check "WS returns render.text events" "$([ "$has_text" -gt 0 ] && echo ok || echo "count=$has_text")"
    check "WS returns render.outcome" "$([ "$has_outcome" -gt 0 ] && echo ok || echo "count=$has_outcome")"
else
    echo -e "${YELLOW}[SKIP]${NC} websocat not installed (apt install websocat or cargo install websocat)"
    echo "  Manual test: echo '{\"message\":\"Hola\",\"voice_enabled\":true}' | websocat ws://localhost:8084/chat"
fi

# -----------------------------------------------
# T7: Neo4j graph projection
# -----------------------------------------------
echo ""
echo "--- T7: Graph Projection ---"
graph_check=$(cypher-shell -u neo4j -p "$NEO4J_PASS" \
    "MATCH (p:PipelineNode {name:'Persona'})-[:DELIVERS_VIA]->(d:PipelineNode {name:'DeliverySubgraph'}) RETURN count(p) AS c" 2>/dev/null | tail -1 || echo "0")
check "Pipeline topology in graph" "$([ "$graph_check" -gt 0 ] && echo ok || echo "count=$graph_check")"

# -----------------------------------------------
# T8: Redis health
# -----------------------------------------------
echo ""
echo "--- T8: Redis ---"
redis_ping=$(redis-cli ping 2>/dev/null || echo "NOPE")
check "Redis responds" "$([ "$redis_ping" = "PONG" ] && echo ok || echo "$redis_ping")"

# -----------------------------------------------
# T9: ffplay test (manual)
# -----------------------------------------------
echo ""
echo "--- T9: ffplay (manual) ---"
echo -e "${YELLOW}[MANUAL]${NC} Test audio playback with ffplay:"
echo "  curl -N -X POST $PIPER_URL/synthesize_stream \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"text\":\"Hola, soy Denis.\"}' | \\"
echo "    ffplay -f s16le -ar 22050 -ac 1 -nodisp -autoexit -"
echo ""

# -----------------------------------------------
# T10: HASS test (manual)
# -----------------------------------------------
echo ""
echo "--- T10: HASS (manual) ---"
echo -e "${YELLOW}[MANUAL]${NC} Test Home Assistant playback:"
echo '  curl -X POST http://localhost:8123/api/services/media_player/play_media \'
echo '    -H "Authorization: Bearer $HA_TOKEN" \'
echo '    -H "Content-Type: application/json" \'
echo '    -d "{\"entity_id\":\"media_player.salon\",\"media_content_id\":\"http://10.10.10.1:8084/render/voice/segment?request_id=test\",\"media_content_type\":\"music\"}"'
echo ""

# -----------------------------------------------
# Summary
# -----------------------------------------------
echo "============================================="
echo " Results: ${GREEN}$pass passed${NC}, ${RED}$fail failed${NC}"
echo "============================================="

# -----------------------------------------------
# Definition of Done Checklist
# -----------------------------------------------
echo ""
echo "=== DEFINITION OF DONE CHECKLIST ==="
echo ""
echo "Render Contract:"
echo "  [ ] Envelope: {type, request_id, sequence, payload, ts}"
echo "  [ ] render.text.delta, render.text.final, render.voice.delta"
echo "  [ ] render.voice.cancelled, render.outcome"
echo ""
echo "Voice:"
echo "  [ ] render.voice.delta has encoding=pcm_s16le, sample_rate, channels, pts_ms, audio_b64"
echo "  [ ] TTFC measured and in render.outcome (voice_ttfc_ms > 0)"
echo "  [ ] Barge-in: client.interrupt -> voice.cancelled (no duplicate outcome)"
echo ""
echo "Graph:"
echo "  [ ] Persona -> DeliverySubgraph -> PipecatRenderer -> PiperTTS in Neo4j"
echo "  [ ] VoiceRequest and VoiceOutcome nodes created per request"
echo "  [ ] Outcome has voice_ttfc_ms, bytes_streamed, cancelled"
echo ""
echo "HASS:"
echo "  [ ] Bridge optional via DENIS_HASS_ENABLED=1"
echo "  [ ] PCM->WAV segmented playback"
echo "  [ ] Cancel stops HA playback"
echo ""
echo "Telemetry:"
echo "  [ ] execution_outcome always written"
echo "  [ ] Idempotency by request_id (no duplicates)"
echo ""

exit $fail
