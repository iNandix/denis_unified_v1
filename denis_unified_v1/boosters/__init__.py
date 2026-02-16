"""Modo Vampiro - Booster Subsystem.

Ephemeral resource boosters for Denis.
"""

from .models import OpportunitySpec, BoosterSpec, Adapter, SelectionResult
from .opportunity_scraper import get_opportunity_scraper
from .booster_catalog import get_booster_catalog
from .broker import get_booster_broker
from .adapter import create_adapter
from .outcome_registry import get_outcome_registry

__all__ = [
    "OpportunitySpec",
    "BoosterSpec", 
    "Adapter",
    "SelectionResult",
    "get_opportunity_scraper",
    "get_booster_catalog",
    "get_booster_broker",
    "create_adapter",
    "get_outcome_registry",
]