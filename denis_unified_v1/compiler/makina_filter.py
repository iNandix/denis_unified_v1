"""Makina fallback filter - fail-open local compiler.

Cuando ChatRoom/LLM falla, este filtro genera un Makina program
básico determinista sin dependencia de LLM externo.

CON PROACTIVIDAD:
- Consulta Neo4j para implicit_tasks
- Auto-inyecta tareas "hygiene" según intent
- Añade constraints y acceptance_criteria
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from .schemas import CompilerRequest, CompilerResult, MakinaProgram, MakinaStep, MakinaTask


IMPLICIT_TASKS_BY_INTENT = {
    "implement_feature": [
        "READ target files before writing",
        "VERIFY all imports resolve after creation",
        "RUN existing tests before commit",
        "CHECK DO_NOT_TOUCH list",
    ],
    "debug_repo": [
        "READ error + stack trace first",
        "CHECK git diff last 5 commits",
        "VERIFY fix does not break existing tests",
    ],
    "refactor_migration": [
        "SNAPSHOT current behavior via tests",
        "VERIFY identical behavior post-refactor",
    ],
    "run_tests_ci": [
        "VERIFY test environment active",
        "CHECK all services needed are running",
    ],
    "toolchain_task": [
        "VERIFY tool/command exists in PATH",
        "CHECK service dependencies are up",
    ],
}

CONSTRAINTS_BY_KEYWORD = {
    "python": ["python"],
    "js": ["javascript"],
    "typescript": ["typescript"],
    "test": ["testing"],
    "async": ["async"],
    "fast": ["performance"],
}

ACCEPTANCE_CRITERIA_BY_INTENT = {
    "implement_feature": ["función existe", "tests pasan", "no errores de importación"],
    "debug_repo": ["error resuelto", "tests no regresionan"],
    "run_tests_ci": ["todos los tests pasan"],
    "refactor_migration": ["comportamiento idéntico", "tests pasan"],
}


class MakinaValidator:
    """Validador de salida Makina desde LLM."""

    VALID_KINDS = {"read", "write", "exec", "http_fallback", "ws_emit", "guard"}

    def validate(self, makina_output: str | dict) -> tuple[bool, str]:
        """Valida que el output sea un Makina válido.

        Returns: (is_valid, error_message)
        """
        try:
            if isinstance(makina_output, str):
                cleaned = makina_output.strip()
                if "```json" in cleaned:
                    cleaned = cleaned.split("```json", 1)[1].split("```", 1)[0].strip()
                elif "```" in cleaned:
                    cleaned = cleaned.split("```", 1)[1].split("```", 1)[0].strip()
                data = json.loads(cleaned)
            else:
                data = makina_output

            if "task" not in data:
                return False, "Missing 'task' field"

            if "steps" not in data or not isinstance(data.get("steps"), list):
                return False, "Missing or invalid 'steps' field"

            for i, step in enumerate(data["steps"]):
                if "id" not in step:
                    return False, f"Step {i} missing 'id'"
                if "kind" not in step:
                    return False, f"Step {i} missing 'kind'"
                if step["kind"] not in self.VALID_KINDS:
                    return False, f"Step {i} has invalid kind: {step['kind']}"

            return True, ""

        except json.JSONDecodeError as e:
            return False, f"Invalid JSON: {e}"
        except Exception as e:
            return False, f"Validation error: {e}"

    def repair(self, makina_output: str) -> str | None:
        """Intenta reparar un output Makina inválido.

        Returns: repaired JSON string or None if no repair possible.
        """
        try:
            cleaned = makina_output.strip()
            if "```json" in cleaned:
                cleaned = cleaned.split("```json", 1)[1].split("```", 1)[0].strip()
            elif "```" in cleaned:
                cleaned = cleaned.split("```", 1)[1].split("```", 1)[0].strip()

            data = json.loads(cleaned)

            if "task" not in data:
                data["task"] = {"id": "repaired", "title": "Repaired task"}

            if "steps" not in data:
                data["steps"] = []
            elif not isinstance(data["steps"], list):
                data["steps"] = []

            valid_steps = []
            for step in data["steps"]:
                if not isinstance(step, dict):
                    continue
                if "id" not in step:
                    step["id"] = f"step_{len(valid_steps) + 1}"
                if "kind" not in step:
                    step["kind"] = "read"
                if step["kind"] not in self.VALID_KINDS:
                    step["kind"] = "read"
                valid_steps.append(step)

            data["steps"] = valid_steps

            return json.dumps(data, ensure_ascii=False)

        except Exception:
            return None


class MakinaFilter:
    """Fallback local para generación de Makina programs."""

    TOOL_KEYWORDS = {
        "read": ["leer", "ver", "mostrar", "read", "show", "view", "cat", "list"],
        "write": ["escribir", "crear", "guardar", "write", "create", "save", "new"],
        "exec": ["ejecutar", "correr", "run", "exec", "execute", "npm", "python", "bash"],
    }

    def compile(self, request: CompilerRequest, retrieval_context: str = "") -> CompilerResult:
        """Compila texto NL a Makina sin LLM.

        Output enriquecido para routing:
        - intent: tipo de tarea detectada
        - constraints: tecnologías/integraciones requeridas
        - acceptance_criteria: qué significa "hecho"
        - missing_inputs: qué falta para ejecutar
        - implicit_tasks: tareas hygiene automáticas
        """
        text = request.text.lower()
        workspace = request.workspace or {}

        # 1. Detectar intent
        intent = self._detect_intent(request.text)

        # 2. Extraer constraints
        constraints = self._extract_constraints(request.text)

        # 3. Infer steps primero (para missing_inputs)
        steps = self._infer_steps(text, workspace)

        # 4. Detectar missing inputs
        missing_inputs = self._detect_missing_inputs(text, steps)

        # 5. Acceptance criteria según intent
        acceptance_criteria = ACCEPTANCE_CRITERIA_BY_INTENT.get(intent, [])

        # 6. Implicit tasks desde grafo o estáticos
        implicit_tasks = self._get_implicit_tasks(intent, workspace)

        task = MakinaTask(
            id=str(uuid.uuid4())[:8],
            title=self._infer_title(request.text),
            intent=intent,
            constraints=constraints,
            acceptance_criteria=acceptance_criteria,
            missing_inputs=missing_inputs,
            implicit_tasks=implicit_tasks,
        )

        makina = MakinaProgram(
            task=task,
            steps=steps,
            observability={
                "emit_events": True,
                "log_tags": ["fallback", "makina_filter"],
                "graph_materialize": True,
            },
        )

        return CompilerResult(
            trace_id=request.trace_id,
            run_id=request.run_id,
            makina=makina.model_dump_json()
            if hasattr(makina, "model_dump_json")
            else json.dumps(makina.model_dump()),
            compiler="fallback_local",
            degraded=True,
            confidence=0.3,
            plan=self._generate_fallback_plan(steps),
        )

    def _infer_steps(self, text: str, workspace: dict[str, Any]) -> list[MakinaStep]:
        """Infiere pasos Makina desde texto NL."""
        steps = []
        step_id = 1

        detected_tools = set()
        for tool, keywords in self.TOOL_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                detected_tools.add(tool)

        if "read" in detected_tools or not detected_tools:
            file_hint = self._extract_file_hint(text, workspace)
            if file_hint:
                steps.append(
                    MakinaStep(
                        id=f"step_{step_id}", kind="read", inputs={"files": [file_hint]}, outputs={}
                    )
                )
                step_id += 1

        if "write" in detected_tools:
            steps.append(
                MakinaStep(
                    id=f"step_{step_id}",
                    kind="write",
                    inputs={"content": self._extract_content_hint(text)},
                    outputs={"created": True},
                )
            )
            step_id += 1

        if "exec" in detected_tools:
            steps.append(
                MakinaStep(
                    id=f"step_{step_id}",
                    kind="exec",
                    inputs={"command": self._extract_command(text)},
                    outputs={},
                )
            )
            step_id += 1

        if not steps:
            steps.append(
                MakinaStep(
                    id="step_1",
                    kind="read",
                    inputs={"files": list(workspace.get("files_changed", []))},
                    outputs={},
                )
            )

        return steps

    def _detect_intent(self, text: str) -> str:
        """Detecta intent desde keywords."""
        text_lower = text.lower()

        if any(k in text_lower for k in ["crea", "implementa", "nueva", "añade"]):
            return "implement_feature"
        if any(k in text_lower for k in ["arregla", "bug", "error", "debug", "depura"]):
            return "debug_repo"
        if any(k in text_lower for k in ["refactor", "migra", "restructura"]):
            return "refactor_migration"
        if any(k in text_lower for k in ["test", "prueba", "pytest"]):
            return "run_tests_ci"
        if any(k in text_lower for k in ["explica", "qué es", "cómo funciona"]):
            return "explain_concept"
        if any(k in text_lower for k in ["documenta", "docs", "readme"]):
            return "write_docs"
        if any(k in text_lower for k in ["diseña", "arquitectura", "estructura"]):
            return "design_architecture"

        return "implement_feature"

    def _extract_constraints(self, text: str) -> list[str]:
        """Extrae constraints desde keywords."""
        text_lower = text.lower()
        constraints = []

        for kw, constraint in CONSTRAINTS_BY_KEYWORD.items():
            if kw in text_lower:
                constraints.extend(constraint)

        return list(set(constraints))

    def _detect_missing_inputs(self, text: str, steps: list) -> list[str]:
        """Detecta inputs faltantes."""
        missing = []

        if len(text.split()) < 3:
            missing.append("intent_unclear")

        has_read = any(s.kind == "read" for s in steps)
        has_write = any(s.kind == "write" for s in steps)
        has_exec = any(s.kind == "exec" for s in steps)

        if has_read:
            read_files = [s.inputs.get("files", []) for s in steps if s.kind == "read"]
            if not any(read_files):
                missing.append("target_file")

        if has_exec:
            commands = [s.inputs.get("command", "") for s in steps if s.kind == "exec"]
            if not any(commands) or not commands[0]:
                missing.append("command")

        return missing

    def _get_implicit_tasks(self, intent: str, workspace: dict) -> list[str]:
        """Obtiene implicit tasks - primero del grafo, luego estáticos."""
        # 1. Intentar desde Neo4j/grafo
        try:
            from denis_unified_v1.inference.implicit_tasks import get_implicit_tasks

            it = get_implicit_tasks()
            session_id = workspace.get("session_id", "default")
            enriched = it.enrich_with_session(intent, session_id)

            if enriched.implicit_tasks:
                return enriched.implicit_tasks
        except Exception:
            pass

        # 2. Fallback a estáticos
        return IMPLICIT_TASKS_BY_INTENT.get(intent, [])

    def _extract_file_hint(self, text: str, workspace: dict[str, Any]) -> str | None:
        """Extrae referencia a archivo del texto."""
        files = workspace.get("files_changed", [])
        if files:
            return files[0]

        path_pattern = r"[a-zA-Z0-9_/\-\.]+\.(py|js|ts|json|yaml|md|txt)"
        match = re.search(path_pattern, text)
        return match.group(0) if match else None

    def _extract_content_hint(self, text: str) -> str:
        """Extrae contenido a escribir."""
        content_match = re.search(
            r'con\s+(?:contenido|texto|con lo siguiente):?\s*["\']?(.+?)["\']?$', text
        )
        return content_match.group(1) if content_match else "contenido pendiente"

    def _extract_command(self, text: str) -> str:
        """Extrae comando a ejecutar."""
        cmd_pattern = r"(npm|python|bash|sh)\s+(.+?)(?:\s|$)"
        match = re.search(cmd_pattern, text)
        if match:
            return f"{match.group(1)} {match.group(2)}"

        action = re.search(r"(ejecutar|correr|run)\s+(.+?)(?:\s|$)", text)
        if action:
            return action.group(2)

        return "echo 'comando no especificado'"

    def _infer_title(self, text: str) -> str:
        """Infiere título de la tarea."""
        words = text.split()[:5]
        return " ".join(words) + "..." if len(text.split()) > 5 else text

    def _generate_fallback_plan(self, steps: list[MakinaStep]) -> str:
        """Genera plan legible para UX."""
        plan_parts = [f"1. {s.kind}: {s.inputs}" for s in steps]
        return "Fallback plan:\n" + "\n".join(plan_parts)


def create_fallback_result(
    request: CompilerRequest, error: str, retrieval_context: str = ""
) -> CompilerResult:
    """Factory para crear resultado de fallback desde cualquier error."""
    filter_instance = MakinaFilter()
    result = filter_instance.compile(request, retrieval_context)
    result.plan = f"Error: {error}\n\n{result.plan}"
    return result
