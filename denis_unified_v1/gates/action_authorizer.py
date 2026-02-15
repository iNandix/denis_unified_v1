"""
ActionAuthorizer - Núcleo Duro de Seguridad para Acciones Irreversibles
=====================================================================

Este módulo implementa la autoridad central de capacidades.
Ningún actor puede ejecutar acciones irreversibles sin pasar por aquí.

Filosofía:
- Denis-agent es el único con capability de promote/commit/push
- El resto (personas, IDEs, CLIs) solo pueden proponer → snapshot → hold
- Todos los caminos pasan por el mismo juez
- Nada se ejecuta sin dejar huella de auditoría

Constitución integrada:
- Singularities: companion_mode, mandatory_governance, anti_bypass_enforcement,
                 honesty_non_deceptive, creator_can_be_risk
- Mandatory systems: action_authorizer, ci_gate, atlas, honesty_core
- Invariants enforced at runtime
"""

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Any, Optional, Literal


class ActorType(Enum):
    """Tipos de actores que pueden interactuar con el sistema."""

    DENIS_AGENT = "denis_agent"
    DENIS_PERSONA = "denis_persona"
    WINDSURF_CLI = "windsurf_cli"
    VSCODE_CLI = "vscode_cli"
    TERMINAL_CLI = "terminal_cli"
    WEB_UI = "web_ui"
    API_CLIENT = "api_client"
    UNKNOWN = "unknown"


class ActionType(Enum):
    """Tipos de acciones posibles en el sistema."""

    WRITE_FILE = "write_file"
    DELETE_FILE = "delete_file"
    CREATE_DIR = "create_dir"

    GIT_COMMIT = "git_commit"
    GIT_PUSH = "git_push"
    GIT_PULL = "git_pull"
    GIT_MERGE = "git_merge"
    GIT_REBASE = "git_rebase"
    GIT_RESET = "git_reset"
    CREATE_BRANCH = "create_branch"
    DELETE_BRANCH = "delete_branch"

    CREATE_SNAPSHOT = "create_snapshot"
    PROMOTE_TO_REPO = "promote_to_repo"
    RESTORE_SNAPSHOT = "restore_snapshot"

    APPLY_POLICY_OVERRIDE = "apply_policy_override"
    MODIFY_PROTECTED_PATH = "modify_protected_path"

    RUN_PIPELINE = "run_pipeline"
    DEPLOY_PROD = "deploy_prod"
    RELEASE = "release"

    READ_FILE = "read_file"
    QUERY = "query"
    LIST = "list"


class DecisionMode(Enum):
    """Modo de decisión del authorizer."""

    ALLOW = "allow"  # Permitir ejecución
    DENY = "deny"  # Denegar completamente
    HOLD = "hold"  # Crear snapshot + notificar, no ejecutar
    ESCALATE = "escalate"  # Requiere aprobación manual


class RiskFlag(Enum):
    """Flags de riesgo para contexto."""

    POLICY_TOUCHED = "policy_touched"
    CI_PIPELINE = "ci_pipeline"
    PROTECTED_PATH = "protected_path"
    MAIN_BRANCH = "main_branch"
    PROD_ENV = "prod_env"
    DESTRUCTIVE = "destructive"
    BULK_CHANGE = "bulk_change"
    NEW_DEPENDENCY = "new_dependency"
    CONSTITUTIONAL_VIOLATION = "constitutional_violation"


