"""Natural Language Interpreter usando el motor de inferencia DENIS existente.

Integra:
- DocumentParser: Parsea chats LLM (Claude, ChatGPT, etc.)
- ProposalAnalyzer: Usa Groq/OpenRouter para análisis semántico
- ProjectDecomposer: Divide en 4 agentes paralelos
- AgentPromptGenerator: Crea prompts especializados
- WorkerDispatch: Ejecuta 4 workers en paralelo via DENIS
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import hashlib

# Importar motor de inferencia DENIS existente
from .model_adapter import (
    build_provider_request,
    invoke_provider_request,
    parse_provider_response,
)
from .providers import (
    ProviderStatus,
    load_provider_statuses,
    ordered_configured_provider_ids,
)
from .config import SprintOrchestratorConfig
from .worker_dispatch import dispatch_worker_task, WorkerDispatchResult
from .session_store import SessionStore
from .event_bus import EventBus


class DocumentType(Enum):
    """Tipos de documentos soportados."""

    MARKDOWN = "markdown"
    TEXT = "text"
    JSON_CHAT = "json_chat"
    JSON_CLAUDE = "json_claude"
    UNKNOWN = "unknown"


class AgentSpecialty(Enum):
    """Especialidades de los 4 agentes paralelos."""

    ARCHITECT = "architect"
    BACKEND = "backend"
    FRONTEND = "frontend"
    DEVOPS = "devops"


@dataclass
class ChatMessage:
    role: str
    content: str
    timestamp: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedDocument:
    raw_content: str
    document_type: DocumentType
    messages: List[ChatMessage] = field(default_factory=list)
    extracted_text: str = ""
    file_hash: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProjectRequirement:
    description: str
    priority: str = "medium"
    category: str = "feature"
    effort: str = "medium"
    agent: str = ""


@dataclass
class ProjectAnalysis:
    title: str
    description: str
    objectives: List[str] = field(default_factory=list)
    requirements: List[ProjectRequirement] = field(default_factory=list)
    tech_stack: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    complexity: str = "medium"
    duration_estimate: str = "unknown"


@dataclass
class AgentTask:
    agent_specialty: AgentSpecialty
    description: str
    requirements: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    deliverables: List[str] = field(default_factory=list)
    tech_stack: List[str] = field(default_factory=list)
    priority: str = "medium"


@dataclass
class GeneratedPrompt:
    agent_specialty: AgentSpecialty
    system_prompt: str
    user_prompt: str
    tools: List[str] = field(default_factory=list)
    validations: List[str] = field(default_factory=list)


class DocumentParser:
    """Parser de documentos multiformato."""

    def parse(
        self, content: Union[str, Path], source_type: Optional[str] = None
    ) -> ParsedDocument:
        """Parsea un documento y detecta su tipo."""
        if isinstance(content, Path):
            raw_content = content.read_text(encoding="utf-8")
            doc_type = self._detect_type_from_path(content)
        else:
            raw_content = content
            if source_type:
                doc_type = self._str_to_doc_type(source_type)
            else:
                doc_type = self._detect_type_from_content(content)

        if doc_type == DocumentType.JSON_CHAT:
            return self._parse_json_chat(raw_content, doc_type)
        elif doc_type == DocumentType.JSON_CLAUDE:
            return self._parse_claude_export(raw_content, doc_type)
        elif doc_type == DocumentType.MARKDOWN:
            return self._parse_markdown(raw_content, doc_type)
        else:
            return self._parse_text(raw_content, doc_type)

    def _detect_type_from_path(self, path: Path) -> DocumentType:
        """Detecta tipo de documento desde la extensión."""
        suffix = path.suffix.lower()

        if suffix in [".md", ".markdown"]:
            return DocumentType.MARKDOWN
        elif suffix == ".json":
            content = path.read_text(encoding="utf-8", errors="ignore")[:1000]
            if '"role"' in content and '"content"' in content:
                if "claude" in content.lower() or "anthropic" in content.lower():
                    return DocumentType.JSON_CLAUDE
                return DocumentType.JSON_CHAT
            return DocumentType.TEXT
        else:
            return DocumentType.TEXT

    def _detect_type_from_content(self, content: str) -> DocumentType:
        """Detecta tipo de documento desde el contenido."""
        content_start = content[:500].strip()

        if content_start.startswith("{") or content_start.startswith("["):
            try:
                json.loads(content_start)
                if '"role"' in content and '"content"' in content:
                    return DocumentType.JSON_CHAT
                return DocumentType.TEXT
            except:
                pass

        if any(marker in content_start for marker in ["# ", "## ", "```"]):
            return DocumentType.MARKDOWN

        return DocumentType.TEXT

    def _parse_json_chat(self, content: str, doc_type: DocumentType) -> ParsedDocument:
        """Parsea exportación JSON de chat (OpenAI format)."""
        try:
            data = json.loads(content)
            messages = []

            if isinstance(data, list):
                msg_list = data
            elif isinstance(data, dict) and "messages" in data:
                msg_list = data["messages"]
            else:
                msg_list = []

            for msg in msg_list:
                if isinstance(msg, dict) and "role" in msg and "content" in msg:
                    messages.append(
                        ChatMessage(
                            role=msg["role"],
                            content=msg["content"],
                            timestamp=msg.get("timestamp") or msg.get("created_at"),
                            metadata={
                                k: v
                                for k, v in msg.items()
                                if k not in ["role", "content", "timestamp"]
                            },
                        )
                    )

            extracted = "\n\n".join(
                [f"{m.role.upper()}: {m.content}" for m in messages]
            )

            return ParsedDocument(
                raw_content=content,
                document_type=doc_type,
                messages=messages,
                extracted_text=extracted,
                file_hash=hashlib.sha256(content.encode()).hexdigest()[:16],
                metadata={"message_count": len(messages)},
            )
        except Exception as e:
            return ParsedDocument(
                raw_content=content,
                document_type=DocumentType.TEXT,
                extracted_text=content,
                file_hash=hashlib.sha256(content.encode()).hexdigest()[:16],
                metadata={"parse_error": str(e)},
            )

    def _parse_claude_export(
        self, content: str, doc_type: DocumentType
    ) -> ParsedDocument:
        """Parsea exportación de Claude (Anthropic)."""
        try:
            data = json.loads(content)
            messages = []

            if isinstance(data, dict):
                chat_data = data.get("chat_messages", []) or data.get("messages", [])

                for msg in chat_data:
                    if isinstance(msg, dict):
                        role = msg.get("sender", msg.get("role", "unknown"))
                        text = msg.get("text", msg.get("content", ""))
                        messages.append(
                            ChatMessage(
                                role=role,
                                content=text
                                if isinstance(text, str)
                                else json.dumps(text),
                                timestamp=msg.get("created_at"),
                                metadata={"uuid": msg.get("uuid", "")},
                            )
                        )

            extracted = "\n\n".join(
                [f"{m.role.upper()}: {m.content}" for m in messages]
            )

            return ParsedDocument(
                raw_content=content,
                document_type=doc_type,
                messages=messages,
                extracted_text=extracted,
                file_hash=hashlib.sha256(content.encode()).hexdigest()[:16],
                metadata={"message_count": len(messages), "source": "claude"},
            )
        except Exception as e:
            return ParsedDocument(
                raw_content=content,
                document_type=DocumentType.TEXT,
                extracted_text=content,
                file_hash=hashlib.sha256(content.encode()).hexdigest()[:16],
                metadata={"parse_error": str(e)},
            )

    def _parse_markdown(self, content: str, doc_type: DocumentType) -> ParsedDocument:
        """Parsea documento Markdown."""
        return ParsedDocument(
            raw_content=content,
            document_type=doc_type,
            extracted_text=content,
            file_hash=hashlib.sha256(content.encode()).hexdigest()[:16],
            metadata={"line_count": content.count("\n")},
        )

    def _parse_text(self, content: str, doc_type: DocumentType) -> ParsedDocument:
        """Parsea texto plano."""
        return ParsedDocument(
            raw_content=content,
            document_type=doc_type,
            extracted_text=content,
            file_hash=hashlib.sha256(content.encode()).hexdigest()[:16],
            metadata={"char_count": len(content)},
        )

    def _str_to_doc_type(self, source_type: str) -> DocumentType:
        """Convierte string a DocumentType."""
        type_map = {
            "markdown": DocumentType.MARKDOWN,
            "text": DocumentType.TEXT,
            "json_chat": DocumentType.JSON_CHAT,
            "json_claude": DocumentType.JSON_CLAUDE,
        }
        return type_map.get(source_type.lower(), DocumentType.TEXT)


class ProposalAnalyzer:
    """Analiza propuestas usando el motor de inferencia DENIS (Groq/OpenRouter/etc)."""

    def __init__(self, config: SprintOrchestratorConfig):
        self.config = config
        self._provider_cache: Optional[ProviderStatus] = None

    def _select_provider(self) -> Optional[ProviderStatus]:
        """Selecciona el mejor provider configurado."""
        if self._provider_cache:
            return self._provider_cache

        statuses = load_provider_statuses(self.config)

        # Prioridad: groq > openrouter > claude > ollama
        priority = ["groq", "openrouter", "claude", "ollama_cloud", "vllm"]
        for provider_id in priority:
            for status in statuses:
                if status.provider == provider_id and status.configured:
                    self._provider_cache = status
                    return status

        # Fallback al primero disponible
        configured = [s for s in statuses if s.configured]
        if configured:
            self._provider_cache = configured[0]
            return configured[0]

        return None

    def analyze(
        self, parsed_doc: ParsedDocument, context: Optional[Dict] = None
    ) -> ProjectAnalysis:
        """Analiza el documento parseado usando LLM.

        Returns:
            ProjectAnalysis con título, objetivos, requerimientos, tech stack, etc.
        """
        provider = self._select_provider()
        if not provider:
            raise RuntimeError("No hay providers de LLM configurados")

        # Preparar prompt para análisis
        system_prompt = """Eres un arquitecto de software experto. Analiza la siguiente propuesta de proyecto y extrae:
