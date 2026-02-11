"""
Extension Generator - Genera código para auto-extensiones de DENIS.

Usa templates y Behavior Handbook para generar código coherente
con el estilo existente del codebase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import os
from typing import Any

import redis


class ExtensionType(Enum):
    NEW_TOOL = "new_tool"
    NEW_ADAPTER = "new_adapter"
    NEW_MEMORY_PROCESSOR = "new_memory_processor"
    NEW_INTEGRATION = "new_integration"
    NEW_ENDPOINT = "new_endpoint"


@dataclass
class GeneratedExtension:
    id: str
    type: ExtensionType
    name: str
    description: str
    code: str
    imports: list[str]
    dependencies: list[str]
    test_code: str
    doc_code: str
    checksum: str
    quality_score: float
    timestamp_utc: str
    gap_id: str | None = None


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


def _load_behavior_handbook() -> dict[str, Any]:
    try:
        r = _get_redis()
        data = r.get("denis:self_extension:behavior_handbook")
        if data:
            return json.loads(data)
    except Exception:
        pass
    return {"patterns": [], "templates": [], "styles": {}}


class ToolTemplates:
    """Templates para nuevos tools."""

    @staticmethod
    def basic_tool(name: str, class_name: str, description: str) -> str:
        return f'''\"\"\"
{name}: {description}
\"\"\"

from __future__ import annotations

from typing import Any
import logging

logger = logging.getLogger(__name__)


class {class_name}:
    \"\"\"{description}\"\"\"

    def __init__(self):
        self.name = "{name}"

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        \"\"\"
        Execute the {name} operation.
        \"\"\"
        try:
            return {{
                "status": "success",
                "tool": self.name,
                "output": input_data,
            }}
        except Exception as e:
            logger.error(f"{{self.name}} failed: {{e}}")
            return {{
                "status": "error",
                "tool": self.name,
                "error": str(e),
            }}
'''

    @staticmethod
    def cortex_adapter(name: str, class_name: str, description: str) -> str:
        return f'''\"\"\"
{name}: {description}
\"\"\"

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import redis


@dataclass
class {class_name}Config:
    redis_url: str = "redis://localhost:6379/0"
    ttl_seconds: int = 3600


class {class_name}:
    \"\"\"{description}\"\"\"

    def __init__(self, config: {class_name}Config | None = None):
        self.config = config or {class_name}Config()
        self._redis = None

    def _get_redis(self) -> redis.Redis:
        if self._redis is None:
            self._redis = redis.Redis.from_url(
                self.config.redis_url, decode_responses=True
            )
        return self._redis

    def perceive(self) -> dict[str, Any]:
        try:
            return {{
                "status": "success",
                "source": "{name}",
                "data": {{}},
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            }}
        except Exception as e:
            return {{
                "status": "error",
                "source": "{name}",
                "error": str(e),
            }}

    def act(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            return {{
                "status": "success",
                "action": action,
                "result": params,
            }}
        except Exception as e:
            return {{
                "status": "error",
                "action": action,
                "error": str(e),
            }}
'''


class MemoryProcessorTemplates:
    """Templates para processors de memoria."""

    @staticmethod
    def memory_augment(name: str, class_name: str, description: str) -> str:
        return f"""\"\"\"
{name}: {description}
\"\"\"

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from neo4j import GraphDatabase


@dataclass
class {class_name}Config:
    uri: str = "bolt://10.10.10.1:7687"
    user: str = "neo4j"
    password: str = ""