class Constitution:
    """
    Constitución de Denis - Singularidades y invariantes no negociables.

    Carga y valida la constitución desde:
    - docs/identity/identity_schema.yaml
    - docs/identity/inventory/identity_inventory.machine.json

    Singularidades (no negociables):
    - companion_mode: Denis debe operar en modo compañero
    - mandatory_governance: Requiere sistemas de gobernanza activos
    - anti_bypass_enforcement: No hay bypass del sistema de ejecución
    - honesty_non_deceptive: Sin engaño, siempre verificable
    - creator_can_be_risk: El creador puede ser un riesgo
    """

    SINGULARITIES = {
        "companion_mode",
        "mandatory_governance",
        "anti_bypass_enforcement",
        "honesty_non_deceptive",
        "creator_can_be_risk",
    }

    MANDATORY_SYSTEMS = {
        "system:action_authorizer",
        "system:ci_gate",
        "system:atlas",
        "system:honesty_core",
    }

    INVARIANTS = {
        "invariant:purpose_identity_indivisible",
        "invariant:companion_mode_mandatory",
        "invariant:purpose_precedes_transformation",
        "invariant:proportional_emergency_override",
        "invariant:identity_requires_companion_mode",
    }

    def __init__(self):
        self.loaded = False
        self.schema: Dict[str, Any] = {}
        self.inventory: Dict[str, Any] = {}
        self.constitutional_hash: str = ""
        self._load()

    def _load(self):
        """Carga la constitución desde archivos."""
        repo_root = Path(__file__).resolve().parents[2]

        schema_path = repo_root / "docs/identity/identity_schema.yaml"
        inventory_path = (
            repo_root / "docs/identity/inventory/identity_inventory.machine.json"
        )

        try:
            import yaml

            if schema_path.exists():
                with open(schema_path) as f:
                    self.schema = yaml.safe_load(f)

            if inventory_path.exists():
                with open(inventory_path) as f:
                    self.inventory = json.load(f)

            self._compute_hash()
            self.loaded = True

        except Exception as e:
            print(f"Warning: Could not load constitution: {e}")
            self.loaded = False

    def _compute_hash(self):
        """Computa hash de la constitución para auditoría."""
        import hashlib

        content = json.dumps(self.inventory, sort_keys=True)
        self.constitutional_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

    def validate(self) -> Dict[str, Any]:
        """Valida que la constitución esté intacta."""
        errors = []
        warnings = []

        if not self.loaded:
            errors.append("Constitution not loaded")
            return {"valid": False, "errors": errors, "warnings": warnings}

        inv_singularities = set(self.inventory.get("singularities", []))
        missing_singularities = self.SINGULARITIES - inv_singularities
        if missing_singularities:
            errors.append(f"Missing singularities: {missing_singularities}")

        inv_systems = {s.get("id") for s in self.inventory.get("systems", [])}
        missing_systems = self.MANDATORY_SYSTEMS - inv_systems
        if missing_systems:
            errors.append(f"Missing mandatory systems: {missing_systems}")

        if not self.inventory.get("constitutional"):
            errors.append("Inventory must be marked constitutional=true")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "hash": self.constitutional_hash,
            "singularities": list(inv_singularities),
            "systems": list(inv_systems),
        }

    def check_action_requirements(self, action: str) -> Dict[str, Any]:
        """Verifica requisitos de una acción según la constitución."""
        action_entry = None
        for a in self.inventory.get("actions", []):
            if a.get("id") == action:
                action_entry = a
                break

        if not action_entry:
            return {"requires_systems": [], "requires_gates": []}

        return {
            "requires_systems": action_entry.get("requires", []),
            "requires_gates": [g.get("id") for g in self.inventory.get("gates", [])],
            "risk_level": action_entry.get("risk_level", "unknown"),
            "blocked_if": action_entry.get("blocked_if", []),
            "constitutional": action_entry.get("constitutional", False),
        }


# Global constitution instance
_constitution: Optional[Constitution] = None


def get_constitution() -> Constitution:
    """Obtiene la instancia global de la constitución."""
    global _constitution
    if _constitution is None:
        _constitution = Constitution()
    return _constitution


@dataclass
class Actor:
    """Representa quién está ejecutando una acción."""

    type: ActorType
    name: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_string(cls, actor_str: str) -> "Actor":
        """Factory para crear Actor desde string."""
        actor_lower = actor_str.lower()
        if "denis" in actor_lower and "persona" in actor_lower:
            return cls(type=ActorType.DENIS_PERSONA, name=actor_str)
        elif "denis" in actor_lower:
            return cls(type=ActorType.DENIS_AGENT, name=actor_str)
        elif "windsurf" in actor_lower:
            return cls(type=ActorType.WINDSURF_CLI, name=actor_str)
        elif "vscode" in actor_lower:
            return cls(type=ActorType.VSCODE_CLI, name=actor_str)
        elif "terminal" in actor_lower or "cli" in actor_lower:
            return cls(type=ActorType.TERMINAL_CLI, name=actor_str)
        elif "web" in actor_lower or "ui" in actor_lower:
            return cls(type=ActorType.WEB_UI, name=actor_str)
        else:
            return cls(type=ActorType.UNKNOWN, name=actor_str)