1. Título claro y descriptivo
2. Descripción resumida (máximo 3 párrafos)
3. Lista de objetivos principales
4. Requerimientos funcionales y no funcionales (cada uno con: descripción, prioridad alta/media/baja, categoría feature/fix/refactor/docs, esfuerzo estimado small/medium/large)
5. Tech stack identificado (lenguajes, frameworks, bases de datos, herramientas)
6. Restricciones o consideraciones importantes
7. Nivel de complejidad: low/medium/high

Responde SOLO con JSON válido con esta estructura:
{
  "title": "string",
  "description": "string",
  "objectives": ["string"],
  "requirements": [{"description": "string", "priority": "medium", "category": "feature", "effort": "medium"}],
  "tech_stack": ["string"],
  "constraints": ["string"],
  "complexity": "medium"
}"""

        user_content = f"""Documento a analizar:

{parsed_doc.extracted_text[:15000]}

Contexto adicional: {json.dumps(context) if context else "Ninguno"}"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            # Usar motor de inferencia DENIS existente
            request = build_provider_request(
                config=self.config,
                status=provider,
                messages=messages,
                temperature=0.2,
                max_tokens=4000,
            )

            response = invoke_provider_request(request, timeout_sec=60.0)
            normalized = parse_provider_response(provider, response["data"])

            # Extraer JSON de la respuesta
            result = self._extract_json(normalized.get("text", ""))

            if not result:
                raise ValueError("No se pudo extraer JSON válido de la respuesta")

            # Construir ProjectAnalysis
            requirements = []
            for req in result.get("requirements", []):
                requirements.append(
                    ProjectRequirement(
                        description=req.get("description", ""),
                        priority=req.get("priority", "medium"),
                        category=req.get("category", "feature"),
                        effort=req.get("effort", "medium"),
                    )
                )

            return ProjectAnalysis(
                title=result.get("title", "Proyecto sin título"),
                description=result.get("description", ""),
                objectives=result.get("objectives", []),
                requirements=requirements,
                tech_stack=result.get("tech_stack", []),
                constraints=result.get("constraints", []),
                complexity=result.get("complexity", "medium"),
                duration_estimate=self._estimate_duration(requirements),
            )

        except Exception as e:
            # Fallback: análisis básico
            return self._heuristic_analysis(parsed_doc)

    def _extract_json(self, text: str) -> Optional[Dict]:
        """Extrae objeto JSON de texto."""
        text = text.strip()

        # Intentar parsear directamente
        try:
            return json.loads(text)
        except:
            pass

        # Buscar entre backticks
        if "```json" in text:
            match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except:
                    pass

        # Buscar primer objeto JSON
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except:
                pass

        return None

    def _heuristic_analysis(self, parsed_doc: ParsedDocument) -> ProjectAnalysis:
        """Análisis heurístico básico sin LLM."""
        text = parsed_doc.extracted_text
        lines = text.split("\n")

        # Extraer título de primera línea
        title = lines[0][:80] if lines else "Proyecto"

        # Buscar objetivos
        objectives = []
        for line in lines:
            if any(
                marker in line.lower() for marker in ["objetivo:", "goal:", "meta:"]
            ):
                objectives.append(line.split(":", 1)[-1].strip())

        return ProjectAnalysis(
            title=title,
            description=text[:500],
            objectives=objectives or ["Definir objetivos del proyecto"],
            requirements=[],
            tech_stack=[],
            constraints=[],
            complexity="medium",
            duration_estimate="unknown",
        )

    def _estimate_duration(self, requirements: List[ProjectRequirement]) -> str:
        """Estima duración basada en requerimientos."""
        if not requirements:
            return "unknown"

        effort_map = {"small": 1, "medium": 2, "large": 4}
        total = sum(effort_map.get(r.effort, 2) for r in requirements)

        if total <= 3:
            return "1-2 días"
        elif total <= 8:
            return "3-5 días"
        elif total <= 15:
            return "1-2 semanas"
        else:
            return "2+ semanas"


