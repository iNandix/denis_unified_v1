"""
API Registry Web Interface - Registro y gestión de providers LLM
Usa provider_loader.py (sistema existente en denis_unified_v1)
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Configurar rutas
base_dir = Path(__file__).parent.parent  # denis_unified_v1
if str(base_dir) not in sys.path:
    sys.path.insert(0, str(base_dir))

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn
import logging

# Importar directamente para evitar __init__.py problemático
import importlib.util

loader_path = base_dir / "inference" / "provider_loader.py"
spec = importlib.util.spec_from_file_location("provider_loader", str(loader_path))
provider_loader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provider_loader)

DiscoveredModel = provider_loader.DiscoveredModel
ProviderLoadRegistry = provider_loader.ProviderLoadRegistry
discover_provider_models = provider_loader.discover_provider_models

logger = logging.getLogger(__name__)


@dataclass
class APIProvider:
    """Provider de API registrado"""

    id: str
    name: str
    provider_type: str
    api_key_masked: str
    endpoint: str
    is_active: bool = True
    last_check: Optional[str] = None
    models_count: int = 0
    free_models_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelClassification:
    """Clasificación de modelo por especialidad"""

    model_id: str
    provider: str
    specialties: Dict[str, float]
    best_for: str
    confidence: float
    last_evaluated: str


class APIRegistry:
    """Registro centralizado de APIs LLM"""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or Path("data/api_registry.json")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.providers: Dict[str, APIProvider] = {}
        self.model_classifications: Dict[str, ModelClassification] = {}
        self.provider_loader_registry = ProviderLoadRegistry()
        self._load_registry()

    def _load_registry(self):
        """Carga registro desde disco"""
        if self.db_path.exists():
            try:
                data = json.loads(self.db_path.read_text())
                for p in data.get("providers", []):
                    self.providers[p["id"]] = APIProvider(**p)
                for m in data.get("classifications", []):
                    self.model_classifications[m["model_id"]] = ModelClassification(**m)
                logger.info(f"Loaded {len(self.providers)} providers from registry")
            except Exception as e:
                logger.error(f"Failed to load registry: {e}")

    def _save_registry(self):
        """Guarda registro a disco"""
        data = {
            "providers": [asdict(p) for p in self.providers.values()],
            "classifications": [asdict(m) for m in self.model_classifications.values()],
            "last_updated": datetime.now().isoformat(),
        }
        self.db_path.write_text(json.dumps(data, indent=2))

    def register_provider(
        self,
        provider_type: str,
        api_key: str,
        name: Optional[str] = None,
        endpoint: Optional[str] = None,
    ) -> APIProvider:
        """Registra un nuevo provider de API"""
        provider_id = f"{provider_type}_{len(self.providers) + 1}"

        # Mask API key for storage
        masked_key = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "****"

        # Default endpoints
        default_endpoints = {
            "openrouter": "https://openrouter.ai/api/v1",
            "groq": "https://api.groq.com/openai/v1",
            "claude": "https://api.anthropic.com/v1",
            "ollama": "http://localhost:11434/v1",
        }

        provider = APIProvider(
            id=provider_id,
            name=name or f"{provider_type.title()} Provider",
            provider_type=provider_type,
            api_key_masked=masked_key,
            endpoint=endpoint or default_endpoints.get(provider_type, ""),
            is_active=True,
            last_check=datetime.now().isoformat(),
        )

        self.providers[provider_id] = provider
        self._save_registry()

        # Set environment variable for provider_loader
        env_var_map = {
            "openrouter": "OPENROUTER_API_KEY",
            "groq": "GROQ_API_KEY",
            "claude": "ANTHROPIC_API_KEY",
        }
        if provider_type in env_var_map:
            os.environ[env_var_map[provider_type]] = api_key

        logger.info(f"Registered provider: {provider_id}")
        return provider

    def get_provider(self, provider_id: str) -> Optional[APIProvider]:
        """Obtiene un provider por ID"""
        return self.providers.get(provider_id)

    def list_providers(self) -> List[APIProvider]:
        """Lista todos los providers registrados"""
        return list(self.providers.values())

    def sync_with_provider_loader(self) -> Dict[str, Any]:
        """Sincroniza con provider_loader para obtener modelos"""
        all_models = []

        # Obtener modelos de cada provider registrado
        for provider_id, provider in self.providers.items():
            if not provider.is_active:
                continue

            try:
                # Usar provider_loader para descubrir modelos
                total, models = discover_provider_models(
                    provider=provider.provider_type,
                    api_key=os.getenv(f"{provider.provider_type.upper()}_API_KEY", ""),
                )

                all_models.extend(models)

                # Actualizar conteos
                provider.models_count = total
                provider.free_models_count = len([m for m in models if m.is_free])
                provider.last_check = datetime.now().isoformat()

            except Exception as e:
                logger.error(f"Failed to sync {provider_id}: {e}")
                provider.is_active = False

        self._save_registry()

        return {
            "providers_synced": len(self.providers),
            "total_models": len(all_models),
            "free_models": len([m for m in all_models if m.is_free]),
        }

    def classify_models(
        self, models: List[DiscoveredModel]
    ) -> List[ModelClassification]:
        """Clasifica modelos por las 4 especialidades"""
        classifications = []

        for model in models:
            # Calcular scores por especialidad
            scores = self._calculate_specialty_scores(model)

            # Determinar mejor especialidad
            best_specialty = max(scores, key=scores.get)
            confidence = scores[best_specialty]

            classification = ModelClassification(
                model_id=model.model_id,
                provider=model.provider,
                specialties=scores,
                best_for=best_specialty,
                confidence=confidence,
                last_evaluated=datetime.now().isoformat(),
            )

            classifications.append(classification)
            self.model_classifications[model.model_id] = classification

        self._save_registry()
        return classifications

    def _calculate_specialty_scores(self, model: DiscoveredModel) -> Dict[str, float]:
        """Calcula scores del modelo para cada especialidad"""
        scores = {"architect": 0.0, "backend": 0.0, "frontend": 0.0, "devops": 0.0}

        model_name = model.model_name.lower()
        model_id = model.model_id.lower()
        tags = [t.lower() for t in model.tags]

        # ARCHITECT: Razonamiento + contexto largo
        if model.context_length >= 32000:
            scores["architect"] += 4.0
        elif model.context_length >= 16000:
            scores["architect"] += 3.0
        else:
            scores["architect"] += 1.0

        if "reasoning" in tags or "think" in model_id:
            scores["architect"] += 4.0
        if "code" in tags:
            scores["architect"] += 2.0
        if model.supports_tools:
            scores["architect"] += 1.5

        # BACKEND: Code + tools + JSON
        if "code" in tags:
            scores["backend"] += 5.0
        if "instruct" in tags:
            scores["backend"] += 2.0
        if model.supports_tools:
            scores["backend"] += 3.0
        if model.supports_json_mode:
            scores["backend"] += 2.5
        if model.context_length >= 16000:
            scores["backend"] += 1.5

        # FRONTEND: JSON + instruct + rápido
        if model.supports_json_mode:
            scores["frontend"] += 4.0
        if "instruct" in tags:
            scores["frontend"] += 3.0
        if model.context_length >= 4096:
            scores["frontend"] += 2.0
        if model.context_length <= 8192:
            scores["frontend"] += 1.5
        if "code" in tags:
            scores["frontend"] += 1.0

        # DEVOPS: Tools + JSON + scripts
        if model.supports_tools:
            scores["devops"] += 4.0
        if model.supports_json_mode:
            scores["devops"] += 4.0
        if "instruct" in tags:
            scores["devops"] += 2.5
        if model.context_length >= 4096:
            scores["devops"] += 1.5

        # Bonus por tamaño
        if "70b" in model_id or "large" in model_name:
            scores["architect"] *= 1.2
            scores["backend"] *= 1.2
        elif "7b" in model_id or "small" in model_name:
            scores["frontend"] *= 1.15
            scores["architect"] *= 0.85

        # Normalizar a 0-10
        for key in scores:
            scores[key] = min(10.0, scores[key])

        return scores


# Crear app FastAPI
app = FastAPI(title="DENIS API Registry", version="1.0.0")
registry = APIRegistry()


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Dashboard principal"""
    providers = registry.list_providers()

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>DENIS API Registry</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
            .header {{ background: #2c3e50; color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
            .card {{ background: white; padding: 20px; margin-bottom: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
            .provider {{ display: flex; justify-content: space-between; align-items: center; padding: 15px; 
                        border: 1px solid #ddd; margin: 10px 0; border-radius: 5px; }}
            .provider.active {{ border-left: 4px solid #27ae60; }}
            .provider.inactive {{ border-left: 4px solid #e74c3c; }}
            .btn {{ padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; font-size: 14px; }}
            .btn-primary {{ background: #3498db; color: white; }}
            .btn-success {{ background: #27ae60; color: white; }}
            .stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 20px; }}
            .stat-box {{ background: white; padding: 20px; border-radius: 8px; text-align: center; 
                        box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
            .stat-number {{ font-size: 32px; font-weight: bold; color: #2c3e50; }}
            .stat-label {{ color: #7f8c8d; margin-top: 5px; }}
            form {{ display: flex; gap: 10px; flex-wrap: wrap; }}
            input, select {{ padding: 10px; border: 1px solid #ddd; border-radius: 5px; font-size: 14px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🧠 DENIS API Registry</h1>
            <p>Registro y gestión de providers LLM</p>
        </div>

        <div class="stats">
            <div class="stat-box">
                <div class="stat-number">{len(providers)}</div>
                <div class="stat-label">Providers Registrados</div>
            </div>
            <div class="stat-box">
                <div class="stat-number">{
        len([p for p in providers if p.is_active])
    }</div>
                <div class="stat-label">Providers Activos</div>
            </div>
            <div class="stat-box">
                <div class="stat-number" id="total-models">-</div>
                <div class="stat-label">Modelos Descubiertos</div>
            </div>
            <div class="stat-box">
                <div class="stat-number" id="free-models">-</div>
                <div class="stat-label">Modelos Gratuitos</div>
            </div>
        </div>

        <div class="card">
            <h2>➕ Registrar Nuevo Provider</h2>
            <form id="register-form">
                <select id="provider-type" required>
                    <option value="">Seleccionar tipo...</option>
                    <option value="openrouter">OpenRouter</option>
                    <option value="groq">Groq</option>
                    <option value="claude">Claude (Anthropic)</option>
                </select>
                <input type="text" id="provider-name" placeholder="Nombre (opcional)">
                <input type="password" id="api-key" placeholder="API Key" required>
                <button type="submit" class="btn btn-primary">Registrar</button>
            </form>
        </div>

        <div class="card">
            <h2>🔗 Providers Registrados</h2>
            <div id="providers-list">
                {
        "".join(
            [
                f'''
                <div class="provider {"active" if p.is_active else "inactive"}">
                    <div>
                        <strong>{p.name}</strong> ({p.provider_type})
                        <br><small>{p.endpoint}</small>
                    </div>
                    <div>
                        <span style="color: {"#27ae60" if p.is_active else "#e74c3c"}">
                            {"Activo" if p.is_active else "Inactivo"}
                        </span>
                        <br><small>{p.models_count} modelos ({p.free_models_count} free)</small>
                    </div>
                </div>
                '''
                for p in providers
            ]
        )
    }
            </div>
        </div>

        <script>
            document.getElementById('register-form').onsubmit = async (e) => {{
                e.preventDefault();
                const data = {{
                    provider_type: document.getElementById('provider-type').value,
                    name: document.getElementById('provider-name').value,
                    api_key: document.getElementById('api-key').value
                }};
                
                const response = await fetch('/api/providers/register', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify(data)
                }});
                
                if (response.ok) {{
                    alert('Provider registrado!');
                    location.reload();
                }} else {{
                    alert('Error al registrar');
                }}
            }};
            
            // Cargar estadísticas
            fetch('/api/models').then(r => r.json()).then(data => {{
                document.getElementById('total-models').textContent = data.total_models || '-';
                document.getElementById('free-models').textContent = data.free_models || '-';
            }});
        </script>
    </body>
    </html>
    """

    return HTMLResponse(content=html_content)


@app.get("/api/providers", response_class=JSONResponse)
async def list_providers():
    """Lista todos los providers"""
    providers = registry.list_providers()
    return {"providers": [asdict(p) for p in providers], "count": len(providers)}


@app.post("/api/providers/register", response_class=JSONResponse)
async def register_provider(data: Dict[str, Any]):
    """Registra un nuevo provider"""
    try:
        provider = registry.register_provider(
            provider_type=data["provider_type"],
            api_key=data["api_key"],
            name=data.get("name"),
            endpoint=data.get("endpoint"),
        )

        # Sincronizar con provider_loader
        sync_result = registry.sync_with_provider_loader()

        return {"success": True, "provider": asdict(provider), "sync": sync_result}
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/models", response_class=JSONResponse)
async def list_models():
    """Lista modelos disponibles"""
    try:
        sync_result = registry.sync_with_provider_loader()

        # Obtener modelos de la base de datos del provider_loader
        db_models = registry.provider_loader_registry.list_models(available_only=True)

        return {
            "total_models": sync_result["total_models"],
            "free_models": sync_result["free_models"],
            "models": db_models,
        }
    except Exception as e:
        logger.error(f"List models error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/models/classified", response_class=JSONResponse)
async def get_classified_models():
    """Obtiene modelos clasificados por especialidad"""
    try:
        # Obtener todos los modelos
        all_models = []
        for provider in registry.providers.values():
            if not provider.is_active:
                continue
            try:
                _, models = discover_provider_models(
                    provider=provider.provider_type,
                    api_key=os.getenv(f"{provider.provider_type.upper()}_API_KEY", ""),
                )
                all_models.extend(models)
            except:
                pass

        # Clasificar
        classifications = registry.classify_models(all_models)

        # Agrupar por especialidad
        by_specialty = {"architect": [], "backend": [], "frontend": [], "devops": []}

        for classification in classifications:
            by_specialty[classification.best_for].append(
                {
                    "model_id": classification.model_id,
                    "provider": classification.provider,
                    "confidence": classification.confidence,
                    "all_scores": classification.specialties,
                }
            )

        # Ordenar por confianza
        for specialty in by_specialty:
            by_specialty[specialty].sort(key=lambda x: x["confidence"], reverse=True)

        return {"specialties": by_specialty, "total_classified": len(classifications)}
    except Exception as e:
        logger.error(f"Classification error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def start_registry_server(host: str = "0.0.0.0", port: int = 8081):
    """Inicia el servidor de registro"""
    import socket

    # Check if port is available
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        result = sock.connect_ex((host, port))
        if result == 0:
            # Port is in use, find alternative
            for alt_port in [8082, 8083, 8085, 8087, 8088, 8089, 8090]:
                result = sock.connect_ex((host, alt_port))
                if result != 0:
                    logger.warning(f"Port {port} in use, using {alt_port}")
                    port = alt_port
                    break
    finally:
        sock.close()

    logger.info(f"Starting API Registry server on {host}:{port}")
    uvicorn.run(app, host=host, port=port)


def build_registry_router():
    """Construye el router de registry para incluir en fastapi_server."""
    from fastapi import APIRouter
    router = APIRouter(prefix="/v1/providers", tags=["providers"])
    
    @router.get("/config")
    async def get_providers_config():
        return await list_providers()
    
    @router.post("/config")
    async def update_providers_config(data: Dict[str, Any]):
        return await register_provider(data)
    
    @router.get("/models")
    async def get_providers_models():
        return await list_models()
    
    @router.get("/classified")
    async def get_providers_classified():
        return await get_classified_models()
    
    return router


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    start_registry_server()