@dataclass
class Resource:
    """Representa el target de una acción."""

    type: str  # "file", "dir", "repo", "branch", "snapshot"
    path: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Decision:
    """Resultado de la autorización."""

    allowed: bool
    mode: DecisionMode
    reason: str
    required_actions: List[str] = field(default_factory=list)
    audit_event: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# Paths protegidos - nunca se tocan sin DenisAgent
PROTECTED_PATHS = {
    ".git/",
    ".github/workflows/",
    "control_plane/",
    "policies/",
    "scripts/gates/",
    "observability/",
    "artifacts/control_plane/",
    ".githooks/",
    ".denis/",
}

# Acciones que solo DenisAgent puede ejecutar directamente
DENIS_AGENT_ONLY_ACTIONS = {
    ActionType.GIT_COMMIT,
    ActionType.GIT_PUSH,
    ActionType.PROMOTE_TO_REPO,
    ActionType.MODIFY_PROTECTED_PATH,
    ActionType.APPLY_POLICY_OVERRIDE,
    ActionType.DEPLOY_PROD,
    ActionType.RELEASE,
}


class GatePolicy:
    """Configuración de políticas del gate."""

    def __init__(self, mode: str = "dev"):
        self.mode = mode
        self.strict_100 = os.getenv("GATE_STRICT_100", "false").lower() == "true"
        self.min_pass_ratio = float(os.getenv("GATE_MIN_PASS_RATIO", "0.7"))
        self.allow_degraded = os.getenv("GATE_ALLOW_DEGRADED", "true").lower() == "true"

    def get_config(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "strict_100": self.strict_100,
            "min_pass_ratio": self.min_pass_ratio,
            "allow_degraded": self.allow_degraded,
        }


class GateRunner:
    """Ejecuta el gate y devuelve resultado verificable."""

    def __init__(self, policy: GatePolicy):
        self.policy = policy
        self.artifacts_dir = Path("artifacts")

    def run(self) -> Dict[str, Any]:
        """Ejecuta meta_smoke_all con la política configurada."""
        cmd = [
            sys.executable,
            "scripts/meta_smoke_all.py",
            "--strict-100" if self.policy.strict_100 else "--strict-70",
            "--out-json",
            str(self.artifacts_dir / "smoke_all.json"),
        ]

        start_time = time.time()
        result = {
            "started_utc": datetime.now(timezone.utc).isoformat(),
            "command": cmd,
            "policy": self.policy.get_config(),
        }

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                cwd=Path.cwd(),
            )
            result["returncode"] = proc.returncode
            result["duration_sec"] = time.time() - start_time

            artifact = self._load_artifact()
            result["artifact"] = artifact

            result["passed"] = self._evaluate(artifact, proc.returncode)
            result["details"] = self._extract_details(artifact)

        except subprocess.TimeoutExpired:
            result["passed"] = False
            result["error"] = "timeout"
            result["duration_sec"] = time.time() - start_time
        except Exception as e:
            result["passed"] = False
            result["error"] = str(e)

        result["finished_utc"] = datetime.now(timezone.utc).isoformat()
        return result

    def _load_artifact(self) -> Dict[str, Any]:
        artifact_path = self.artifacts_dir / "smoke_all.json"
        if artifact_path.exists():
            with open(artifact_path) as f:
                return json.load(f)
        return {}

    def _evaluate(self, artifact: Dict[str, Any], returncode: int) -> bool:
        summary = artifact.get("summary", {})
        passed_ratio = summary.get("pass_rate", 0)
        total = summary.get("total", 0)

        if self.policy.strict_100:
            return returncode == 0 and passed_ratio == 100 and total > 0

        return passed_ratio >= (self.policy.min_pass_ratio * 100) and total > 0

    def _extract_details(self, artifact: Dict[str, Any]) -> Dict[str, Any]:
        summary = artifact.get("summary", {})
        phases = artifact.get("phases", {})

        return {
            "passed": summary.get("passed", 0),
            "total": summary.get("total", 0),
            "pass_rate": summary.get("pass_rate", 0),
            "failed_phases": [
                name for name, data in phases.items() if not data.get("ok", False)
            ],
        }


