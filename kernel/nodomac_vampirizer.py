"""NodoMac Vampirizer - Vampirize free tiers from HF Spaces, LlamaCloud, OpenRouter.

Polls free tiers and syncs to Neo4j as VampireEngine nodes.
"""

import os
import time
import logging
from typing import Dict, Any, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class VampireEngine:
    """Vampire engine from free tier."""

    name: str
    provider: str
    endpoint: str
    best_for: List[str]
    quota_left: int
    latency_avg_ms: int
    healthy: bool


class NodoMacVampirizer:
    """
    Vampirizer for free tiers.

    Sources:
    - HF Spaces: llama-405b, gemma-vision (rate-limit aware)
    - LlamaCloud: vision tier (500 rpd free)
    - OpenRouter free: deepseek-r1 fallback

    Polls and syncs to Neo4j as VampireEngine nodes.
    """

    def __init__(self):
        self._driver = None

    def _get_driver(self):
        if self._driver is None:
            try:
                from neo4j import GraphDatabase

                uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
                user = os.getenv("NEO4J_USER", "neo4j")
                password = os.getenv("NEO4J_PASSWORD", "Leon1234$")
                self._driver = GraphDatabase.driver(uri, auth=(user, password))
            except Exception as e:
                logger.warning(f"Neo4j driver failed: {e}")
        return self._driver

    def poll(self) -> List[VampireEngine]:
        """
        Poll free tiers and return vampire engines.

        Sources:
        1. HF Spaces (mock - real would need API keys)
        2. LlamaCloud (mock)
        3. OpenRouter free (mock)
        """
        vampires = []

        # HF Spaces - mock (real would check actual endpoints)
        vampires.extend(
            [
                VampireEngine(
                    name="llama-405b-hf",
                    provider="huggingface_spaces",
                    endpoint="https://meta-llama-llama-4-405b.hf.space",
                    best_for=["reasoning", "code", "vision"],
                    quota_left=450,  # Estimated remaining
                    latency_avg_ms=8000,
                    healthy=True,
                ),
                VampireEngine(
                    name="gemma-vision-hf",
                    provider="huggingface_spaces",
                    endpoint="https://gemma-3b-vision.hf.space",
                    best_for=["vision", "image_analysis"],
                    quota_left=480,
                    latency_avg_ms=5000,
                    healthy=True,
                ),
            ]
        )

        # LlamaCloud
        vampires.append(
            VampireEngine(
                name="vision-llamacloud",
                provider="llamacloud",
                endpoint="https://cloud.llamaindex.ai/api/v1/chat",
                best_for=["vision", "document_analysis"],
                quota_left=500,  # 500 rpd free
                latency_avg_ms=3000,
                healthy=True,
            )
        )

        # OpenRouter free tier
        vampires.append(
            VampireEngine(
                name="deepseek-r1-openrouter",
                provider="openrouter_free",
                endpoint="https://openrouter.ai/api/v1/chat/completions",
                best_for=["reasoning", "code"],
                quota_left=1000,  # Varies
                latency_avg_ms=4000,
                healthy=True,
            )
        )

        # Sync to Neo4j
        self._sync_to_graph(vampires)

        return vampires

    def _sync_to_graph(self, vampires: List[VampireEngine]):
        """Sync vampire engines to Neo4j."""
        driver = self._get_driver()
        if not driver:
            return

        for v in vampires:
            query = """
            MERGE (ve:VampireEngine {name: $name})
            SET ve.provider = $provider,
                ve.endpoint = $endpoint,
                ve.best_for = $best_for,
                ve.quota_left = $quota_left,
                ve.latency_avg_ms = $latency,
                ve.healthy = $healthy,
                ve.node = 'nodomac',
                ve.last_poll = datetime()
            """
            try:
                with driver.session() as session:
                    session.run(
                        query,
                        name=v.name,
                        provider=v.provider,
                        endpoint=v.endpoint,
                        best_for=v.best_for,
                        quota_left=v.quota_left,
                        latency=v.latency_avg_ms,
                        healthy=v.healthy,
                    )
            except Exception as e:
                logger.warning(f"Failed to sync {v.name}: {e}")

        logger.info(f"Synced {len(vampires)} vampire engines to Neo4j")

    def poll_loop(self, interval_seconds: int = 60):
        """Poll loop for daemon."""
        logger.info(f"Starting vampire poll loop (interval={interval_seconds}s)")
        while True:
            try:
                self.poll()
            except Exception as e:
                logger.warning(f"Poll failed: {e}")
            time.sleep(interval_seconds)


# Singleton
_vampirizer = None


def get_nodomac_vampirizer() -> NodoMacVampirizer:
    """Get NodoMacVampirizer singleton."""
    global _vampirizer
    if _vampirizer is None:
        _vampirizer = NodoMacVampirizer()
    return _vampirizer
