"""Opportunity Scraper - Descubre recursos efímeros.

Minimal scraper for ephemeral resources (HF Spaces, promos, etc.).
"""

from __future__ import annotations

import asyncio
import logging
from typing import List

from denis_unified_v1.boosters.models import OpportunitySpec
from denis_unified_v1.kernel.internet_health import get_internet_health

logger = logging.getLogger(__name__)


class OpportunityScraper:
    """Scraper base para recursos efímeros."""

    def __init__(self):
        self.internet = get_internet_health()

    async def discover(self) -> List[OpportunitySpec]:
        """Descubre oportunidades disponibles."""
        if not self.internet.is_internet_ok():
            logger.info("No internet - returning cached opportunities")
            return self._get_cached_opportunities()

        opportunities = []

        # Scrape HF Spaces (mock for now)
        hf_ops = await self._scrape_hf_spaces()
        opportunities.extend(hf_ops)

        # Scrape promo endpoints (mock)
        promo_ops = await self._scrape_promo_endpoints()
        opportunities.extend(promo_ops)

        # Scrape GPU idle (mock)
        gpu_ops = await self._scrape_gpu_idle()
        opportunities.extend(gpu_ops)

        logger.info(f"Discovered {len(opportunities)} opportunities")
        return opportunities

    async def _scrape_hf_spaces(self) -> List[OpportunitySpec]:
        """Mock scrape de HF Spaces."""
        # TODO: Real API call to HF
        return [
            OpportunitySpec(
                id="hf_space_llama_7b",
                type="hf_space",
                endpoint="https://hf.space/gradio/llama-7b-chat",
                capabilities=["inference", "chat"],
                health_score=0.85,
                cost_per_use=0.0,  # Free
                latency_ms=1500,
                expires_at=None,  # Long-lived
                meta={"model": "llama-7b", "owner": "gradio"}
            )
        ]

    async def _scrape_promo_endpoints(self) -> List[OpportunitySpec]:
        """Mock scrape de endpoints en promo."""
        # TODO: Scrape promo sites
        return [
            OpportunitySpec(
                id="promo_gpt_mini",
                type="promo_endpoint",
                endpoint="https://promo.openai.com/gpt-mini",
                capabilities=["inference"],
                health_score=0.7,
                cost_per_use=0.001,
                latency_ms=800,
                expires_at=None,
                meta={"promo_until": "2025-12-31"}
            )
        ]

    async def _scrape_gpu_idle(self) -> List[OpportunitySpec]:
        """Mock scrape de GPUs ociosas."""
        # TODO: Scrape cloud providers for idle GPUs
        return [
            OpportunitySpec(
                id="gpu_idle_a100",
                type="gpu_idle",
                endpoint="https://gpu-provider.com/a100-instance",
                capabilities=["gpu_accel", "inference"],
                health_score=0.9,
                cost_per_use=0.02,
                latency_ms=200,
                expires_at=None,
                meta={"gpu_type": "A100", "idle_hours": 24}
            )
        ]

    def _get_cached_opportunities(self) -> List[OpportunitySpec]:
        """Return cached opportunities for offline."""
        return [
            OpportunitySpec(
                id="cached_local_llm",
                type="local",
                endpoint="http://localhost:8080",
                capabilities=["inference"],
                health_score=0.95,
                cost_per_use=0.0,
                latency_ms=100,
                expires_at=None,
                meta={"cached": True}
            )
        ]


# Global instance
_opportunity_scraper = None

def get_opportunity_scraper() -> OpportunityScraper:
    global _opportunity_scraper
    if _opportunity_scraper is None:
        _opportunity_scraper = OpportunityScraper()
    return _opportunity_scraper