class {class_name}:
    \"\"\"{description}\"\"\"

    def __init__(self, config: {class_name}Config | None = None):
        self.config = config or {class_name}Config()
        self._driver = None

    def _get_driver(self):
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                self.config.uri,
                auth=(self.config.user, self.config.password)
            )
        return self._driver

    def augment_node(self, node_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        try:
            with self._get_driver().session() as session:
                result = session.run("\"\"
                    MATCH (n)
                    WHERE n.node_id = $node_id OR id(n) = toInteger($node_id)
                    SET n += $properties, n.updated_at = datetime()
                    RETURN n
                \"\"\", node_id=node_id, properties=properties)
                return {{
                    "status": "success",
                    "node_id": node_id,
                    "properties_added": list(properties.keys()),
                }}
        except Exception as e:
            return {{
                "status": "error",
                "node_id": node_id,
                "error": str(e),
            }}

    def query(self, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            with self._get_driver().session() as session:
                result = session.run(query, params)
                return [dict(r) for r in result]
        except Exception as e:
            return [{{"error": str(e)}}]
"""


class ExtensionGenerator:
    """Generador de extensiones basado en templates y handbook."""

    def __init__(self):
        self._templates_used: list[str] = []
        self._extensions_generated: int = 0

    def _load_handbook_patterns(self) -> dict[str, Any]:
        return _load_behavior_handbook()

    def _extract_naming_style(self, handbook: dict[str, Any]) -> dict[str, str]:
        styles = handbook.get("styles", {})
        return {
            "class_prefix": styles.get("class_prefix", ""),
            "function_style": styles.get("function_style", "snake_case"),
            "variable_style": styles.get("variable_style", "snake_case"),
        }

    def _generate_class_name(self, name: str, style: dict[str, str]) -> str:
        words = name.replace("-", " ").replace("_", " ").split()
        class_words = [w.capitalize() for w in words]
        return style.get("class_prefix", "") + "".join(class_words)

    def _generate_file_name(self, name: str) -> str:
        return name.replace(" ", "_").lower() + ".py"

    def _generate_test(self, class_name: str, name: str) -> str:
        file_name = name.replace(" ", "_").lower()
        return f'''\"\"\"
Tests for {name}
\"\"\"

import pytest
from {file_name} import {class_name}


class Test{class_name}:
    def setup_method(self):
        self.processor = {class_name}()

    def test_initialization(self):
        assert self.processor.name == "{name}"

    def test_execute_success(self):
        result = self.processor.execute({{"test": True}})
        assert result["status"] == "success"
'''

    def _generate_doc(self, name: str, description: str, class_name: str) -> str:
        file_name = name.replace(" ", "_").lower()
        return f"""# {name}

{description}

## Usage

```python
from {file_name} import {class_name}

processor = {class_name}()
result = processor.execute({{"input": "data"}})
```
"""

    def _calculate_quality(self, code: str, handbook: dict[str, Any]) -> float:
        score = 0.5
        patterns = handbook.get("patterns", [])
        for pattern in patterns:
            if pattern.get("name") in code:
                score += 0.1
        if "from __future__ import annotations" in code:
            score += 0.1
        if "logger" in code.lower():
            score += 0.1
        if "try:" in code and "except" in code:
            score += 0.1
        if "async" in code:
            score += 0.1
        return min(1.0, score)

    def generate_tool(
        self,
        name: str,
        description: str,
        gap_id: str | None = None,
    ) -> GeneratedExtension:
        handbook = self._load_handbook_patterns()
        style = self._extract_naming_style(handbook)
        class_name = self._generate_class_name(name, style)
        code = ToolTemplates.basic_tool(name, class_name, description)
        imports = ["from __future__ import annotations", "from typing import Any"]
        test_code = self._generate_test(class_name, name)
        doc_code = self._generate_doc(name, description, class_name)

        extension = GeneratedExtension(
            id=f"ext_{name}_{_utc_now()[:10]}",
            type=ExtensionType.NEW_TOOL,
            name=name,
            description=description,
            code=code,
            imports=imports,
            dependencies=[],
            test_code=test_code,
            doc_code=doc_code,
            checksum=_compute_checksum(code),
            quality_score=self._calculate_quality(code, handbook),
            timestamp_utc=_utc_now(),
            gap_id=gap_id,
        )

        self._templates_used.append(ExtensionType.NEW_TOOL.value)
        self._extensions_generated += 1

        _emit_event(
            "denis:self_extension:extension_generated",
            {
                "extension_id": extension.id,
                "type": extension.type.value,
                "name": extension.name,
                "quality_score": extension.quality_score,
            },
        )

        return extension

    def generate_memory_processor(
        self,
        name: str,
        description: str,
        processor_type: str = "augment",
        gap_id: str | None = None,
    ) -> GeneratedExtension:
        handbook = self._load_handbook_patterns()
        style = self._extract_naming_style(handbook)
        class_name = self._generate_class_name(name, style)
        code = MemoryProcessorTemplates.memory_augment(name, class_name, description)
        imports = ["from __future__ import annotations", "from typing", "from neo4j"]
        test_code = self._generate_test(class_name, name)
        doc_code = self._generate_doc(name, description, class_name)

        extension = GeneratedExtension(
            id=f"ext_mem_{name}_{_utc_now()[:10]}",
            type=ExtensionType.NEW_MEMORY_PROCESSOR,
            name=name,
            description=description,
            code=code,
            imports=imports,
            dependencies=["neo4j"],
            test_code=test_code,
            doc_code=doc_code,
            checksum=_compute_checksum(code),
            quality_score=self._calculate_quality(code, handbook),
            timestamp_utc=_utc_now(),
            gap_id=gap_id,
        )

        self._templates_used.append(ExtensionType.NEW_MEMORY_PROCESSOR.value)
        self._extensions_generated += 1

        return extension

    def save_extension(
        self, extension: GeneratedExtension, output_dir: str
    ) -> dict[str, str]:
        os.makedirs(output_dir, exist_ok=True)

        code_path = os.path.join(output_dir, self._generate_file_name(extension.name))
        with open(code_path, "w") as f:
            f.write(extension.code)

        test_path = None
        if extension.test_code:
            test_path = os.path.join(
                output_dir, f"test_{self._generate_file_name(extension.name)}"
            )
            with open(test_path, "w") as f:
                f.write(extension.test_code)

        doc_path = None
        if extension.doc_code:
            doc_path = os.path.join(
                output_dir, f"{self._generate_file_name(extension.name)}.md"
            )
            with open(doc_path, "w") as f:
                f.write(extension.doc_code)

        _emit_event(
            "denis:self_extension:extension_saved",
            {
                "extension_id": extension.id,
                "code_path": code_path,
            },
        )

        return {"code": code_path, "test": test_path, "doc": doc_path}

    def get_stats(self) -> dict[str, Any]:
        return {
            "extensions_generated": self._extensions_generated,
            "templates_used": self._templates_used,
        }


def create_generator() -> ExtensionGenerator:
    return ExtensionGenerator()


if __name__ == "__main__":
    import json

    gen = ExtensionGenerator()

    print("=== GENERATING TOOL ===")
    ext = gen.generate_tool(
        name="data-aggregator",
        description="Aggregates data from multiple sources",
        gap_id="gap_missing_aggregator",
    )
    print(
        json.dumps(
            {
                "id": ext.id,
                "name": ext.name,
                "type": ext.type.value,
                "quality_score": ext.quality_score,
            },
            indent=2,
        )
    )

    print("\n=== CODE PREVIEW ===")
    for i, line in enumerate(ext.code.split("\n")[:30]):
        print(f"{i + 1:3}: {line}")

    print("\n=== SAVING ===")
    paths = gen.save_extension(ext, "/tmp/denis_extensions")
    print(json.dumps(paths, indent=2))
