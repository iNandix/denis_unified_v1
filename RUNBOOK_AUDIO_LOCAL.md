# RUNBOOK: Denis Audio Local (PC con Altavoces)

## Quick Start

```bash
# 1. Instalar dependencia
pip install websockets

# 2. Reproducir audio (en terminal)
cd /media/jotah/SSD_denis/home_jotah/denis_unified_v1
DENIS_WS="ws://10.10.10.1:8084/chat" python3 play_denis_ws.py | ffplay -nodisp -autoexit -f s16le -ar 22050 -ac 1 -i -
```

## Health Checks

```bash
# Nodo1 (Denis Persona)
curl -sf http://10.10.10.1:8084/meta

# Nodo2 (Piper TTS)
curl -sf http://10.10.10.2:8005/health
```

## Verificación Grafo

```bash
# Requests recientes
cypher-shell -u neo4j -p 'Leon1234$' "MATCH (r:VoiceRequest) RETURN r.id, r.voice_enabled ORDER BY r.started_at DESC LIMIT 5"

# Outcome más reciente
cypher-shell -u neo4j -p 'Leon1234$' "MATCH (r:VoiceRequest)-[:HAS_OUTCOME]->(o) RETURN r.id, o.voice_ttfc_ns, o.bytes_streamed ORDER BY r.started_at DESC LIMIT 1"
```

## Pipeline

```
WS /chat (10.10.10.1:8084)
    → DeliverySubgraph
    → PipecatRendererNode  
    → PiperStreamProvider
    → POST /synthesize_stream (10.10.10.2:8005)
    → render.voice.delta (PCM s16le 22050Hz)
    → play_denis_ws.py → stdout
    → ffplay (altavos PC)
```

## Opcional: Home Assistant Bridge

```bash
# Variables entorno
export DENIS_HASS_ENABLED=1
export HA_BASE_URL=http://localhost:8123
export HA_TOKEN=<long_lived_token>
export HA_MEDIA_PLAYER=media_player.salon
```

## Troubleshooting

| Problema | Solución |
|----------|----------|
| No hay audio | Verificar `voice_enabled: true` en request |
| ffplay error "Invalid PCM packet" | Chunk pequeño al final, ignorable |
| Nodo2 no responde | `curl -sf http://10.10.10.2:8005/health` |
| Grafo vacío | El servicio no reiniciado tras cambios |
