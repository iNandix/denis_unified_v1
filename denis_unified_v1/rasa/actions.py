"""Rasa Actions for Denis - Graph-integrated actions.

Actions:
- ActionGetSymbols: Get symbols from Neo4j for context
- ActionSessionContext: Get session context from graph
- ActionProSearch: Search external knowledge via ProSearch
"""

from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class Action:
    """Base action class."""

    def name(self) -> str:
        raise NotImplementedError

    def run(self, dispatcher, tracker, domain) -> List[Dict[str, Any]]:
        raise NotImplementedError


class ActionGetSymbols(Action):
    """Get symbols from Neo4j for current context."""

    def name(self) -> str:
        return "action_get_symbols"

    def run(self, dispatcher, tracker, domain) -> List[Dict[str, Any]]:
        # Get current intent
        intent = tracker.latest_message.get("intent", {}).get("name", "")

        # Query graph
        try:
            from kernel.ghostide.symbol_cypher_router import get_symbol_cypher_router

            router = get_symbol_cypher_router()
            symbols = router.get_symbols_context(intent, limit=10)

            if symbols:
                text = "Símbolos relevantes:\n"
                for s in symbols[:5]:
                    text += f"- {s.name} ({s.kind}) en {s.path}:{s.line}\n"
                return [dispatcher.utter_message(text=text)]
        except Exception as e:
            logger.warning(f"ActionGetSymbols failed: {e}")

        return []


class ActionSessionContext(Action):
    """Get session context from Neo4j."""

    def name(self) -> str:
        return "action_session_context"

    def run(self, dispatcher, tracker, domain) -> List[Dict[str, Any]]:
        # Get session_id from tracker
        session_id = tracker.current_state().get("sender_id", "default")

        try:
            from kernel.ghostide.symbol_cypher_router import get_symbol_cypher_router

            router = get_symbol_cypher_router()

            # Get implicit tasks
            tasks = router.get_implicit_tasks(session_id)

            # Get symbols
            symbols = router.get_symbols_context("implement_feature", session_id)

            text = f"Contexto para sesión {session_id}:\n"
            if tasks:
                text += "Tareas implícitas:\n"
                for t in tasks:
                    text += f"  - {t}\n"
            if symbols:
                text += "Símbolos relevantes:\n"
                for s in symbols[:3]:
                    text += f"  - {s.name}\n"

            return [dispatcher.utter_message(text=text)]
        except Exception as e:
            logger.warning(f"ActionSessionContext failed: {e}")

        return []


class ActionProSearch(Action):
    """Search external knowledge via ProSearch."""

    def name(self) -> str:
        return "action_pro_search"

    def run(self, dispatcher, tracker, domain) -> List[Dict[str, Any]]:
        # Get query from latest message
        message = tracker.latest_message.get("text", "")

        try:
            from denis_unified_v1.search.pro_search import search as pro_search

            hits, _ = pro_search(query=message, limit=5)

            if hits:
                text = "Resultados de búsqueda:\n"
                for hit in hits:
                    text += f"- {hit.title}\n  {hit.snippet_redacted}\n"
                return [dispatcher.utter_message(text=text)]
            else:
                return [dispatcher.utter_message(text="No encontré resultados.")]
        except Exception as e:
            logger.warning(f"ActionProSearch failed: {e}")

        return [dispatcher.utter_message(text="Búsqueda no disponible.")]


# Action registry
RASA_ACTIONS = {
    "action_get_symbols": ActionGetSymbols,
    "action_session_context": ActionSessionContext,
    "action_pro_search": ActionProSearch,
}


def get_action(action_name: str) -> Action:
    """Get action by name."""
    return RASA_ACTIONS.get(action_name, Action())()
