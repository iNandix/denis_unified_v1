# Configuración Multi-Nodo - Denis + Pipecat

## Distribución de Servicios

### Nodo1 (Local - Este equipo)
```
Denis Persona (Orquestador)
├─ Control Plane Daemon
├─ CP Generator + Queue
├─ Approval Popup
├─ 4 Workers (Celery + Redis)
├─ Neo4j (Grafo local)
└─ Rasa/ParLAI (NLU local)
```

### Nodo2 (Remoto - Voz)
```
Pipecat + Piper
├─ Servidor WebSocket de voz
├─ Modelo Piper TTS
├─ STT (Speech-to-Text)
└─ Interfaz conversacional
```

## Comunicación Nodo1 ↔ Nodo2

```python
# En kernel/denis_persona.py - Configuración Pipecat
PIPECAT_CONFIG = {
    "enabled": True,
    "node": "nodo2",
    "websocket_url": "ws://nodo2:8765/voice",
    "api_url": "http://nodo2:8000/api",
    "model": "piper",
    "voice_id": "denis_voice_v1"
}
```

## Flujo de Voz

```
1. Usuario habla (micrófono)
   ↓
2. Nodo2 - Pipecat recibe audio
   ↓ STT (Speech-to-Text)
3. Nodo2 - Texto → Nodo1 vía WebSocket
   ↓
4. Nodo1 - Denis Persona procesa
   ├─ Rasa NLU (entiende)
   ├─ Decide estrategia
   └─ Genera respuesta
   ↓
5. Nodo1 - Respuesta → Nodo2 vía API
   ↓
6. Nodo2 - Piper TTS (Text-to-Speech)
   ↓
7. Usuario escucha (altavoz)
```

## MCP Tools para Pipecat

```python
# denis_mcp_server.py - Tools de voz
{
    "name": "pipecat_speak",
    "description": "Envía texto a Pipecat para sintetizar voz",
    "endpoint": "http://nodo2:8000/api/speak"
},
{
    "name": "pipecat_listen", 
    "description": "Escucha input de voz del usuario",
    "endpoint": "ws://nodo2:8765/voice/listen"
}
```

## Estado de Servicios

```bash
# Nodo1
systemctl --user status denis-control-plane  # ✅ Active
systemctl --user status denis-cp-graph        # ✅ Active
redis-cli ping                                # ✅ PONG

# Nodo2 (verificar)
curl http://nodo2:8000/health                 # ?
websocat ws://nodo2:8765/voice                # ?
```
