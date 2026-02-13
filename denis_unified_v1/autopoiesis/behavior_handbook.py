"""
Behavior Handbook - Extrae y almacena patrones de comportamiento de DENIS.

Analiza:
- Código existente para extraer patrones de estilo
- Decisiones de routing exitosas
- Extensiones que funcionaron bien
- Errores y sus soluciones

Almacena patrones en Redis para reutilización.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import hashlib
import json
import os
import re

import redis


@dataclass
class BehaviorPattern:
    """Patrón de comportamiento extraído."""

    id: str
    name: str
    category: str
    pattern_type: str
    source: str
    code_snippet: str
    success_rate: float
    times_used: int
    context_patterns: list[str]
    outcome_patterns: list[str]
    timestamp_utc: str


@dataclass
class StyleGuide:
    """Guía de estilo extraída del código existente."""

    class_prefix: str = ""
    function_style: str = "snake_case"
    variable_style: str = "snake_case"
    docstring_format: str = "google"
    import_order: list[str] = field(
        default_factory=lambda: [
            "from __future__ import annotations",
            "from typing import Any",
            "import",
            "from",
        ]
    )
    error_handling_pattern: str = "try_except"
    async_pattern: bool = True


@dataclass
class HandBookEntry:
    """Entrada del handbook."""

    pattern: BehaviorPattern | None = None
    style_guide: StyleGuide | None = None
    template: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


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
        r.publish(channel, json.dumps(data, sort_keys=True))
    except Exception:
        pass


def _compute_checksum(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


class StyleExtractor:
    """Extrae guías de estilo del código existente."""

    CODE_PATHS = [
        "/media/jotah/SSD_denis/core",
        "/media/jotah/SSD_denis/home_jotah/denis_unified_v1",
    ]

    def extract_from_files(self) -> StyleGuide:
        """Analiza archivos para extraer estilo."""
        class_prefix = ""
        import_order = []
        has_async = False

        for code_path in self.CODE_PATHS:
            if not os.path.exists(code_path):
                continue

            for root, _, files in os.walk(code_path):
                for file in files:
                    if not file.endswith(".py"):
                        continue

                    file_path = os.path.join(root, file)
                    try:
                        content = open(file_path).read()
                        if "class " in content:
                            match = re.search(r"class ([A-Z][a-zA-Z0-9_]+)", content)
                            if match:
                                class_prefix = match.group(1)[:3]

                        if "async def" in content or "await " in content:
                            has_async = True

                        imports = re.findall(
                            r"^(?:from|import)\s+[\w.]+", content, re.MULTILINE
                        )
                        if imports:
                            for imp in imports[:10]:
                                if imp.strip() not in import_order:
                                    import_order.append(imp.strip())
                    except Exception:
                        continue

        return StyleGuide(
            class_prefix=class_prefix or "Denis",
            function_style="snake_case",
            variable_style="snake_case",
            docstring_format="google",
            import_order=import_order[:15],
            error_handling_pattern="try_except",
            async_pattern=has_async,
        )


class PatternExtractor:
    """Extrae patrones de código existente."""

    CODE_PATHS = [
        "/media/jotah/SSD_denis/core",
        "/media/jotah/SSD_denis/home_jotah/denis_unified_v1",
    ]

    def _extract_snippet(self, content: str, start: int, max_length: int = 200) -> str:
        lines = content[start:].split("\n")
        snippet = []
        for line in lines:
            if line.strip().startswith(("def ", "class ", "@", "if __name__")):
                snippet.append(line)
            if len(snippet) >= 5:
                break
        return "\n".join(snippet)[:max_length]

    def _extract_patterns_from_file(self, file_path: str) -> list[BehaviorPattern]:
        patterns = []
        try:
            content = open(file_path).read()
            file_name = os.path.basename(file_path)

            if "async def" in content:
                patterns.append(
                    BehaviorPattern(
                        id=f"pat_async_{_compute_checksum(content[:100])}",
                        name=f"Async pattern in {file_name}",
                        category="async",
                        pattern_type="async_function",
                        source=file_path,
                        code_snippet=self._extract_snippet(
                            content, content.find("async def")
                        ),
                        success_rate=0.95,
                        times_used=1,
                        context_patterns=["async", "await"],
                        outcome_patterns=["await"],
                        timestamp_utc=_utc_now(),
                    )
                )

            if "try:" in content and "except" in content:
                patterns.append(
                    BehaviorPattern(
                        id=f"pat_error_{_compute_checksum(content[:100])}",
                        name=f"Error handling in {file_name}",
                        category="error_handling",
                        pattern_type="try_except",
                        source=file_path,
                        code_snippet=self._extract_snippet(
                            content, content.find("try:")
                        ),
                        success_rate=0.9,
                        times_used=1,
                        context_patterns=["error", "exception"],
                        outcome_patterns=["error", "return"],
                        timestamp_utc=_utc_now(),
                    )
                )

            if "redis.Redis" in content or "redis.from_url" in content:
                patterns.append(
                    BehaviorPattern(
                        id=f"pat_redis_{_compute_checksum(content[:100])}",
                        name=f"Redis pattern in {file_name}",
                        category="integration",
                        pattern_type="redis_client",
                        source=file_path,
                        code_snippet=self._extract_snippet(
                            content, content.find("redis")
                        ),
                        success_rate=0.98,
                        times_used=1,
                        context_patterns=["cache", "metrics", "events"],
                        outcome_patterns=["set", "get"],
                        timestamp_utc=_utc_now(),
                    )
                )

            if "GraphDatabase" in content or "neo4j" in content.lower():
                patterns.append(
                    BehaviorPattern(
                        id=f"pat_neo4j_{_compute_checksum(content[:100])}",
                        name=f"Neo4j pattern in {file_name}",
                        category="integration",
                        pattern_type="neo4j_driver",
                        source=file_path,
                        code_snippet=self._extract_snippet(
                            content, content.find("GraphDatabase")
                        ),
                        success_rate=0.95,
                        times_used=1,
                        context_patterns=["graph", "database"],
                        outcome_patterns=["session", "run"],
                        timestamp_utc=_utc_now(),
                    )
                )

            if "dataclass" in content:
                patterns.append(
                    BehaviorPattern(
                        id=f"pat_dataclass_{_compute_checksum(content[:100])}",
                        name=f"Dataclass pattern in {file_name}",
                        category="structure",
                        pattern_type="dataclass",
                        source=file_path,
                        code_snippet=self._extract_snippet(
                            content, content.find("dataclass")
                        ),
                        success_rate=0.98,
                        times_used=1,
                        context_patterns=["data", "configuration"],
                        outcome_patterns=["@dataclass"],
                        timestamp_utc=_utc_now(),
                    )
                )

            if "feature_flags" in content or "load_feature_flags" in content:
                patterns.append(
                    BehaviorPattern(
                        id=f"pat_flags_{_compute_checksum(content[:100])}",
                        name=f"Feature flags pattern in {file_name}",
                        category="configuration",
                        pattern_type="feature_flag",
                        source=file_path,
                        code_snippet=self._extract_snippet(
                            content, content.find("feature_flags")
                        ),
                        success_rate=1.0,
                        times_used=1,
                        context_patterns=["feature", "flag", "config"],
                        outcome_patterns=["True", "False"],
                        timestamp_utc=_utc_now(),
                    )
                )

        except Exception:
            pass

        return patterns

    def extract_all_patterns(self) -> list[BehaviorPattern]:
        """Extrae todos los patrones del código existente."""
        all_patterns = []

        for code_path in self.CODE_PATHS:
            if not os.path.exists(code_path):
                continue

            for root, _, files in os.walk(code_path):
                for file in files:
                    if not file.endswith(".py"):
                        continue

                    file_path = os.path.join(root, file)
                    patterns = self._extract_patterns_from_file(file_path)
                    all_patterns.extend(patterns)

        return all_patterns


class BehaviorHandbook:
    """Behavior Handbook principal."""

    def __init__(self):
        self.style_extractor = StyleExtractor()
        self.pattern_extractor = PatternExtractor()
        self._patterns_cache: list[BehaviorPattern] | None = None

    def _save_to_redis(self, entry: HandBookEntry) -> None:
        try:
            r = _get_redis()
            handbook_key = "denis:self_extension:behavior_handbook"

            existing = {}
            data = r.get(handbook_key)
            if data:
                existing = json.loads(data)

            if entry.pattern:
                existing["patterns"] = existing.get("patterns", [])
                existing["patterns"].append(
                    {
                        "id": entry.pattern.id,
                        "name": entry.pattern.name,
                        "category": entry.pattern.category,
                        "pattern_type": entry.pattern.pattern_type,
                        "source": entry.pattern.source,
                        "success_rate": entry.pattern.success_rate,
                        "times_used": entry.pattern.times_used,
                    }
                )

            if entry.style_guide:
                existing["styles"] = {
                    "class_prefix": entry.style_guide.class_prefix,
                    "function_style": entry.style_guide.function_style,
                    "variable_style": entry.style_guide.variable_style,
                    "docstring_format": entry.style_guide.docstring_format,
                    "import_order": entry.style_guide.import_order,
                    "error_handling_pattern": entry.style_guide.error_handling_pattern,
                    "async_pattern": entry.style_guide.async_pattern,
                }

            r.setex(handbook_key, 86400 * 7, json.dumps(existing, sort_keys=True))
        except Exception:
            pass

    def build(self) -> HandBookEntry:
        """Construye el handbook desde cero."""
        style_guide = self.style_extractor.extract_from_files()
        patterns = self.pattern_extractor.extract_all_patterns()

        entry = HandBookEntry(
            pattern=None,
            style_guide=style_guide,
            template=None,
            metadata={"patterns_count": len(patterns)},
        )

        if patterns:
            entry.pattern = BehaviorPattern(
                id=f"pat_batch_{_utc_now()[:10]}",
                name="Extracted patterns batch",
                category="all",
                pattern_type="batch",
                source="auto_extraction",
                code_snippet="",
                success_rate=0.95,
                times_used=len(patterns),
                context_patterns=[],
                outcome_patterns=[],
                timestamp_utc=_utc_now(),
            )

        self._save_to_redis(entry)

        _emit_event(
            "denis:self_extension:handbook_built",
            {
                "patterns_count": len(patterns),
                "has_style_guide": True,
            },
        )

        return entry

    def add_pattern(self, pattern: BehaviorPattern) -> None:
        """Añade un patrón al handbook."""
        entry = HandBookEntry(pattern=pattern)
        self._save_to_redis(entry)
        self._patterns_cache = None

    def add_success_story(
        self,
        name: str,
        category: str,
        code: str,
        context: list[str],
        outcome: list[str],
    ) -> None:
        """Añade una historia de éxito (extensión que funcionó)."""
        pattern = BehaviorPattern(
            id=f"pat_success_{_compute_checksum(code[:100])}",
            name=name,
            category=category,
            pattern_type="success_story",
            source="runtime",
            code_snippet=code[:200],
            success_rate=1.0,
            times_used=1,
            context_patterns=context,
            outcome_patterns=outcome,
            timestamp_utc=_utc_now(),
        )
        self.add_pattern(pattern)

    def add_failure_pattern(
        self,
        name: str,
        category: str,
        code: str,
        context: list[str],
        lesson: str,
    ) -> None:
        """Añade un patrón de fallo (para evitar repetir)."""
        pattern = BehaviorPattern(
            id=f"pat_failure_{_compute_checksum(code[:100])}",
            name=name,
            category=category,
            pattern_type="failure_lesson",
            source="runtime",
            code_snippet=code[:200],
            success_rate=0.0,
            times_used=1,
            context_patterns=context,
            outcome_patterns=[lesson],
            timestamp_utc=_utc_now(),
        )
        self.add_pattern(pattern)

    def get_style_guide(self) -> StyleGuide:
        """Obtiene la guía de estilo."""
        handbook = self.load()
        if handbook and handbook.style_guide:
            return handbook.style_guide

        return StyleExtractor().extract_from_files()

    def get_patterns(
        self, category: str | None = None, min_success: float = 0.0
    ) -> list[BehaviorPattern]:
        """Obtiene patrones filtrados."""
        handbook = self.load()
        patterns = []

        if handbook and handbook.pattern:
            patterns = [handbook.pattern]

        all_patterns = self._get_all_patterns_from_redis()
        patterns.extend(all_patterns)

        if category:
            patterns = [p for p in patterns if p.category == category]

        if min_success > 0:
            patterns = [p for p in patterns if p.success_rate >= min_success]

        return sorted(patterns, key=lambda p: (-p.success_rate, -p.times_used))

    def _get_all_patterns_from_redis(self) -> list[BehaviorPattern]:
        patterns = []
        try:
            r = _get_redis()
            handbook_key = "denis:self_extension:behavior_handbook"
            data = r.get(handbook_key)
            if data:
                handbook = json.loads(data)
                for p in handbook.get("patterns", []):
                    patterns.append(
                        BehaviorPattern(
                            id=p["id"],
                            name=p["name"],
                            category=p["category"],
                            pattern_type=p["pattern_type"],
                            source=p["source"],
                            code_snippet="",
                            success_rate=p["success_rate"],
                            times_used=p["times_used"],
                            context_patterns=[],
                            outcome_patterns=[],
                            timestamp_utc=_utc_now(),
                        )
                    )
        except Exception:
            pass
        return patterns

    def load(self) -> HandBookEntry | None:
        """Carga el handbook desde Redis."""
        try:
            r = _get_redis()
            handbook_key = "denis:self_extension:behavior_handbook"
            data = r.get(handbook_key)
            if data:
                handbook = json.loads(data)
                style_data = handbook.get("styles", {})

                style_guide = StyleGuide(
                    class_prefix=style_data.get("class_prefix", ""),
                    function_style=style_data.get("function_style", "snake_case"),
                    variable_style=style_data.get("variable_style", "snake_case"),
                    docstring_format=style_data.get("docstring_format", "google"),
                    import_order=style_data.get("import_order", []),
                    error_handling_pattern=style_data.get(
                        "error_handling_pattern", "try_except"
                    ),
                    async_pattern=style_data.get("async_pattern", True),
                )

                return HandBookEntry(
                    style_guide=style_guide,
                    metadata={"patterns_count": len(handbook.get("patterns", []))},
                )
        except Exception:
            pass
        return None

    def get_stats(self) -> dict[str, Any]:
        """Obtiene estadísticas del handbook."""
        handbook = self.load()
        patterns = self.get_patterns()

        return {
            "handbook_exists": handbook is not None,
            "patterns_total": len(patterns),
            "patterns_by_category": self._count_by_category(patterns),
            "avg_success_rate": self._avg_success_rate(patterns),
        }

    def _count_by_category(self, patterns: list[BehaviorPattern]) -> dict[str, int]:
        counts = {}
        for p in patterns:
            counts[p.category] = counts.get(p.category, 0) + 1
        return counts

    def _avg_success_rate(self, patterns: list[BehaviorPattern]) -> float:
        if not patterns:
            return 0.0
        return sum(p.success_rate for p in patterns) / len(patterns)


def create_handbook() -> BehaviorHandbook:
    return BehaviorHandbook()


if __name__ == "__main__":
    import json

    handbook = BehaviorHandbook()

    print("=== BUILDING HANDBOOK ===")
    entry = handbook.build()
    print(f"Built handbook with {entry.metadata.get('patterns_count', 0)} patterns")
    print(f"Style guide: {entry.style_guide.class_prefix}")

    print("\n=== STATS ===")
    stats = handbook.get_stats()
    print(json.dumps(stats, indent=2))

    print("\n=== PATTERNS ===")
    patterns = handbook.get_patterns()
    for p in patterns[:5]:
        print(f"- {p.name} ({p.category}): {p.success_rate:.0%}")
