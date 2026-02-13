"""Policy: Contextual Bandit with Thompson Sampling."""

import json
import math
import random
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Any
import os

try:
    import redis
except ImportError:
    redis = None


@dataclass
class EngineStats:
    a: float = 1.0
    b: float = 1.0
    ema_latency: float = 500.0
    ema_quality: float = 0.5
    last_seen: float = field(default_factory=time.time)


class PolicyBandit:
    def __init__(self):
        self.redis_client = None
        self._init_redis()

        self.weights = {
            "wQ": 0.35,
            "wS": 0.35,
            "wL": 0.20,
            "wC": 0.05,
            "wR": 0.05,
        }

    def _init_redis(self):
        if redis is None:
            return
        try:
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            self.redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
        except Exception:
            pass

    def _get_key(self, class_key: str, engine_id: str) -> str:
        return f"denis:phase7:bandit:{class_key}:{engine_id}"

    def get_stats(self, class_key: str, engine_id: str) -> EngineStats:
        if self.redis_client:
            try:
                data = self.redis_client.get(self._get_key(class_key, engine_id))
                if data:
                    d = json.loads(data)
                    return EngineStats(
                        a=d.get("a", 1.0),
                        b=d.get("b", 1.0),
                        ema_latency=d.get("ema_latency", 500.0),
                        ema_quality=d.get("ema_quality", 0.5),
                        last_seen=d.get("last_seen", time.time()),
                    )
            except Exception:
                pass
        return EngineStats()

    def save_stats(self, class_key: str, engine_id: str, stats: EngineStats):
        if self.redis_client:
            try:
                self.redis_client.setex(
                    self._get_key(class_key, engine_id),
                    86400 * 7,
                    json.dumps(
                        {
                            "a": stats.a,
                            "b": stats.b,
                            "ema_latency": stats.ema_latency,
                            "ema_quality": stats.ema_quality,
                            "last_seen": stats.last_seen,
                        }
                    ),
                )
            except Exception:
                pass

    def sample_beta(self, a: float, b: float) -> float:
        u1 = random.random()
        u2 = random.random()
        if u1 == 0:
            u1 = 1e-10
        return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)

    def expected_success(self, a: float, b: float) -> float:
        return a / (a + b) if (a + b) > 0 else 0.5

    def norm_latency(self, latency_ms: float) -> float:
        return min(2.0, latency_ms / 800.0)

    def norm_cost(self, cost: float) -> float:
        return min(2.0, cost / 0.002)

    def utility(
        self,
        class_key: str,
        engine_id: str,
        engine_spec: Any,
        features: Any,
    ) -> float:
        stats = self.get_stats(class_key, engine_id)

        e_success = self.expected_success(stats.a, stats.b)

        norm_lat = self.norm_latency(stats.ema_latency)
        norm_cost = self.norm_cost(engine_spec.cost)

        safety_penalty = 0.0
        if features.safety_risk_hint:
            if engine_spec.safety_level == "low":
                safety_penalty = 0.5
            elif engine_spec.safety_level == "medium":
                safety_penalty = 0.2

        u = (
            self.weights["wQ"] * stats.ema_quality
            + self.weights["wS"] * e_success
            - self.weights["wL"] * norm_lat
            - self.weights["wC"] * norm_cost
            - self.weights["wR"] * safety_penalty
        )
        return max(0.0, u)

    def choose(
        self,
        class_key: str,
        candidates: list,
        features: Any,
    ) -> tuple[Optional[str], Dict[str, float]]:
        if not candidates:
            return None, {}

        scores = {}
        for engine_id, engine_spec in candidates:
            scores[engine_id] = self.utility(
                class_key, engine_id, engine_spec, features
            )

        best_engine = max(scores, key=scores.get)
        return best_engine, scores

    def update(
        self,
        class_key: str,
        engine_id: str,
        reward: float,
        latency_ms: float,
        success: bool,
    ):
        stats = self.get_stats(class_key, engine_id)

        stats.a += reward
        stats.b += 1.0 - reward

        alpha = 0.1
        stats.ema_latency = (1 - alpha) * stats.ema_latency + alpha * latency_ms
        stats.ema_quality = (1 - alpha) * stats.ema_quality + alpha * reward
        stats.last_seen = time.time()

        self.save_stats(class_key, engine_id, stats)


def get_policy_bandit() -> PolicyBandit:
    return PolicyBandit()
