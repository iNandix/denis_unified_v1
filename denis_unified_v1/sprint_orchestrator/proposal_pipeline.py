"""Proposal-to-phased-plan pipeline using Groq (fast) + Rasa (structure)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import textwrap
from typing import Any

from .config import SprintOrchestratorConfig
from .intent_router_rasa import RasaIntentRouter
from .model_adapter import build_provider_request, invoke_provider_request, parse_provider_response
from .providers import ProviderStatus, load_provider_statuses


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower()).strip("-")
    return clean or "proposal"


def pick_file_with_zenity(*, base_dir: Path) -> Path | None:
    cmd = [
        "zenity",
        "--file-selection",
        "--title=Selecciona propuesta markdown (REFRACTOR_PHASED_TODO.md o similar)",
        f"--filename={str(base_dir)}/",
    ]
    try:
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=120)
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    selected = (proc.stdout or "").strip()
    if not selected:
        return None
    path = Path(selected).expanduser().resolve()
    if not path.exists() or not path.is_file():
        return None
    return path


@dataclass(frozen=True)
class ProposalArtifacts:
    source_file: str
    generated_phase_file: str
    generated_todo_file: str
    contextpack_file: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file,
            "generated_phase_file": self.generated_phase_file,
            "generated_todo_file": self.generated_todo_file,
            "contextpack_file": self.contextpack_file,
        }


class ProposalPipeline:
    def __init__(self, config: SprintOrchestratorConfig) -> None:
        self.config = config
        self.router = RasaIntentRouter(config)

    def run(
        self,
        *,
        source_path: Path,
        source_text: str,
        feedback: str = "",
    ) -> dict[str, Any]:
        ingest = self._ingest(source_path=source_path, source_text=source_text)
        groq = self._analyze_with_groq(source_text=source_text, feedback=feedback)
        rasa = self._analyze_with_rasa(source_text=source_text)
        merged = self._merge(source_text=source_text, ingest=ingest, groq=groq, rasa=rasa, feedback=feedback)
        return {
            "status": "ok",
            "timestamp_utc": _utc_now(),
            "ingest": ingest,
            "groq": groq,
            "rasa": rasa,
            "merged": merged,
        }

    def write_generated_docs(
        self,
        *,
        root_dir: Path,
        proposal: dict[str, Any],
    ) -> tuple[Path, Path]:
        merged = proposal.get("merged") or {}
        phase_file = root_dir / "REFRACTOR_PHASED_TODO.generated.md"
        todo_file = root_dir / "TODO_PHASES.generated.md"
        phase_file.write_text(self._render_phase_doc(merged), encoding="utf-8")
        todo_file.write_text(self._render_todo_doc(merged), encoding="utf-8")
        return phase_file, todo_file

    def write_contextpack(
        self,
        *,
        root_dir: Path,
        source_path: Path,
        proposal: dict[str, Any],
        topic: str | None = None,
    ) -> Path:
        merged = proposal.get("merged") or {}
        label = _slug(topic or source_path.stem)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out = root_dir / f"contextpack-{label}-{stamp}.md"
        out.write_text(
            self._render_contextpack(source_path=source_path, proposal=proposal, merged=merged),
            encoding="utf-8",
        )
        return out

    def _ingest(self, *, source_path: Path, source_text: str) -> dict[str, Any]:
        lines = source_text.splitlines()
        return {
            "source_file": str(source_path),
            "chars": len(source_text),
            "lines": len(lines),
            "phase_markers": len(re.findall(r"\bfase\b", source_text, flags=re.IGNORECASE)),
        }

    def _analyze_with_groq(self, *, source_text: str, feedback: str) -> dict[str, Any]:
        provider = self._select_provider("groq")
        if provider is None:
            return {
                "status": "fallback",
                "provider": "",
                "reason": "groq_not_configured",
                "payload": self._heuristic_plan(source_text),
            }

        messages = [
            {
                "role": "system",
                "content": (
                    "Eres arquitecto senior. Convierte una propuesta de refactor incremental en un plan por fases. "
                    "Devuelve SOLO JSON con keys: summary, phases, todo_by_phase, risks, checkpoints."
                ),
            },
            {
                "role": "user",
                "content": textwrap.dedent(
                    f"""
                    Entrada:
                    {source_text[:12000]}

                    Feedback adicional:
                    {feedback or "(sin feedback)"}

                    Restricciones:
                    - refactor incremental augmentativo
                    - no romper producción
                    - reversible por fase
                    - validaciones por fase
                    """
                ).strip(),
            },
        ]
        try:
            request = build_provider_request(
                config=self.config,
                status=provider,
                messages=messages,
                temperature=0.1,
                max_tokens=2200,
            )
            response = invoke_provider_request(request, timeout_sec=35.0)
            normalized = parse_provider_response(provider, response["data"])
            parsed = _extract_json_object(normalized.get("text") or "")
            if not isinstance(parsed, dict):
                parsed = self._heuristic_plan(source_text)
            return {
                "status": "ok",
                "provider": provider.provider,
                "request_format": provider.request_format,
                "payload": parsed,
            }
        except Exception as exc:
            return {
                "status": "fallback",
                "provider": provider.provider,
                "reason": str(exc),
                "payload": self._heuristic_plan(source_text),
            }

    def _analyze_with_rasa(self, *, source_text: str) -> dict[str, Any]:
        status = self.router.status()
        max_lines = 24
        candidate_lines = [
            ln.strip()
            for ln in source_text.splitlines()
            if ln.strip() and len(ln.strip()) <= 180
        ][:max_lines]
        intents: dict[str, int] = {}
        entities: dict[str, int] = {}
        samples: list[dict[str, Any]] = []
        errors = 0

        for line in candidate_lines:
            try:
                parsed = self.router.parse(line)
            except Exception:
                errors += 1
                continue
            intent_data = parsed.get("intent") or {}
            intent = str(intent_data.get("name") or "unknown")
            intents[intent] = intents.get(intent, 0) + 1
            for entity in parsed.get("entities") or []:
                if not isinstance(entity, dict):
                    continue
                name = str(entity.get("entity") or entity.get("name") or "entity")
                entities[name] = entities.get(name, 0) + 1
            if len(samples) < 6:
                samples.append(
                    {
                        "text": line[:140],
                        "intent": intent,
                        "confidence": float(intent_data.get("confidence") or 0.0),
                    }
                )

        constraints = []
        lower = source_text.lower()
        if "incremental" in lower:
            constraints.append("incremental_refactor")
        if "rollback" in lower or "reversible" in lower:
            constraints.append("rollback_required")
        if "feature flag" in lower or "flag" in lower:
            constraints.append("feature_flag_first")
        if "sin downtime" in lower or "no downtime" in lower:
            constraints.append("zero_downtime")

        return {
            "status": "ok" if errors < max(1, len(candidate_lines)) else "fallback",
            "router_status": status,
            "lines_analyzed": len(candidate_lines),
            "parse_errors": errors,
            "intent_histogram": intents,
            "entity_histogram": entities,
            "constraints": constraints,
            "samples": samples,
        }

    def _merge(
        self,
        *,
        source_text: str,
        ingest: dict[str, Any],
        groq: dict[str, Any],
        rasa: dict[str, Any],
        feedback: str,
    ) -> dict[str, Any]:
        raw_payload = groq.get("payload")
        base: dict[str, Any] = raw_payload if isinstance(raw_payload, dict) else {}
        summary = str(base.get("summary") or "").strip()
        phases = base.get("phases")
        if not isinstance(phases, list) or not phases:
            phases = self._extract_phases_from_text(source_text)
        normalized_phases = []
        for idx, item in enumerate(phases, start=1):
            if not isinstance(item, dict):
                continue
            phase_id = str(item.get("id") or f"F{idx}")
            name = str(item.get("name") or item.get("title") or f"Fase {idx}")
            goal = str(item.get("goal") or item.get("objective") or "Objetivo por definir")
            raw_tasks = item.get("tasks")
            tasks: list[Any] = raw_tasks if isinstance(raw_tasks, list) else []
            raw_validations = item.get("validations")
            validations: list[Any] = raw_validations if isinstance(raw_validations, list) else []
            raw_risks = item.get("risks")
            risks: list[Any] = raw_risks if isinstance(raw_risks, list) else []
            normalized_phases.append(
                {
                    "id": phase_id,
                    "name": name,
                    "goal": goal,
                    "tasks": [str(t) for t in tasks if str(t).strip()],
                    "validations": [str(v) for v in validations if str(v).strip()],
                    "risks": [str(r) for r in risks if str(r).strip()],
                }
            )

        if not normalized_phases:
            normalized_phases = [
                {
                    "id": "F1",
                    "name": "Bootstrap Incremental",
                    "goal": "Crear baseline operativo y verificable",
                    "tasks": ["Definir contratos", "Smokes de baseline", "Feature flags por capa"],
                    "validations": ["make preflight"],
                    "risks": ["Deriva de entorno"],
                }
            ]

        todo_by_phase: list[dict[str, Any]] = []
        raw_todo = base.get("todo_by_phase")
        if isinstance(raw_todo, list) and raw_todo:
            for item in raw_todo:
                if not isinstance(item, dict):
                    continue
                phase_id = str(item.get("phase") or "")
                raw_phase_tasks = item.get("tasks")
                phase_task_items: list[Any] = raw_phase_tasks if isinstance(raw_phase_tasks, list) else []
                todo_by_phase.append(
                    {"phase": phase_id, "tasks": [str(t) for t in phase_task_items if str(t).strip()]}
                )
        if not todo_by_phase:
            for phase_item in normalized_phases:
                phase_tasks: list[str] = list(phase_item["tasks"][:])
                if not phase_tasks:
                    phase_tasks = [f"Definir tareas concretas para {phase_item['id']}"]
                todo_by_phase.append({"phase": phase_item["id"], "tasks": phase_tasks})

        if not summary:
            summary = (
                "Refactor incremental augmentativo con coexistencia legacy+nuevo, "
                "validaciones por fase y rollback rápido."
            )
        if feedback.strip():
            summary = f"{summary} Ajuste feedback: {feedback.strip()[:220]}"

        return {
            "summary": summary,
            "source_file": ingest.get("source_file"),
            "phases": normalized_phases,
            "todo_by_phase": todo_by_phase,
            "constraints": rasa.get("constraints") or [],
            "rasa_intents": rasa.get("intent_histogram") or {},
            "generated_at_utc": _utc_now(),
        }

    def _heuristic_plan(self, source_text: str) -> dict[str, Any]:
        phases = self._extract_phases_from_text(source_text)
        todo = []
        for phase in phases:
            todo.append({"phase": phase["id"], "tasks": phase.get("tasks", []) or ["Cerrar tareas de la fase"]})
        return {
            "summary": "Plan generado por heurística local (fallback).",
            "phases": phases,
            "todo_by_phase": todo,
            "risks": ["Necesita revisión humana"],
            "checkpoints": ["Revisión de fases", "Validación de contratos"],
        }

    def _extract_phases_from_text(self, source_text: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for match in re.finditer(r"(?im)^\s*(fase\s+\d+)\s*[:\-]?\s*(.+)?$", source_text):
            phase_tag = match.group(1).strip().upper().replace(" ", "")
            title = (match.group(2) or "").strip() or match.group(1).strip().title()
            out.append(
                {
                    "id": phase_tag.replace("FASE", "F"),
                    "name": title,
                    "goal": f"Completar {title}",
                    "tasks": [f"Implementar {title}", f"Validar {title}"],
                    "validations": ["smoke", "contract checks"],
                    "risks": ["Cambios paralelos no sincronizados"],
                }
            )
        if out:
            return out
        return [
            {
                "id": "F1",
                "name": "Fase inicial",
                "goal": "Estabilizar propuesta y baseline",
                "tasks": ["Definir alcance", "Acordar checkpoints"],
                "validations": ["smoke baseline"],
                "risks": ["Ambiguedad de requisitos"],
            }
        ]

    def _select_provider(self, provider_id: str) -> ProviderStatus | None:
        for status in load_provider_statuses(self.config):
            if status.provider == provider_id and status.configured:
                return status
        return None

    def _render_phase_doc(self, merged: dict[str, Any]) -> str:
        lines = [
            "# Refactor Incremental - Plan Faseado",
            "",
            f"- Generated: {merged.get('generated_at_utc', _utc_now())}",
            f"- Source: {merged.get('source_file', '-')}",
            "",
            "## Resumen",
            "",
            str(merged.get("summary") or ""),
            "",
            "## Fases",
            "",
        ]
        for phase in merged.get("phases") or []:
            lines.append(f"### {phase.get('id')} - {phase.get('name')}")
            lines.append("")
            lines.append(f"- Objetivo: {phase.get('goal')}")
            lines.append("- Tareas:")
            for task in phase.get("tasks") or []:
                lines.append(f"  - {task}")
            lines.append("- Validaciones:")
            for validation in phase.get("validations") or []:
                lines.append(f"  - {validation}")
            lines.append("- Riesgos:")
            for risk in phase.get("risks") or []:
                lines.append(f"  - {risk}")
            lines.append("")
        constraints = merged.get("constraints") or []
        if constraints:
            lines.append("## Constraints")
            lines.append("")
            for item in constraints:
                lines.append(f"- {item}")
            lines.append("")
        return "\n".join(lines).strip() + "\n"

    def _render_todo_doc(self, merged: dict[str, Any]) -> str:
        lines = [
            "# TODO por Fase",
            "",
            f"- Generated: {merged.get('generated_at_utc', _utc_now())}",
            "",
        ]
        for item in merged.get("todo_by_phase") or []:
            phase = item.get("phase") or "F?"
            lines.append(f"## {phase}")
            lines.append("")
            for task in item.get("tasks") or []:
                lines.append(f"- [ ] {task}")
            lines.append("")
        return "\n".join(lines).strip() + "\n"

    def _render_contextpack(
        self,
        *,
        source_path: Path,
        proposal: dict[str, Any],
        merged: dict[str, Any],
    ) -> str:
        return (
            "# Contextpack\n\n"
            f"- timestamp_utc: {_utc_now()}\n"
            f"- source_file: {source_path}\n\n"
            "## Summary\n\n"
            f"{merged.get('summary', '')}\n\n"
            "## Phases\n\n"
            f"```json\n{json.dumps(merged.get('phases') or [], indent=2, ensure_ascii=True)}\n```\n\n"
            "## TodoByPhase\n\n"
            f"```json\n{json.dumps(merged.get('todo_by_phase') or [], indent=2, ensure_ascii=True)}\n```\n\n"
            "## RasaSignals\n\n"
            f"```json\n{json.dumps((proposal.get('rasa') or {}).get('intent_histogram') or {}, indent=2, ensure_ascii=True)}\n```\n"
        )


def _extract_json_object(text: str) -> dict[str, Any] | None:
    cleaned = text.strip()
    if not cleaned:
        return None
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    candidate = cleaned[start : end + 1]
    try:
        data = json.loads(candidate)
    except Exception:
        return None
    return data if isinstance(data, dict) else None
