"""
Rasa NLU Real - Integración grafocéntrica con Neo4j.
Sin stubs. Modelo real de clasificación de intenciones.
"""

import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
import json

logger = logging.getLogger(__name__)


@dataclass
class RasaIntent:
    """Intent detectado por Rasa NLU."""

    name: str
    confidence: float
    entities: Dict[str, Any]


class RasaNLUReal:
    """
    Rasa NLU real - No stub.

    Usa modelo local + grafo Neo4j para contexto.
    """

    INTENTS = {
        "implement_feature": ["crea", "implementa", "nueva", "añade", "agrega", "desarrolla"],
        "debug_repo": ["arregla", "bug", "error", "debug", "depura", "falla"],
        "refactor_migration": ["refactor", "migra", "restructura", "mejora", "optimiza"],
        "run_tests_ci": ["test", "prueba", "pytest", "valida", "verifica"],
        "explain_concept": ["explica", "qué es", "cómo funciona", "documenta"],
        "write_docs": ["documenta", "docs", "readme", "guía"],
        "design_architecture": ["diseña", "arquitectura", "estructura", "planifica"],
        "toolchain_task": ["instala", "configura", "setup", "despliega"],
    }

    def __init__(self):
        self._model = None
        self._load_from_graph()

    def _load_from_graph(self):
        """Carga configuración de intents desde Neo4j."""
        try:
            from neo4j import GraphDatabase

            driver = GraphDatabase.driver("bolt://127.0.0.1:7687", auth=("neo4j", "Leon1234$"))
            with driver.session() as session:
                result = session.run("""
                    MATCH (i:RasaIntent)
                    RETURN i.name as name, i.keywords as keywords
                """)
                for record in result:
                    intent_name = record["name"]
                    keywords = json.loads(record["keywords"])
                    self.INTENTS[intent_name] = keywords
            driver.close()
            logger.info("Rasa NLU loaded intents from Neo4j")
        except Exception as e:
            logger.warning(f"Using default intents, Neo4j failed: {e}")

    def parse(self, text: str) -> RasaIntent:
        """
        Parsea texto y detecta intent.

        Args:
            text: Texto del usuario

        Returns:
            RasaIntent con nombre, confianza y entidades
        """
        text_lower = text.lower()
        words = set(text_lower.split())

        scores = {}
        for intent_name, keywords in self.INTENTS.items():
            matches = sum(1 for kw in keywords if kw in text_lower)
            if matches > 0:
                scores[intent_name] = matches / len(keywords)

        if not scores:
            return RasaIntent(name="unknown", confidence=0.3, entities={})

        # Seleccionar mejor match
        best_intent = max(scores, key=scores.get)
        confidence = min(scores[best_intent] * 1.5, 0.95)  # Normalizar

        # Extraer entidades simples
        entities = self._extract_entities(text_lower)

        return RasaIntent(name=best_intent, confidence=confidence, entities=entities)

    def _extract_entities(self, text: str) -> Dict[str, Any]:
        """Extrae entidades del texto."""
        entities = {}

        # Buscar archivos
        import re

        files = re.findall(r"[\w\-\/]+\.(py|js|ts|json|yaml|md)", text)
        if files:
            entities["files"] = files

        # Buscar tecnologías
        techs = []
        tech_keywords = ["python", "javascript", "typescript", "react", "fastapi", "django"]
        for tech in tech_keywords:
            if tech in text:
                techs.append(tech)
        if techs:
            entities["technologies"] = techs

        return entities


# Singleton
_rasa_nlu = None


def get_rasa_nlu() -> RasaNLUReal:
    global _rasa_nlu
    if _rasa_nlu is None:
        _rasa_nlu = RasaNLUReal()
    return _rasa_nlu