class ProjectDecomposer:
    """Descompone proyecto en 4 tareas paralelas para agentes especializados."""

    def decompose(self, analysis: ProjectAnalysis) -> List[AgentTask]:
        """Divide el análisis en 4 tareas especializadas.

        Returns:
            Lista de 4 AgentTask (architect, backend, frontend, devops)
        """
        tasks = []

        # 1. Arquitecto: Diseño y estructura
        architect_reqs = self._filter_requirements(
            analysis.requirements, ["architect", "structure", "design", "api"]
        )
        tasks.append(
            AgentTask(
                agent_specialty=AgentSpecialty.ARCHITECT,
                description=f"Diseñar arquitectura y estructura del proyecto: {analysis.title}",
                requirements=architect_reqs
                or ["Definir arquitectura general", "Establecer patrones de diseño"],
                dependencies=[],
                deliverables=[
                    "Diagrama de arquitectura",
                    "Estructura de carpetas",
                    "Definición de interfaces/APIs",
                    "Documentación técnica inicial",
                ],
                tech_stack=self._filter_tech_stack(
                    analysis.tech_stack, ["framework", "architecture"]
                ),
                priority="high",
            )
        )

        # 2. Backend: Lógica de negocio
        backend_reqs = self._filter_requirements(
            analysis.requirements, ["backend", "api", "database", "logic", "server"]
        )
        tasks.append(
            AgentTask(
                agent_specialty=AgentSpecialty.BACKEND,
                description=f"Implementar lógica de negocio y APIs: {analysis.title}",
                requirements=backend_reqs
                or [
                    "Implementar endpoints API",
                    "Lógica de negocio",
                    "Integración con base de datos",
                ],
                dependencies=["architect"],  # Depende del arquitecto
                deliverables=[
                    "API endpoints funcionales",
                    "Modelos de datos",
                    "Lógica de negocio implementada",
                    "Tests de backend",
                ],
                tech_stack=self._filter_tech_stack(
                    analysis.tech_stack, ["backend", "database", "api", "server"]
                ),
                priority="high",
            )
        )

        # 3. Frontend: UI/UX
        frontend_reqs = self._filter_requirements(
            analysis.requirements, ["frontend", "ui", "ux", "interface", "component"]
        )
        tasks.append(
            AgentTask(
                agent_specialty=AgentSpecialty.FRONTEND,
                description=f"Desarrollar interfaz de usuario: {analysis.title}",
                requirements=frontend_reqs
                or ["Diseñar UI/UX", "Implementar componentes", "Integración con API"],
                dependencies=["backend"],  # Depende del backend
                deliverables=[
                    "Componentes UI",
                    "Pantallas/vistas",
                    "Estilos y tema",
                    "Tests de frontend",
                ],
                tech_stack=self._filter_tech_stack(
                    analysis.tech_stack,
                    ["frontend", "ui", "css", "react", "vue", "angular"],
                ),
                priority="medium",
            )
        )

        # 4. DevOps: Infraestructura
        devops_reqs = self._filter_requirements(
            analysis.requirements, ["deploy", "ci/cd", "docker", "infra", "test"]
        )
        tasks.append(
            AgentTask(
                agent_specialty=AgentSpecialty.DEVOPS,
                description=f"Configurar infraestructura y deployment: {analysis.title}",
                requirements=devops_reqs
                or [
                    "Configurar CI/CD",
                    "Dockerización",
                    "Scripts de deploy",
                    "Monitoreo",
                ],
                dependencies=["backend", "frontend"],  # Depende de ambos
                deliverables=[
                    "Dockerfile y docker-compose",
                    "Pipeline CI/CD",
                    "Scripts de deployment",
                    "Configuración de monitoreo",
                ],
                tech_stack=self._filter_tech_stack(
                    analysis.tech_stack, ["docker", "ci/cd", "aws", "kubernetes"]
                ),
                priority="medium",
            )
        )

        return tasks

    def _filter_requirements(
        self, requirements: List[ProjectRequirement], keywords: List[str]
    ) -> List[str]:
        """Filtra requerimientos por keywords."""
        filtered = []
        for req in requirements:
            desc_lower = req.description.lower()
            if any(kw in desc_lower for kw in keywords):
                filtered.append(req.description)
        return filtered

    def _filter_tech_stack(
        self, tech_stack: List[str], keywords: List[str]
    ) -> List[str]:
        """Filtra tech stack por keywords."""
        filtered = []
        for tech in tech_stack:
            tech_lower = tech.lower()
            if any(kw in tech_lower for kw in keywords):
                filtered.append(tech)
        return filtered or tech_stack[:5]  # Si no hay match, devolver primeros 5


