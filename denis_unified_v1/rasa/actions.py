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


class ActionAskDenis(Action):
    """
    Tool de Rasa para consultar a Denis Persona.

    Cuando Rasa necesita una decisión, consulta a Denis.
    Denis = orquestador principal, Rasa = tool.
    """

    def name(self) -> str:
        return "action_ask_denis"

    def run(self, dispatcher, tracker, domain) -> List[Dict[str, Any]]:
        """Consulta a Denis Persona para obtener decisión."""
        import asyncio

        intent = tracker.latest_message.get("intent", {}).get("name", "unknown")
        session_id = tracker.current_state().get("sender_id", "default")

        slots = {}
        for key, value in tracker.slots.items():
            if value:
                slots[key] = value[0] if isinstance(value, list) else value

        try:
            from kernel.denis_persona import get_denis_persona

            denis = get_denis_persona()

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures

                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(
                            asyncio.run, denis.decide(intent, session_id, list(slots.values()))
                        )
                        decision = future.result(timeout=30)
                else:
                    decision = loop.run_until_complete(
                        denis.decide(intent, session_id, list(slots.values()))
                    )
            except Exception as e:
                logger.warning(f"DenisPersona.decide in Rasa failed: {e}")
                return [dispatcher.utter_message(text=f"Denis no puede decidir ahora: {e}")]

            mood_emoji = {"sad": "😢", "neutral": "😐", "confident": "😎"}.get(decision.mood, "😐")

            knowledge_text = ""
            if decision.knowledge:
                knowledge_text = "\nConocimiento relevante:\n"
                for k in decision.knowledge[:3]:
                    knowledge_text += f"  • {k.get('name', 'unknown')}\n"

            text = f"""🤔 Denis ({mood_emoji} {decision.mood.upper()}):
• Engine: {decision.engine}
• Confianza: {decision.confidence:.0%}{knowledge_text}
• Razonamiento: {decision.reasoning}"""

            return [dispatcher.utter_message(text=text)]

        except Exception as e:
            logger.error(f"ActionAskDenis failed: {e}")
            return [dispatcher.utter_message(text="Denis no está disponible.")]


# Action registry
RASA_ACTIONS = {
    "action_get_symbols": ActionGetSymbols,
    "action_session_context": ActionSessionContext,
    "action_pro_search": ActionProSearch,
    "action_ask_denis": ActionAskDenis,
}


def get_action(action_name: str) -> Action:
    """Get action by name."""
    return RASA_ACTIONS.get(action_name, Action())()


class ActionAskDenis(Action):
    """
    Tool de Rasa para consultar a Denis Persona.

    Cuando Rasa necesita una decisión, consulta a Denis.
    Denis = orquestador principal, Rasa = tool.
    """

    def name(self) -> str:
        return "action_ask_denis"

    def run(self, dispatcher, tracker, domain) -> List[Dict[str, Any]]:
        """Consulta a Denis Persona para obtener decisión."""
        import asyncio

        intent = tracker.latest_message.get("intent", {}).get("name", "unknown")
        session_id = tracker.current_state().get("sender_id", "default")

        slots = {}
        for key, value in tracker.slots.items():
            if value:
                slots[key] = value[0] if isinstance(value, list) else value

        try:
            from kernel.denis_persona import get_denis_persona

            denis = get_denis_persona()

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures

                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(
                            asyncio.run, denis.decide(intent, session_id, list(slots.values()))
                        )
                        decision = future.result(timeout=30)
                else:
                    decision = loop.run_until_complete(
                        denis.decide(intent, session_id, list(slots.values()))
                    )
            except Exception as e:
                logger.warning(f"DenisPersona.decide in Rasa failed: {e}")
                return [dispatcher.utter_message(text=f"Denis no puede decidir ahora: {e}")]

            mood_emoji = {"sad": "😢", "neutral": "😐", "confident": "😎"}.get(decision.mood, "😐")

            knowledge_text = ""
            if decision.knowledge:
                knowledge_text = "\nConocimiento relevante:\n"
                for k in decision.knowledge[:3]:
                    knowledge_text += f"  • {k.get('name', 'unknown')}\n"

            text = f"""🤔 Denis ({mood_emoji} {decision.mood.upper()}):
• Engine: {decision.engine}
• Confianza: {decision.confidence:.0%}{knowledge_text}
• Razonamiento: {decision.reasoning}"""

            return [dispatcher.utter_message(text=text)]

        except Exception as e:
            logger.error(f"ActionAskDenis failed: {e}")
            return [dispatcher.utter_message(text="Denis no está disponible.")]
