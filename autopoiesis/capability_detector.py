"""
Capability Detector - Detecta gaps de capacidad en DENIS.

Analiza:
- Errores recurrentes (missing capability)
- Latencias elevadas (cuellos de botella)
- Patrones de uso no cubiertos
- Request explícitos de nuevas features

Genera "capability gaps" que alimentan extension_generator.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import redis


class GapSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class GapCategory(Enum):
    MISSING_TOOL = "missing_tool"
    PERFORMANCE = "performance"
    INTEGRATION = "integration"
    COVERAGE = "coverage"
    QUALITY = "quality"


@dataclass
class CapabilityGap:
    id: str
    category: GapCategory
    severity: GapSeverity
    title: str
    description: str
    evidence: dict[str, Any]
    suggested_approach: str
    estimated_impact: float
    timestamp_utc: str
    status: str = "detected"
    times_detected: int = 1


@dataclass
class GapEvidence:
    source: str
    error_pattern: str | None = None
    latency_ms: float | None = None
    frequency: int = 0
    related_tools: list[str] = field(default_factory=list)
    sample_error: str | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_redis() -> redis.Redis:
    url = "redis://localhost:6379/0"
    try:
        import os

        url = os.getenv("REDIS_URL", url)
        return redis.Redis.from_url(url, decode_responses=True)
    except Exception:
        return redis.Redis.from_url(url, decode_responses=True)


def _emit_event(channel: str, data: dict[str, Any]) -> None:
    try:
        r = _get_redis()
        import json

        r.publish(channel, json.dumps(data, sort_keys=True))
    except Exception:
        pass


def _record_gap(gap: CapabilityGap) -> None:
    try:
        r = _get_redis()
        import json

        key = f"denis:self_extension:gaps:{gap.id}"
        r.setex(
            key,
            86400 * 7,
            json.dumps(
                {
                    "id": gap.id,
                    "category": gap.category.value,
                    "severity": gap.severity.value,
                    "title": gap.title,
                    "description": gap.description,
                    "evidence": gap.evidence,
                    "suggested_approach": gap.suggested_approach,
                    "estimated_impact": gap.estimated_impact,
                    "timestamp_utc": gap.timestamp_utc,
                    "status": gap.status,
                    "times_detected": gap.times_detected,
                },
                sort_keys=True,
            ),
        )
    except Exception:
        pass


def _load_existing_gaps() -> dict[str, dict]:
    try:
        r = _get_redis()
        import json

        pattern = "denis:self_extension:gaps:*"
        gaps = {}
        for key in r.keys(pattern):
            data = r.get(key)
            if data:
                gaps[key.split(":")[-1]] = json.loads(data)
        return gaps
    except Exception:
        return {}


def _generate_gap_id(category: GapCategory, title: str) -> str:
    import hashlib

    content = f"{category.value}:{title}"
    short_hash = hashlib.md5(content.encode()).hexdigest()[:8]
    return f"gap_{category.value}_{short_hash}"


class ErrorPatternAnalyzer:
    """Analiza patrones de error para detectar gaps."""

    KNOWN_PATTERNS = {
        "missing_capability": {
            "patterns": [
                r"unknown capability",
                r"no handler for",
                r"tool not found",
                r"unsupported operation",
            ],
            "category": GapCategory.MISSING_TOOL,
            "severity": GapSeverity.HIGH,
        },
        "timeout": {
            "patterns": [
                r"timeout",
                r"took too long",
                r"deadline exceeded",
            ],
            "category": GapCategory.PERFORMANCE,
            "severity": GapSeverity.MEDIUM,
        },
        "resource_missing": {
            "patterns": [
                r"not found",
                r"does not exist",
                r"resource unavailable",
            ],
            "category": GapCategory.INTEGRATION,
            "severity": GapSeverity.LOW,
        },
        "quality_issue": {
            "patterns": [
                r"poor quality",
                r"incorrect result",
                r"failed assertion",
            ],
            "category": GapCategory.QUALITY,
            "severity": GapSeverity.MEDIUM,
        },
    }

    def analyze_error(self, error: str) -> tuple[str, str] | None:
        for pattern_name, config in self.KNOWN_PATTERNS.items():
            for pattern in config["patterns"]:
                import re

                if re.search(pattern, error.lower()):
                    return pattern_name, config["category"].value
        return None


class CapabilityDetector:
    def __init__(self):
        self.error_analyzer = ErrorPatternAnalyzer()
        self._error_counts: dict[str, int] = {}
        self._latency_buckets: dict[str, list[float]] = {}
        self._gap_frequency_threshold: int = 3

    def detect_from_errors(self, errors: list[dict[str, Any]]) -> list[CapabilityGap]:
        gaps: list[CapabilityGap] = []
        existing_gaps = _load_existing_gaps()

        for error_data in errors:
            error = error_data.get("error", "") or error_data.get("message", "")
            source = error_data.get("source", "unknown")
            timestamp = error_data.get("timestamp", _utc_now())

            result = self.error_analyzer.analyze_error(error)
            if result:
                pattern_name, category_value = result
                category = GapCategory(category_value)
                severity = self.error_analyzer.KNOWN_PATTERNS[pattern_name]["severity"]

                gap_id = _generate_gap_id(category, pattern_name)
                key = f"denis:self_extension:gaps:{gap_id}"

                evidence = {
                    "source": source,
                    "error_pattern": pattern_name,
                    "sample_error": error[:200],
                    "frequency": self._error_counts.get(gap_id, 0) + 1,
                }

                if gap_id in existing_gaps:
                    gap = CapabilityGap(
                        id=gap_id,
                        category=category,
                        severity=severity,
                        title=f"Recurring {pattern_name}",
                        description=f"Pattern '{pattern_name}' detected again",
                        evidence={
                            **existing_gaps[gap_id].get("evidence", {}),
                            **evidence,
                        },
                        suggested_approach=existing_gaps[gap_id].get(
                            "suggested_approach", ""
                        ),
                        estimated_impact=existing_gaps[gap_id].get(
                            "estimated_impact", 0.5
                        ),
                        timestamp_utc=timestamp,
                        status="detected",
                        times_detected=evidence["frequency"],
                    )
                else:
                    gap = CapabilityGap(
                        id=gap_id,
                        category=category,
                        severity=severity,
                        title=f"Missing capability: {pattern_name}",
                        description=f"System lacks capability to handle: {error[:100]}...",
                        evidence=evidence,
                        suggested_approach=self._suggest_approach(pattern_name, error),
                        estimated_impact=self._estimate_impact(
                            severity, evidence["frequency"]
                        ),
                        timestamp_utc=timestamp,
                    )

                self._error_counts[gap_id] = evidence["frequency"]
                gaps.append(gap)

        return gaps

    def detect_from_latency(
        self, operations: list[dict[str, Any]], threshold_ms: float = 500.0
    ) -> list[CapabilityGap]:
        gaps: list[CapabilityGap] = []
        existing_gaps = _load_existing_gaps()

        for op in operations:
            op_name = op.get("operation", op.get("tool", "unknown"))
            latency = op.get("latency_ms", float("inf"))
            frequency = op.get("frequency", 1)

            if latency > threshold_ms:
                gap_id = _generate_gap_id(GapCategory.PERFORMANCE, f"slow_{op_name}")
                evidence = {
                    "operation": op_name,
                    "latency_ms": latency,
                    "frequency": frequency,
                    "threshold_ms": threshold_ms,
                }

                if gap_id in existing_gaps:
                    gap = CapabilityGap(
                        id=gap_id,
                        category=GapCategory.PERFORMANCE,
                        severity=GapSeverity.MEDIUM,
                        title=f"Performance issue: {op_name}",
                        description=f"Operation {op_name} exceeds threshold",
                        evidence={
                            **existing_gaps[gap_id].get("evidence", {}),
                            **evidence,
                        },
                        suggested_approach=existing_gaps[gap_id].get(
                            "suggested_approach", ""
                        ),
                        estimated_impact=existing_gaps[gap_id].get(
                            "estimated_impact", 0.3
                        ),
                        timestamp_utc=_utc_now(),
                        times_detected=evidence["frequency"],
                    )
                else:
                    gap = CapabilityGap(
                        id=gap_id,
                        category=GapCategory.PERFORMANCE,
                        severity=GapSeverity.MEDIUM,
                        title=f"Performance optimization needed: {op_name}",
                        description=f"Operation {op_name} takes {latency}ms (> {threshold_ms}ms threshold)",
                        evidence=evidence,
                        suggested_approach=self._suggest_performance_approach(
                            op_name, latency
                        ),
                        estimated_impact=0.3,
                    )

                gaps.append(gap)

        return gaps

    def detect_from_usage_patterns(
        self, patterns: list[dict[str, Any]]
    ) -> list[CapabilityGap]:
        gaps: list[CapabilityGap] = []

        for pattern in patterns:
            pattern_type = pattern.get("type", "unknown")
            uncovered = pattern.get("uncovered_intents", [])
            frequency = pattern.get("frequency", 1)

            if uncovered and frequency > 2:
                for intent in uncovered:
                    gap_id = _generate_gap_id(
                        GapCategory.COVERAGE, intent.replace(" ", "_")
                    )
                    gap = CapabilityGap(
                        id=gap_id,
                        category=GapCategory.COVERAGE,
                        severity=GapSeverity.LOW
                        if frequency < 5
                        else GapSeverity.MEDIUM,
                        title=f"Intent not covered: {intent}",
                        description=f"User intent '{intent}' has {frequency} occurrences but no handler",
                        evidence={
                            "intent": intent,
                            "frequency": frequency,
                            "pattern_type": pattern_type,
                        },
                        suggested_approach=f"Implement handler for intent: {intent}",
                        estimated_impact=0.2,
                        timestamp_utc=_utc_now(),
                    )
                    gaps.append(gap)

        return gaps

    def detect_all(self) -> list[CapabilityGap]:
        """Detecta gaps de todas las fuentes."""
        gaps: list[CapabilityGap] = []

        try:
            r = _get_redis()
            import json

            recent_errors = r.lrange("denis:metacognitive:errors", -100, -1)
            parsed_errors = []
            for e in recent_errors:
                try:
                    parsed_errors.append(json.loads(e))
                except Exception:
                    pass

            error_gaps = self.detect_from_errors(parsed_errors)
            gaps.extend(error_gaps)

            latency_ops = r.lrange("denis:metacognitive:latencies", -100, -1)
            parsed_ops = []
            for op in latency_ops:
                try:
                    parsed_ops.append(json.loads(op))
                except Exception:
                    pass

            latency_gaps = self.detect_from_latency(parsed_ops)
            gaps.extend(latency_gaps)

            pattern_keys = r.keys("denis:cortex:usage_patterns:*")
            patterns = []
            for key in pattern_keys[:10]:
                data = r.get(key)
                if data:
                    try:
                        patterns.append(json.loads(data))
                    except Exception:
                        pass

            pattern_gaps = self.detect_from_usage_patterns(patterns)
            gaps.extend(pattern_gaps)

            for gap in gaps:
                _record_gap(gap)
                _emit_event(
                    "denis:self_extension:gap_detected",
                    {
                        "gap_id": gap.id,
                        "category": gap.category.value,
                        "severity": gap.severity.value,
                        "title": gap.title,
                    },
                )

        except Exception as e:
            _emit_event(
                "denis:self_extension:detection_error",
                {
                    "error": str(e),
                },
            )

        return gaps

    def get_gaps(self, status: str | None = None) -> list[CapabilityGap]:
        gaps = []
        existing_gaps = _load_existing_gaps()

        for gap_id, data in existing_gaps.items():
            if status and data.get("status") != status:
                continue
            gap = CapabilityGap(
                id=gap_id,
                category=GapCategory(data.get("category", "unknown")),
                severity=GapSeverity(data.get("severity", "medium")),
                title=data.get("title", ""),
                description=data.get("description", ""),
                evidence=data.get("evidence", {}),
                suggested_approach=data.get("suggested_approach", ""),
                estimated_impact=data.get("estimated_impact", 0.5),
                timestamp_utc=data.get("timestamp_utc", ""),
                status=data.get("status", "detected"),
                times_detected=data.get("times_detected", 1),
            )
            gaps.append(gap)

        gaps.sort(key=lambda g: (g.severity.value, -g.times_detected))
        return gaps

    def dismiss_gap(self, gap_id: str) -> bool:
        try:
            r = _get_redis()
            key = f"denis:self_extension:gaps:{gap_id}"
            if r.exists(key):
                r.delete(key)
                return True
            return False
        except Exception:
            return False

    def _suggest_approach(self, pattern_name: str, error: str) -> str:
        suggestions = {
            "missing_capability": "Implement new tool/handler to cover this capability",
            "timeout": "Optimize existing operation or implement caching",
            "resource_missing": "Ensure resource exists or implement fallback",
            "quality_issue": "Add validation or improve existing implementation",
        }
        return suggestions.get(
            pattern_name, "Review and implement appropriate solution"
        )

    def _suggest_performance_approach(self, op_name: str, latency: float) -> str:
        if latency > 2000:
            return f"Major optimization needed for {op_name} (current: {latency}ms)"
        elif latency > 500:
            return f"Optimize {op_name} for better performance"
        else:
            return f"Minor tweak for {op_name}"

    def _estimate_impact(self, severity: GapSeverity, frequency: int) -> float:
        base_impact = {
            GapSeverity.CRITICAL: 1.0,
            GapSeverity.HIGH: 0.8,
            GapSeverity.MEDIUM: 0.5,
            GapSeverity.LLOW: 0.2,
        }.get(severity, 0.5)

        frequency_factor = min(1.0, frequency / 10)
        return round(base_impact * (0.5 + 0.5 * frequency_factor), 2)


def create_detector() -> CapabilityDetector:
    return CapabilityDetector()


if __name__ == "__main__":
    import json

    detector = CapabilityDetector()

    print("=== DETECTING GAPS ===")
    gaps = detector.detect_all()
    print(f"Found {len(gaps)} gaps")

    for gap in gaps[:5]:
        print(
            json.dumps(
                {
                    "id": gap.id,
                    "category": gap.category.value,
                    "severity": gap.severity.value,
                    "title": gap.title,
                    "times_detected": gap.times_detected,
                },
                indent=2,
                sort_keys=True,
            )
        )

    print("\n=== ALL GAPS ===")
    all_gaps = detector.get_gaps()
    print(f"Total: {len(all_gaps)}")
    for gap in all_gaps[:3]:
        print(f"- {gap.id}: {gap.title}")