class AgentPromptGenerator:
    """Genera prompts especializados para cada uno de los 4 agentes."""

    # System prompts especializados por agente
    SYSTEM_PROMPTS = {
        AgentSpecialty.ARCHITECT: """Eres un Arquitecto de Software Senior con 15 años de experiencia.
Tu especialidad es diseñar arquitecturas limpias, escalables y mantenibles.

PRINCIPIOS:
- SOLID, DRY, KISS
- Patrones de diseño apropiados al contexto
- Separación de responsabilidades claras
- Documentación técnica concisa pero completa

DEBES PRODUCIR:
1. Estructura de carpetas y módulos
2. Diagrama de componentes (en formato texto/Mermaid si es posible)
3. Definición de interfaces/contracts
4. Decisiones de arquitectura documentadas
5. Consideraciones de escalabilidad y mantenibilidad

RESTRICCIONES:
- No escribas código de implementación, solo interfaces y estructura
- Sé específico en nombres de archivos y carpetas
- Justifica decisiones arquitectónicas clave""",
        AgentSpecialty.BACKEND: """Eres un Backend Developer Senior experto en APIs RESTful, bases de datos y lógica de negocio.

PRINCIPIOS:
- API-first design
- Validación exhaustiva de inputs
- Manejo robusto de errores
- Tests unitarios y de integración
- Performance y optimización

DEBES PRODUCIR:
1. Implementación de endpoints API
2. Modelos de datos y esquemas
3. Lógica de negocio completa
4. Manejo de errores y validaciones
5. Tests automatizados

RESTRICCIONES:
- Código type-hinted (Python) o con tipos estrictos
- Manejo de errores try/except apropiado
- Nunca devuelvas datos sensibles en errores
- Documenta funciones complejas con docstrings""",
        AgentSpecialty.FRONTEND: """Eres un Frontend Developer Senior especializado en UX/UI y componentes reutilizables.

PRINCIPIOS:
- Componentes desacoplados y reutilizables
- Responsive design
- Accesibilidad (a11y)
- Performance (lazy loading, memoización)
- Estado manejado apropiadamente

DEBES PRODUCIR:
1. Componentes UI funcionales
2. Estilos consistentes (CSS/Tailwind/styled-components)
3. Manejo de estado local y global
4. Integración con API backend
5. Tests de componentes

RESTRICCIONES:
- Usa hooks/modern patterns
- Componentes pequeños y enfocados
- Props bien documentadas
- Manejo de estados de carga y error""",
        AgentSpecialty.DEVOPS: """Eres un DevOps Engineer Senior experto en CI/CD, containers y cloud.

PRINCIPIOS:
- Infrastructure as Code
- Automatización total
- Seguridad por defecto
- Observabilidad (logs, métricas, trazas)
- Reproducibilidad de ambientes

DEBES PRODUCIR:
1. Dockerfile optimizado (multi-stage si aplica)
2. Docker-compose para desarrollo
3. Pipeline CI/CD (GitHub Actions/GitLab CI/Jenkins)
4. Scripts de deployment
5. Configuración de monitoreo básico

RESTRICCIONES:
- No hardcodees secrets (usa variables de entorno)
- Documenta variables de entorno requeridas
- Considera ambientes dev/staging/prod
- Health checks y readiness probes""",
    }

    def generate(self, task: AgentTask, analysis: ProjectAnalysis) -> GeneratedPrompt:
        """Genera prompt completo para un agente específico."""
        specialty = task.agent_specialty
        system_prompt = self.SYSTEM_PROMPTS[specialty]

        # Construir user prompt contextualizado
        user_prompt = self._build_user_prompt(task, analysis)

        # Definir herramientas necesarias por especialidad
        tools = self._get_tools_for_specialty(specialty)

        # Definir criterios de validación
        validations = self._get_validations_for_specialty(specialty)

        return GeneratedPrompt(
            agent_specialty=specialty,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            tools=tools,
            validations=validations,
        )

    def generate_all(
        self, tasks: List[AgentTask], analysis: ProjectAnalysis
    ) -> List[GeneratedPrompt]:
        """Genera prompts para todos los agentes."""
        return [self.generate(task, analysis) for task in tasks]

    def _build_user_prompt(self, task: AgentTask, analysis: ProjectAnalysis) -> str:
        """Construye el user prompt específico para una tarea."""
        sections = [
            f"# PROYECTO: {analysis.title}",
            "",
            f"## Descripción\n{analysis.description}",
            "",
            f"## Tu Rol\n{task.agent_specialty.value.upper()}: {task.description}",
            "",
        ]

        if task.requirements:
            sections.append("## Requerimientos Específicos")
            for req in task.requirements:
                sections.append(f"- {req}")
            sections.append("")

        if task.tech_stack:
            sections.append("## Tech Stack")
            for tech in task.tech_stack:
                sections.append(f"- {tech}")
            sections.append("")

        if task.dependencies:
            sections.append(
                f"## Dependencias\nEsperar a: {', '.join(task.dependencies)}"
            )
            sections.append("")

        sections.append("## Deliverables Esperados")
        for deliverable in task.deliverables:
            sections.append(f"- [ ] {deliverable}")
        sections.append("")

        if analysis.objectives:
            sections.append("## Objetivos Generales del Proyecto")
            for obj in analysis.objectives:
                sections.append(f"- {obj}")
            sections.append("")

        if analysis.constraints:
            sections.append("## Restricciones y Consideraciones")
            for constraint in analysis.constraints:
                sections.append(f"- {constraint}")
            sections.append("")

        sections.append("""## Instrucciones
1. Trabaja en tu área de especialidad según los deliverables listados
2. Sigue las restricciones y consideraciones del proyecto
3. Documenta decisiones importantes
4. Si encuentras ambigüedades, documenta tus supuestos
5. Entrega código/implementación completa y funcional

Comienza a trabajar en tu asignación ahora.""")

        return "\n".join(sections)

    def _get_tools_for_specialty(self, specialty: AgentSpecialty) -> List[str]:
        """Devuelve herramientas recomendadas por especialidad."""
        tools_map = {
            AgentSpecialty.ARCHITECT: [
                "code_search",
                "file_read",
                "file_write",
                "diagram_generation",
                "documentation",
            ],
            AgentSpecialty.BACKEND: [
                "code_search",
                "file_read",
                "file_write",
                "test_runner",
                "type_checker",
                "linter",
            ],
            AgentSpecialty.FRONTEND: [
                "code_search",
                "file_read",
                "file_write",
                "test_runner",
                "css_validator",
                "component_preview",
            ],
            AgentSpecialty.DEVOPS: [
                "file_read",
                "file_write",
                "shell",
                "docker_build",
                "pipeline_validator",
            ],
        }
        return tools_map.get(specialty, ["code_search", "file_read", "file_write"])

    def _get_validations_for_specialty(self, specialty: AgentSpecialty) -> List[str]:
        """Devuelve criterios de validación por especialidad."""
        validations_map = {
            AgentSpecialty.ARCHITECT: [
                "Estructura clara y lógica",
                "Interfaces bien definidas",
                "Documentación presente",
                "Decisiones justificadas",
            ],
            AgentSpecialty.BACKEND: [
                "Código compila/ejecuta sin errores",
                "Tests pasan",
                "Type checking exitoso",
                "Sin placeholders ni stubs",
            ],
            AgentSpecialty.FRONTEND: [
                "Componentes renderizan correctamente",
                "Tests pasan",
                "Responsive funcional",
                "Sin errores de lint",
            ],
            AgentSpecialty.DEVOPS: [
                "Docker build exitoso",
                "Pipeline válido",
                "Scripts ejecutables",
                "Variables documentadas",
            ],
        }
        return validations_map.get(specialty, ["Código funcional", "Sin errores"])


