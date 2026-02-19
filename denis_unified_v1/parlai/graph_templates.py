"""ParLAI Graph Templates - Templates from Neo4j.

Cypher queries:
- get_template_for_intent: MATCH (t:Template)-[:TEMPLATE_FOR{intent}]->(i:Intent)
- seed_templates: Import default templates to Neo4j
"""

import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ParLAITemplate:
    """ParLAI template from graph."""

    name: str
    intent: str
    template: str
    slots: List[str]
    code_stub: str


DEFAULT_TEMPLATES = {
    "implement_feature": {
        "template": "Crear {feature_name} con {tech_stack}",
        "slots": ["feature_name", "tech_stack"],
        "code_stub": "def {feature_name}():\n    pass",
    },
    "debug_repo": {
        "template": "Debuggear {error_msg} en {file_path}",
        "slots": ["error_msg", "file_path"],
        "code_stub": "import pdb; pdb.set_trace()",
    },
    "refactor_migration": {
        "template": "Refactorizar {target} hacia {new_pattern}",
        "slots": ["target", "new_pattern"],
        "code_stub": "# TODO: refactor {target}",
    },
    "run_tests_ci": {
        "template": "Ejecutar tests en {test_suite}",
        "slots": ["test_suite"],
        "code_stub": "pytest {test_suite} -v",
    },
    "design_architecture": {
        "template": "Diseñar arquitectura para {system}",
        "slots": ["system"],
        "code_stub": "# Architecture design for {system}",
    },
}


class ParLAIGraphTemplates:
    """
    ParLAI templates from Neo4j graph.

    Flow:
    1. Query Neo4j for template: MATCH (t:Template)-[:TEMPLATE_FOR]->(i:Intent {name: $intent})
    2. If not found, fallback to DEFAULT_TEMPLATES
    3. Return template with code_stub for fast generation
    """

    def __init__(self):
        self._driver = None

    def _get_driver(self):
        if self._driver is None:
            try:
                from neo4j import GraphDatabase
                import os

                uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
                user = os.getenv("NEO4J_USER", "neo4j")
                password = os.getenv("NEO4J_PASSWORD", "Leon1234$")
                self._driver = GraphDatabase.driver(uri, auth=(user, password))
            except Exception as e:
                logger.warning(f"Neo4j driver failed: {e}")
        return self._driver

    def get_template_for_intent(self, intent: str) -> Optional[ParLAITemplate]:
        """Get template for intent from Neo4j."""
        driver = self._get_driver()
        if not driver:
            return self._get_default_template(intent)

        query = """
        MATCH (t:Template)-[:TEMPLATE_FOR]->(i:Intent {name: $intent})
        RETURN t.name as name, t.template as template, t.slots as slots, t.code_stub as code_stub
        LIMIT 1
        """

        try:
            with driver.session() as session:
                result = session.run(query, intent=intent)
                record = result.single()
                if record:
                    return ParLAITemplate(
                        name=record.get("name", ""),
                        intent=intent,
                        template=record.get("template", ""),
                        slots=record.get("slots", []) or [],
                        code_stub=record.get("code_stub", ""),
                    )
        except Exception as e:
            logger.debug(f"Template query failed: {e}")

        # Fallback
        return self._get_default_template(intent)

    def _get_default_template(self, intent: str) -> Optional[ParLAITemplate]:
        """Get default template."""
        defaults = DEFAULT_TEMPLATES.get(intent)
        if defaults:
            return ParLAITemplate(
                name=f"default_{intent}",
                intent=intent,
                template=defaults["template"],
                slots=defaults["slots"],
                code_stub=defaults["code_stub"],
            )
        return None

    def seed_templates(self) -> int:
        """Seed default templates to Neo4j."""
        driver = self._get_driver()
        if not driver:
            return 0

        seeded = 0
        for intent, data in DEFAULT_TEMPLATES.items():
            query = """
            MERGE (t:Template {name: $name})
            SET t.template = $template, t.slots = $slots, t.code_stub = $code_stub
            WITH t
            MERGE (i:Intent {name: $intent})
            MERGE (t)-[:TEMPLATE_FOR]->(i)
            """
            try:
                with driver.session() as session:
                    session.run(
                        query,
                        name=f"default_{intent}",
                        intent=intent,
                        template=data["template"],
                        slots=data["slots"],
                        code_stub=data["code_stub"],
                    )
                seeded += 1
            except Exception as e:
                logger.warning(f"Seed template failed: {e}")

        logger.info(f"Seeded {seeded} ParLAI templates")
        return seeded

    def generate_code_stub(self, intent: str, **slots) -> str:
        """Generate code stub filling slots."""
        template = self.get_template_for_intent(intent)
        if not template:
            return "# No template available"

        code = template.code_stub
        for key, value in slots.items():
            code = code.replace(f"{{{key}}}", str(value))

        return code


# Singleton
_templates: Optional[ParLAIGraphTemplates] = None


def get_parlai_templates() -> ParLAIGraphTemplates:
    """Get ParLAIGraphTemplates singleton."""
    global _templates
    if _templates is None:
        _templates = ParLAIGraphTemplates()
    return _templates