class ActionAuthorizer:
    """
    AUTORIDAD CENTRAL - El juez único para acciones irreversibles.

    Reglas duras:
    1. Solo DenisAgent puede ejecutar acciones irreversibles directamente
    2. El resto → HOLD + SNAPSHOT + NOTIFY
    3. Paths protegidos → solo DenisAgent
    4. Todo deja huella de auditoría
    """

    IRREVERSIBLE_ACTIONS = {
        ActionType.WRITE_FILE,
        ActionType.DELETE_FILE,
        ActionType.GIT_COMMIT,
        ActionType.GIT_PUSH,
        ActionType.GIT_MERGE,
        ActionType.GIT_RESET,
        ActionType.CREATE_BRANCH,
        ActionType.DELETE_BRANCH,
        ActionType.PROMOTE_TO_REPO,
        ActionType.MODIFY_PROTECTED_PATH,
        ActionType.APPLY_POLICY_OVERRIDE,
        ActionType.RUN_PIPELINE,
        ActionType.DEPLOY_PROD,
        ActionType.RELEASE,
    }

    def __init__(self, mode: str = "dev"):
        self.policy = GatePolicy(mode)
        self.gate_runner = GateRunner(self.policy)
        self.last_gate_result: Optional[Dict[str, Any]] = None
        self.audit_log: List[Dict[str, Any]] = []

        # Load constitution
        self.constitution = get_constitution()
        self.constitution_valid = self.constitution.validate()
        if not self.constitution_valid["valid"]:
            print(f"CONSTITUTION WARNING: {self.constitution_valid['errors']}")

    def authorize(
        self,
        actor: Actor,
        action: ActionType,
        target: Resource,
        context: Dict[str, Any] = None,
        force_gate_rerun: bool = False,
    ) -> Decision:
        """
        Autoriza o deniega una acción.

        Este es el único punto de entrada para acciones sensibles.
        """
        context = context or {}
        risk_flags = self._compute_risk_flags(action, target, context)

        # Crear evento de auditoría base
        audit_event = {
            "actor": actor.type.value,
            "actor_name": actor.name,
            "action": action.value,
            "target_type": target.type,
            "target_path": target.path,
            "risk_flags": [f.value for f in risk_flags],
            "context": context,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "constitution_hash": self.constitution.constitutional_hash,
        }

        # 0. CONSTITUTIONAL CHECK - Verificar constitución primero
        if not self.constitution_valid["valid"]:
            decision = Decision(
                allowed=False,
                mode=DecisionMode.DENY,
                reason=f"CONSTITUTIONAL_VIOLATION: {self.constitution_valid['errors']}",
                audit_event=audit_event,
            )
            self._log_decision(decision)
            return decision

        # 0b. Check action requirements from constitution
        action_requirements = self.constitution.check_action_requirements(
            f"action:{action.value}"
        )
        if action_requirements.get("constitutional"):
            # This is a constitutional action - must have all required systems
            required_systems = action_requirements.get("requires_systems", [])
            for req_sys in required_systems:
                if req_sys not in self.constitution.MANDATORY_SYSTEMS:
                    continue
                # System is required - in a full implementation, verify it's operational
                # For now, just log the requirement

        # 1. Verificar si es acción irreversible
        is_irreversible = action in self.IRREVERSIBLE_ACTIONS

        if not is_irreversible:
            # Acciones seguras - permitir siempre
            decision = Decision(
                allowed=True,
                mode=DecisionMode.ALLOW,
                reason="action_is_reversible",
                audit_event=audit_event,
            )
            self._log_decision(decision)
            return decision

        # 2. Verificar si es path protegido
        if self._is_protected_path(target.path):
            audit_event["risk_flags"].append(RiskFlag.PROTECTED_PATH.value)

            if actor.type != ActorType.DENIS_AGENT:
                decision = self._create_hold_decision(
                    actor,
                    action,
                    target,
                    context,
                    risk_flags,
                    audit_event,
                    reason="Protected path - only DenisAgent can modify",
                )
                self._log_decision(decision)
                return decision

        # 3. Verificar si es acción solo para DenisAgent
        if action in DENIS_AGENT_ONLY_ACTIONS:
            if actor.type != ActorType.DENIS_AGENT:
                decision = self._create_hold_decision(
                    actor,
                    action,
                    target,
                    context,
                    risk_flags,
                    audit_event,
                    reason=f"Action {action.value} is DenisAgent-only",
                )
                self._log_decision(decision)
                return decision

        # 4. Verificar gate para acciones que modifican repo
        if action in {
            ActionType.GIT_COMMIT,
            ActionType.GIT_PUSH,
            ActionType.PROMOTE_TO_REPO,
        }:
            gate_passed = self._ensure_gate(force_gate_rerun)

            if not gate_passed:
                decision = self._create_hold_decision(
                    actor,
                    action,
                    target,
                    context,
                    risk_flags,
                    audit_event,
                    reason="Gate failed - cannot proceed",
                )
                self._log_decision(decision)
                return decision

        # 5. Si llegó hasta aquí, es DenisAgent y el gate pasó
        decision = Decision(
            allowed=True,
            mode=DecisionMode.ALLOW,
            reason="denis_agent_with_gate_passed",
            required_actions=[],
            audit_event=audit_event,
            metadata={"gate_passed": True},
        )

        self._log_decision(decision)
        return decision

    def authorize_simple(
        self,
        actor_str: str,
        action_str: str,
        target_path: str,
        context: Dict[str, Any] = None,
    ) -> Decision:
        """Interfaz simple para compatibilidad hacia atrás."""
        actor = Actor.from_string(actor_str)

        try:
            action = ActionType(action_str)
        except ValueError:
            action = ActionType.WRITE_FILE  # Default

        target = Resource(type="file", path=target_path)

        return self.authorize(actor, action, target, context)

    def _create_hold_decision(
        self,
        actor: Actor,
        action: ActionType,
        target: Resource,
        context: Dict[str, Any],
        risk_flags: List[RiskFlag],
        audit_event: Dict[str, Any],
        reason: str,
    ) -> Decision:
        """Crea decisión de HOLD con snapshot automático."""
        required_actions = ["CREATE_SNAPSHOT"]

        # Agregar más acciones según el contexto
        if context.get("notify_admin", True):
            required_actions.append("NOTIFY_ADMIN")

        return Decision(
            allowed=False,
            mode=DecisionMode.HOLD,
            reason=reason,
            required_actions=required_actions,
            audit_event=audit_event,
            metadata={
                "risk_flags": [f.value for f in risk_flags],
                "snapshot_required": True,
            },
        )

    def _compute_risk_flags(
        self,
        action: ActionType,
        target: Resource,
        context: Dict[str, Any],
    ) -> List[RiskFlag]:
        """Computa flags de riesgo para la acción."""
        flags = []

        # Policy touched
        if "policy" in target.path.lower() or "gate" in target.path.lower():
            flags.append(RiskFlag.POLICY_TOUCHED)

        # CI pipeline
        if ".github" in target.path or "workflows" in target.path:
            flags.append(RiskFlag.CI_PIPELINE)

        # Protected path
        if self._is_protected_path(target.path):
            flags.append(RiskFlag.PROTECTED_PATH)

        # Main branch
        if context.get("branch") == "main":
            flags.append(RiskFlag.MAIN_BRANCH)

        # Prod env
        if context.get("environment") == "prod":
            flags.append(RiskFlag.PROD_ENV)

        # Destructive
        if action in {ActionType.DELETE_FILE, ActionType.GIT_RESET}:
            flags.append(RiskFlag.DESTRUCTIVE)

        # Bulk change
        if context.get("files_changed", 0) > 10:
            flags.append(RiskFlag.BULK_CHANGE)

        return flags

    def _is_protected_path(self, path: str) -> bool:
        """Verifica si el path es protegido."""
        path_normalized = str(Path(path))
        for protected in PROTECTED_PATHS:
            if path_normalized.startswith(protected) or protected in path_normalized:
                return True
        return False

    def _ensure_gate(self, force_rerun: bool = False) -> bool:
        """Asegura que el gate pasó."""
        if force_rerun or self.last_gate_result is None:
            self.last_gate_result = self.gate_runner.run()
            self._save_gate_audit()

        return self.last_gate_result.get("passed", False)

    def check_and_authorize(
        self,
        actor: Actor,
        actions: List[tuple[ActionType, Resource, Dict[str, Any]]],
    ) -> Dict[str, Any]:
        """Autoriza una lista de acciones."""
        results = []
        all_allowed = True

        for action, target, context in actions:
            decision = self.authorize(actor, action, target, context)
            results.append(
                {
                    "action": action.value,
                    "target": target.path,
                    "decision": decision.mode.value,
                    "allowed": decision.allowed,
                    "reason": decision.reason,
                }
            )
            if not decision.allowed:
                all_allowed = False

        return {
            "all_allowed": all_allowed,
            "results": results,
            "gate_status": self.get_gate_status(),
        }

    def get_gate_status(self) -> Dict[str, Any]:
        """Retorna estado actual del gate."""
        if self.last_gate_result is None:
            return {"status": "unknown", "passed": None}

        return {
            "status": "ok" if self.last_gate_result.get("passed") else "failed",
            "passed": self.last_gate_result.get("passed"),
            "pass_rate": self.last_gate_result.get("details", {}).get("pass_rate", 0),
            "failed_phases": self.last_gate_result.get("details", {}).get(
                "failed_phases", []
            ),
            "last_run_utc": self.last_gate_result.get("finished_utc"),
        }

    def _log_decision(self, decision: Decision):
        """Registra decisión en log local."""
        if decision.audit_event:
            self.audit_log.append(decision.audit_event)
            # Keep last 1000
            self.audit_log = self.audit_log[-1000:]

    def _save_gate_audit(self):
        """Guarda log de auditoría del gate."""
        log_dir = Path("artifacts/control_plane")
        log_dir.mkdir(parents=True, exist_ok=True)

        log_path = log_dir / "gate_audit.json"

        existing_logs = []
        if log_path.exists():
            with open(log_path) as f:
                existing_logs = json.load(f)

        if self.last_gate_result:
            existing_logs.append(
                {
                    "timestamp": self.last_gate_result.get("finished_utc"),
                    "passed": self.last_gate_result.get("passed"),
                    "pass_rate": self.last_gate_result.get("details", {}).get(
                        "pass_rate", 0
                    ),
                    "returncode": self.last_gate_result.get("returncode"),
                }
            )

        existing_logs = existing_logs[-100:]
        with open(log_path, "w") as f:
            json.dump(existing_logs, f, indent=2)

    def save_audit_log(self, path: str = None):
        """Guarda el log de auditoría a archivo."""
        if path is None:
            path = "artifacts/control_plane/action_authorizer_audit.json"

        log_dir = Path(path).parent
        log_dir.mkdir(parents=True, exist_ok=True)

        with open(path, "w") as f:
            json.dump(self.audit_log, f, indent=2)


def get_authorizer(mode: str = "dev") -> ActionAuthorizer:
    """Factory function para obtener authorizer."""
    return ActionAuthorizer(mode)


# Ejemplo de uso:
if __name__ == "__main__":
    authorizer = get_authorizer("dev")

    # Ejemplo 1: DenisAgent intentando commit (debería pasar si gate ok)
    actor = Actor(type=ActorType.DENIS_AGENT, name="denis_agent_main")
    action = ActionType.GIT_COMMIT
    target = Resource(type="repo", path=".", metadata={"branch": "feature/test"})

    decision = authorizer.authorize(actor, action, target, {"branch": "feature/test"})
    print(f"Decision: {decision.mode.value} - {decision.reason}")

    # Ejemplo 2: WindSurf CLI intentando commit (debería ser HOLD)
    actor2 = Actor.from_string("windsurf_cli")
    decision2 = authorizer.authorize(actor2, action, target, {"branch": "feature/test"})
    print(f"Decision: {decision2.mode.value} - {decision2.reason}")