class NLInterpreter:
    """Intérprete de lenguaje natural integrado con motor DENIS.

    Flujo completo:
    1. Parsear documento (chat LLM, markdown, etc.)
    2. Analizar con LLM (Groq/OpenRouter/etc via DENIS)
    3. Descomponer en 4 tareas paralelas
    4. Generar prompts especializados
    5. Ejecutar 4 workers en paralelo via WorkerDispatch
    """

    def __init__(self, config: SprintOrchestratorConfig):
        self.config = config
        self.parser = DocumentParser()
        self.analyzer = ProposalAnalyzer(config)
        self.decomposer = ProjectDecomposer()
        self.prompt_generator = AgentPromptGenerator()

    def process_document(
        self,
        content: Union[str, Path],
        source_type: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Procesa documento completo y genera plan para 4 agentes.

        Args:
            content: Documento a procesar (path o string)
            source_type: Tipo de documento (opcional)
            context: Contexto adicional del proyecto

        Returns:
            Dict con análisis, tareas y prompts para 4 agentes
        """
        # 1. Parsear documento
        parsed = self.parser.parse(content, source_type)

        # 2. Analizar con LLM
        analysis = self.analyzer.analyze(parsed, context)

        # 3. Descomponer en 4 tareas
        tasks = self.decomposer.decompose(analysis)

        # 4. Generar prompts
        prompts = self.prompt_generator.generate_all(tasks, analysis)

        return {
            "parsed_document": parsed,
            "project_analysis": analysis,
            "agent_tasks": tasks,
            "generated_prompts": prompts,
            "execution_plan": self._create_execution_plan(tasks),
            "metadata": {
                "document_hash": parsed.file_hash,
                "timestamp": datetime.now().isoformat(),
                "agent_count": 4,
                "parallel": True,
            },
        }

    def execute_parallel_agents(
        self,
        result: Dict[str, Any],
        store: SessionStore,
        session_id: str,
        projects: List[Path],
        bus: Optional[EventBus] = None,
    ) -> Dict[str, Any]:
        """Ejecuta los 4 agentes en paralelo usando WorkerDispatch.

        Args:
            result: Resultado de process_document
            store: SessionStore para persistencia
            session_id: ID de sesión
            projects: Lista de proyectos a trabajar
            bus: EventBus opcional para notificaciones

        Returns:
            Resultados de ejecución de los 4 workers
        """
        prompts = result["generated_prompts"]
        execution_results = {}

        # Ejecutar 4 workers en paralelo (usando asyncio o threading)
        import concurrent.futures

        def dispatch_agent(prompt: GeneratedPrompt, worker_id: str) -> Dict[str, Any]:
            """Despacha un agente específico."""
            messages = [
                {"role": "system", "content": prompt.system_prompt},
                {"role": "user", "content": prompt.user_prompt},
            ]

            # Usar dispatch_worker_task de DENIS
            dispatch_result = dispatch_worker_task(
                config=self.config,
                store=store,
                session_id=session_id,
                worker_id=worker_id,
                provider_status=self._get_provider_for_agent(prompt.agent_specialty),
                messages=messages,
                timeout_sec=300.0,  # 5 minutos por agente
                bus=bus,
            )

            return {
                "agent": prompt.agent_specialty.value,
                "worker_id": worker_id,
                "status": dispatch_result.status,
                "mode": dispatch_result.mode,
                "provider": dispatch_result.provider,
                "duration_ms": dispatch_result.duration_ms,
                "result": dispatch_result.details,
                "error": None if dispatch_result.status == "ok" else "Execution failed",
            }

        # Ejecutar en paralelo
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            future_to_agent = {
                executor.submit(
                    dispatch_agent, prompt, f"{prompt.agent_specialty.value}_worker"
                ): prompt.agent_specialty
                for prompt in prompts
            }

            for future in concurrent.futures.as_completed(future_to_agent):
                specialty = future_to_agent[future]
                try:
                    execution_results[specialty.value] = future.result()
                except Exception as exc:
                    execution_results[specialty.value] = {
                        "agent": specialty.value,
                        "status": "error",
                        "error": str(exc),
                    }

        return {
            "parallel_execution": execution_results,
            "completed_agents": len(
                [r for r in execution_results.values() if r.get("status") == "ok"]
            ),
            "failed_agents": len(
                [r for r in execution_results.values() if r.get("status") == "error"]
            ),
            "total_agents": 4,
        }

    def _get_provider_for_agent(self, specialty: AgentSpecialty) -> ProviderStatus:
        """Selecciona provider apropiado para cada tipo de agente."""
        statuses = load_provider_statuses(self.config)

        # DevOps y Architect pueden usar providers más ligeros
        # Backend y Frontend necesitan providers más potentes
        priority = {
            AgentSpecialty.ARCHITECT: ["groq", "openrouter", "claude"],
            AgentSpecialty.BACKEND: ["groq", "openrouter", "claude"],
            AgentSpecialty.FRONTEND: ["groq", "openrouter", "ollama_cloud"],
            AgentSpecialty.DEVOPS: ["groq", "ollama_cloud", "vllm"],
        }

        for provider_id in priority.get(specialty, ["groq"]):
            for status in statuses:
                if status.provider == provider_id and status.configured:
                    return status

        # Fallback al primero configurado
        configured = [s for s in statuses if s.configured]
        if configured:
            return configured[0]

        raise RuntimeError("No hay providers configurados")

    def _create_execution_plan(self, tasks: List[AgentTask]) -> Dict[str, Any]:
        """Crea plan de ejecución paralela considerando dependencias."""
        # Fase 1: Architect (sin dependencias)
        # Fase 2: Backend (depende de architect)
        # Fase 3: Frontend (depende de backend)
        # Fase 4: DevOps (depende de backend y frontend)

        phases = [
            {
                "phase": 1,
                "agents": ["architect"],
                "can_parallel": False,
                "dependencies": [],
            },
            {
                "phase": 2,
                "agents": ["backend"],
                "can_parallel": False,
                "dependencies": ["architect"],
            },
            {
                "phase": 3,
                "agents": ["frontend"],
                "can_parallel": False,
                "dependencies": ["backend"],
            },
            {
                "phase": 4,
                "agents": ["devops"],
                "can_parallel": False,
                "dependencies": ["backend", "frontend"],
            },
        ]

        return {
            "phases": phases,
            "estimated_duration": "30-60 minutos (dependiendo de complejidad)",
            "parallelizable": False,  # Por ahora secuencial por dependencias
            "strategy": "sequential_with_dependencies",
        }


def interpret_document(
    content: Union[str, Path],
    config: SprintOrchestratorConfig,
    source_type: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Función de conveniencia para interpretar documentos.

    Args:
        content: Documento a procesar
        config: Configuración de SprintOrchestrator
        source_type: Tipo de documento
        context: Contexto adicional

    Returns:
        Resultado completo con análisis y prompts para 4 agentes
    """
    interpreter = NLInterpreter(config)
    return interpreter.process_document(content, source_type, context)
