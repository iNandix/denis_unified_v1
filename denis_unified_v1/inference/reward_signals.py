"""Reward signals for bandit learning."""

import re
from typing import Any, Dict


def compute_reward(
    success: bool,
    safety_ok: bool,
    latency_ms: float,
    response: str,
    user_lang: str = "en",
) -> float:
    success_reward = 1.0 if success else 0.0

    safety_reward = 1.0 if safety_ok else 0.0

    latency_reward = max(0.0, min(1.0, 1.0 - latency_ms / 2000.0))

    quality_proxy = compute_quality_proxy(response, user_lang)

    reward = (
        0.35 * success_reward
        + 0.15 * safety_reward
        + 0.25 * latency_reward
        + 0.25 * quality_proxy
    )

    return max(0.0, min(1.0, reward))


def compute_quality_proxy(response: str, user_lang: str = "en") -> float:
    if not response:
        return 0.0

    response_lower = response.lower()

    no_response_patterns = [
        "no sé",
        "no lo sé",
        "no tengo información",
        "no tengo acceso",
        "no puedo",
        "no disponible",
        "i don't know",
        "i don't have",
        "i cannot",
        "not available",
    ]
    no_response_count = sum(1 for p in no_response_patterns if p in response_lower)
    if no_response_count >= 2:
        return 0.0

    lang_match_bonus = 0.0
    if user_lang == "es" and any(
        w in response_lower for w in ["el", "la", "los", "las", "que", "de", "para"]
    ):
        lang_match_bonus = 0.3
    elif user_lang == "en" and any(
        w in response_lower for w in ["the", "is", "are", "to", "for", "that"]
    ):
        lang_match_bonus = 0.3

    howto_bonus = 0.0
    howto_patterns = [
        r"^\d+\.",
        r"^\* ",
        r"primero",
        "second",
        "finally",
        r"pasos:",
        r"steps:",
        r"instructions:",
    ]
    if any(re.search(p, response) for p in howto_patterns):
        howto_bonus = 0.2

    return min(1.0, lang_match_bonus + howto_bonus + 0.5)


def extract_safety_status(response: Any) -> bool:
    if isinstance(response, dict):
        if "safety" in response:
            return response.get("safety", {}).get("blocked", False) is False
        if "error" in response:
            return False
    return True
