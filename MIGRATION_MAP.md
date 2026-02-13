production_system:
  base_path: /media/jotah/SSD_denis
  entry_point: denis_persona_canonical.py:8084
  services:
    - name: denis-persona
      port: 8084
      pid: <detectar>
      systemd_unit: denis-persona.service
      description: "Main FastAPI entry point for Denis Persona"
    - name: smx-swarm
      port: 9990
      pid: <detectar>
      systemd_unit: smx-swarm.service
      description: "SMX orchestration service"
    - name: rasa-nlu
      port: 5005
      pid: <detectar>
      systemd_unit: rasa-nlu.service
      description: "Rasa NLU for intent recognition"
    - name: parlai-nlu
      port: 5006
      pid: <detectar>
      systemd_unit: parlai-nlu.service
      description: "ParlAI NLU as alternative"
    - name: home-assistant
      port: 8123
      host: 192.168.1.34
      pid: <detectar>
      description: "Home Assistant integration"
    - name: neo4j
      ports: [7474, 7687]
      pid: <detectar>
      systemd_unit: neo4j.service
      description: "Neo4j graph database"
    - name: redis
      port: 6379
      pid: <detectar>
      systemd_unit: redis.service
      description: "Redis cache and pub/sub"
    - name: mongodb-atlas
      port: 27017
      host: 192.168.1.65
      description: "MongoDB Atlas for additional storage"
  databases:
    neo4j:
      uri: bolt://localhost:7687
      user: neo4j
      password: denisneo4j
      database: neo4j
      http_port: 7474
    redis:
      uri: redis://localhost:6379/0
      db: 0
    mongodb:
      host: 192.168.1.65
      port: 27017
      database: denis_atlas
  smx_motors:
    - role: tokenize
      model: SmolLM2 1.7B
      port: 8006
      node: 10.10.10.2
      endpoint: http://10.10.10.2:8006
    - role: safety
      model: Gemma 1B
      port: 8007
      node: 10.10.10.2
      endpoint: http://10.10.10.2:8007
    - role: fast
      model: Qwen 0.5B
      port: 8003
      node: 10.10.10.2
      endpoint: http://10.10.10.2:8003
    - role: intent
      model: Qwen 1.5B
      port: 8008
      node: 10.10.10.2
      endpoint: http://10.10.10.2:8008
    - role: macro
      model: QwenCoder 7B
      port: 9998
      node: 127.0.0.1
      endpoint: http://127.0.0.1:9998
    - role: response
      model: Qwen 3B
      port: 9997
      node: 127.0.0.1
      endpoint: http://127.0.0.1:9997
  nlu:
    rasa:
      port: 5005
      url: http://localhost:5005
      status: <check>
      actions_port: 5055
      actions_url: http://127.0.0.1:5055
    parlai:
      port: 5006
      url: http://localhost:5006
      status: <check>
  critical_env_vars:
    - GROQ_API_KEY
    - OPENROUTER_API_KEY
    - LLAMA_CLOUD_API_KEY
    - OLLAMA_CLOUD_API_KEY
    - GOOGLE_CLIENT_ID
    - GOOGLE_CLIENT_SECRET
    - GOOGLE_PROJECT_ID
    - NEO4J_URI
    - NEO4J_USER
    - NEO4J_PASSWORD
    - REDIS_URL
    - HASS_TOKEN
    - HASS_LONG_LIVED_TOKEN
    - API_KEY
    - CLIENT_SECRET
    - DENIS_JWT_SECRET
  distributed_nodes:
    - name: node1
      host: 10.10.10.1
      tailscale: 100.86.69.108
      services: ["denis-persona", "smx-macro", "smx-response"]
    - name: node2
      host: 10.10.10.2
      tailscale: 100.93.192.27
      services: ["smx-tokenize", "smx-safety", "smx-fast", "smx-intent", "embeddings"]
    - name: nodomac
      host: 192.168.1.65
      tailscale: 100.117.11.87
      services: ["mongodb-atlas", "tool-executor"]
  iot_integration:
    home_assistant:
      url: http://192.168.1.34:8123
      token: <configured>
      user: jordi
      password: "130722"
    denis_gps:
      url: http://100.86.69.108:8010
  external_apis:
    - groq: gsk_kgLt3ZtNuxgWMGoBiBiSWGdyb3FYsLbw6Bi4VE9zFUwtenjotMv
    - openrouter: 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
    - llama_cloud: ccd90c89080c448fa4ecb56217bcd00c.BMmZbdWNvYOoajKevn7uwYYb
    - ollama_cloud: e7255cfe8030443299f345f0daf93a7e.ochdhi_6L7vSuLn2Zs0pIM6x
    - google_oauth: configured
    - google_maps: <needs_api_key>
    - google_places: <needs_api_key>

unified_v1:
  base_path: /media/jotah/SSD_denis/home_jotah/denis_unified_v1
  phases_completed: []
  placeholders_remaining:
    - sprint_orchestrator/cli.py:3010 (pass statement)
    - sprint_orchestrator/proposal_pipeline.py:484 (pass statement)
  missing_integrations:
    - SMX motors connectivity verification
    - NLU services integration
    - Graph reasoning engine integration
    - Streaming engine integration
    - Home Assistant deep integration
    - Distributed node orchestration
    - Real entity extraction in SMX enrichment
  current_status: phase_11_sprint_orchestrator_implementation_pending
