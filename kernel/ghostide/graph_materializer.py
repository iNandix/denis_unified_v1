"""GraphMaterializer — sincroniza estado del sistema a Neo4j."""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class GraphMaterializer:
    """
    Sincroniza eventos de CapacityView a Neo4j.

    Wires:
    - CapacityView.on_update → GraphMaterializer.on_capacity_update
    - seed_engines() al inicio
    - on_capacity_update() en tiempo real
    """

    def __init__(self):
        self._enabled = True

    def on_capacity_update(self, node: str, engines: list[Dict[str, Any]]) -> None:
        """
        Callback para actualizar engines en Neo4j cuando CapacityView reporta.

        Args:
            node: Nombre del nodo (nodo1, nodo2)
            engines: Lista de dicts con {name, vram_used, queue_len, latency, healthy}
        """
        if not self._enabled:
            return

        try:
            from denis_unified_v1.delivery.graph_projection import sync_engine_to_graph

            for engine in engines:
                engine_id = engine.get("name", "")
                if not engine_id:
                    continue

                sync_engine_to_graph(
                    engine_id=engine_id,
                    vram_used_mb=engine.get("vram_used", 0),
                    queue_length=engine.get("queue_len", 0),
                    latency_ms=engine.get("latency", 0),
                    healthy=engine.get("healthy", True),
                    intent=engine.get("role", engine.get("intent", "unknown")),
                )

            logger.debug(f"GraphMaterializer: synced {len(engines)} engines from {node}")

        except Exception as e:
            logger.warning(f"GraphMaterializer.on_capacity_update failed: {e}")

    def seed_initial(self) -> int:
        """Sincroniza engines iniciales desde registry."""
        try:
            from denis_unified_v1.delivery.graph_projection import sync_all_engines_from_registry

            return sync_all_engines_from_registry()
        except Exception as e:
            logger.warning(f"GraphMaterializer.seed_initial failed: {e}")
            return 0

    def disable(self) -> None:
        """Desactiva materialization."""
        self._enabled = False

    def enable(self) -> None:
        """Activa materialization."""
        self._enabled = True


# Instancia global
_materializer: Optional[GraphMaterializer] = None


def get_graph_materializer() -> GraphMaterializer:
    """Get singleton GraphMaterializer instance."""
    global _materializer
    if _materializer is None:
        _materializer = GraphMaterializer()
    return _materializer


def wire_capacity_view(materializer: GraphMaterializer = None) -> GraphMaterializer:
    """
    Wire CapacityView al GraphMaterializer.

    Busca capacity_view en sprint_orchestrator y wirea el callback.
    """
    mat = materializer or get_graph_materializer()

    try:
        # Intentar importar capacity_view
        from denis_unified_v1.sprint_orchestrator.capacity_view import CapacityView

        # Verificar si existe capacidad de callback
        if hasattr(CapacityView, "register_callback"):
            capacity = CapacityView.get_instance()
            capacity.register_callback(mat.on_capacity_update)
            logger.info("GraphMaterializer wired to CapacityView via register_callback")
        elif hasattr(capacity, "on_update"):
            # Callback directo
            capacity.on_update = mat.on_capacity_update
            logger.info("GraphMaterializer wired to CapacityView via on_update")
        else:
            logger.warning("CapacityView no tiene método de callback")

    except ImportError:
        logger.warning("capacity_view no encontrado, skipping wire")
    except Exception as e:
        logger.warning(f"Wire failed: {e}")

    return mat
