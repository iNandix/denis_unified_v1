from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import uuid
import logging

logger = logging.getLogger(__name__)


@dataclass
class ContextPack:
    """Context Pack for agent execution with graph integration."""

    cp_id: str = ""
    mission: str = ""
    model: str = "llamaLocal"
    repo_id: str = ""
    repo_name: str = "unknown"
    branch: str = "main"
    human_validated: bool = False
    validated_by: str = ""
    notes: str = ""
    intent: str = ""
    files_to_read: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    implicit_tasks: List[str] = field(default_factory=list)
    risk_level: str = "MEDIUM"
    is_checkpoint: bool = False
    engine_node: str = "nodo1"
    symbols_context: List[Dict] = field(default_factory=list)

    @classmethod
    async def from_agent_result(cls, result: dict) -> "ContextPack":
        """Generate CP from agent result with graph integration."""
        import os

        # Get repo info
        repo_path = result.get("repo_path", os.getcwd())
        repo_id = result.get("repo_id", "default")

        # Get intent from result
        intent = result.get("intent", "unknown")
        prompt = result.get("prompt", "")

        # Try graph routing
        engine = None
        symbols = []
        implicit_tasks_list = []

        try:
            from control_plane.precise_router import get_precise_router

            router = get_precise_router()
            route_result = await router.classify(prompt or intent)
            engine = route_result.engine_id
            logger.info(f"Graph routing: {intent} -> {engine}")
        except Exception as e:
            logger.warning(f"Graph routing failed: {e}")

        # Get symbols from graph
        try:
            from kernel.ghostide.symbol_cypher_router import get_symbol_cypher_router

            cypher = get_symbol_cypher_router()
            symbols_raw = cypher.get_symbols_context(intent, repo_id, limit=10)
            symbols = [{"name": s.name, "path": s.path, "kind": s.kind} for s in symbols_raw]
            files_to_read = [s.path for s in symbols_raw[:5]]

            # Get implicit tasks
            implicit_tasks_list = cypher.get_implicit_tasks(repo_id)
        except Exception as e:
            logger.warning(f"Symbol graph query failed: {e}")
            files_to_read = result.get("files_to_read", [])

        # Build constraints from routing
        constraints = []
        if engine:
            constraints.append(f"engine:{engine}")
        constraints.append(f"intent:{intent}")

        cp = cls(
            cp_id=uuid.uuid4().hex[:12],
            mission=result.get("mission", ""),
            model=engine or "qwen3b_local",
            repo_id=repo_id,
            repo_name=result.get("repo_name", "unknown"),
            branch=result.get("branch", "main"),
            intent=intent,
            files_to_read=files_to_read,
            constraints=constraints,
            implicit_tasks=implicit_tasks_list,
            risk_level=result.get("risk_level", "MEDIUM"),
            symbols_context=symbols,
            human_validated=False,
        )

        # Sync to Neo4j
        try:
            cp._sync_to_graph()
        except Exception as e:
            logger.warning(f"CP graph sync failed: {e}")

        return cp

    def _sync_to_graph(self):
        """Sync CP to Neo4j."""
        try:
            from neo4j import GraphDatabase
            import os

            uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
            user = os.getenv("NEO4J_USER", "neo4j")
            password = os.getenv("NEO4J_PASSWORD", "Leon1234$")

            driver = GraphDatabase.driver(uri, auth=(user, password))

            query = """
            MERGE (cp:ContextPack {cp_id: $cp_id})
            SET cp.mission = $mission,
                cp.model = $model,
                cp.intent = $intent,
                cp.repo_id = $repo_id,
                cp.branch = $branch,
                cp.risk_level = $risk_level,
                cp.human_validated = $human_validated,
                cp.created_at = datetime()
            """

            with driver.session() as session:
                session.run(
                    query,
                    cp_id=self.cp_id,
                    mission=self.mission,
                    model=self.model,
                    intent=self.intent,
                    repo_id=self.repo_id,
                    branch=self.branch,
                    risk_level=self.risk_level,
                    human_validated=self.human_validated,
                )

            driver.close()
            logger.info(f"CP {self.cp_id} synced to Neo4j")

        except Exception as e:
            logger.warning(f"Neo4j sync failed: {e}")

    def approve(self, validated_by: str, notes: str = ""):
        """Approve this CP."""
        self.human_validated = True
        self.validated_by = validated_by
        self.notes = notes

        # Update Neo4j
        try:
            from neo4j import GraphDatabase
            import os

            uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
            user = os.getenv("NEO4J_USER", "neo4j")
            password = os.getenv("NEO4J_PASSWORD", "Leon1234$")

            driver = GraphDatabase.driver(uri, auth=(user, password))

            query = """
            MATCH (cp:ContextPack {cp_id: $cp_id})
            SET cp.human_validated = true,
                cp.validated_by = $validated_by,
                cp.notes = $notes,
                cp.approved_at = datetime()
            """

            with driver.session() as session:
                session.run(query, cp_id=self.cp_id, validated_by=validated_by, notes=notes)

            driver.close()

        except Exception as e:
            logger.warning(f"CP approval sync failed: {e}")

    def to_dict(self) -> dict:
        return {
            "cp_id": self.cp_id,
            "mission": self.mission,
            "model": self.model,
            "repo_id": self.repo_id,
            "repo_name": self.repo_name,
            "branch": self.branch,
            "human_validated": self.human_validated,
            "validated_by": self.validated_by,
            "notes": self.notes,
            "intent": self.intent,
            "files_to_read": self.files_to_read,
            "constraints": self.constraints,
            "implicit_tasks": self.implicit_tasks,
            "risk_level": self.risk_level,
            "is_checkpoint": self.is_checkpoint,
            "engine_node": self.engine_node,
            "symbols_context": self.symbols_context,
        }


async def generate_cp_from_result(result: dict) -> ContextPack:
    """Generate ContextPack from agent result with graph integration."""
    return await ContextPack.from_agent_result(result)
