"""
Extension Generator - Genera código para auto-extensiones de DENIS.

Usa templates y Behavior Handbook para generar código coherente
con el estilo existente del codebase.

NO usa LLM externo - usa templates y patrones extraídos.
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
class ExtensionTemplate:
    type: ExtensionType
    name: str
    description: str
    template_code: str
    imports_required: list[str]
    dependencies: list[str] = field(default_factory=list)
    test_template: str = ""
    doc_template: str = ""


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


class ToolTemplate:
    """Templates para nuevos tools."""

    @staticmethod
    def basic_tool() -> str:
        return '''"""
{name}: {description}
"""

from __future__ import annotations

from typing import Any
import logging

logger = logging.getLogger(__name__)


class {class_name}:
    """{description}"""
    
    def __init__(self):
        self.name = "{name}"
    
    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the {name} operation.
        
        Args:
            input_data: Dictionary containing input parameters
            
        Returns:
            Dictionary with result
        """
        try:
            # TODO: Implement {name} logic
            result = {{
                "status": "success",
                "tool": self.name,
                "output": input_data,
            }}
            return result
        except Exception as e:
            logger.error(f"{{self.name}} failed: {{e}}")
            return {{
                "status": "error",
                "tool": self.name,
                "error": str(e),
            }}
'''

    @staticmethod
    def cortex_adapter() -> str:
        return '''"""
{name}: {description}
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import redis


@dataclass
class {class_name}Config:
    """Configuration for {name}"""
    redis_url: str = "redis://localhost:6379/0"
    ttl_seconds: int = 3600


class {class_name}:
    """{description}"""
    
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
        """Perceive current state from external system."""
        try:
            # TODO: Implement perception logic
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
        """Perform action on external system."""
        try:
            # TODO: Implement action logic
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


class MemoryProcessorTemplate:
    """Templates para processors de memoria."""

    @staticmethod
    def memory_augment() -> str:
        return '''"""
{name}: {description}
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from neo4j import GraphDatabase


@dataclass
class {class_name}Config:
    """Configuration for {class_name}"""
    uri: str = "bolt://10.10.10.1:7687"
    user: str = "neo4j"
    password: str = ""


class {class_name}:
    """{description}"""
    
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
        """Augment a node with new properties."""
        try:
            with self._driver.session() as session:
                result = session.run("""
                    MATCH (n)
                    WHERE n.node_id = $node_id OR id(n) = toInteger($node_id)
                    SET n += $properties,
                        n.updated_at = datetime()
                    RETURN n
                """, node_id=node_id, properties=properties)
                
                updated = result.single()
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
        """Execute custom query."""
        try:
            with self._driver.session() as session:
                result = session.run(query, params)
                return [dict(r) for r in result]
        except Exception as e:
            return [{{"error": str(e)}}]
'''


class ExtensionGenerator:
    """Generador de extensiones basado en templates y handbook."""

    TEMPLATES = {
        ExtensionType.NEW_TOOL: ToolTemplate.basic_tool,
        ExtensionType.NEW_ADAPTER: ToolTemplate.cortex_adapter,
        ExtensionType.NEW_MEMORY_PROCESSOR: MemoryProcessorTemplate.memory_augment,
    }

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

    def _format_code(self, code: str) -> str:
        import re

        lines = code.split("\n")
        formatted = []
        indent_level = 0
        indent_size = 4

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("}"):
                indent_level = max(0, indent_level - 1)
            formatted.append(" " * indent_level * indent_size + stripped)
            if stripped.startswith("{") and not stripped.endswith("}"):
                indent_level += 1
            elif stripped.startswith(
                ("if ", "for ", "while ", "def ", "class ", "try:", "except")
            ):
                indent_level += 1

        return "\n".join(formatted)

    def generate_tool(
        self,
        name: str,
        description: str,
        gap_id: str | None = None,
    ) -> GeneratedExtension:
        handbook = self._load_handbook_patterns()
        style = self._extract_naming_style(handbook)

        class_name = self._generate_class_name(name, style)
        file_name = self._generate_file_name(name)

        template_fn = self.TEMPLATES.get(
            ExtensionType.NEW_TOOL, ToolTemplate.basic_tool
        )
        code = template_fn().format(
            name=name,
            class_name=class_name,
            description=description,
        )

        code = self._format_code(code)

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

        template_fn = self.TEMPLATES.get(
            ExtensionType.NEW_MEMORY_PROCESSOR, MemoryProcessorTemplate.memory_augment
        )
        code = template_fn().format(
            name=name,
            class_name=class_name,
            description=description,
        )

        code = self._format_code(code)

        imports = [
            "from __future__ import annotations",
            "from typing import Any",
            "from neo4j import GraphDatabase",
        ]

        test_code = self._generate_test(class_name, name, processor_type="neo4j")
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

    def _generate_test(
        self, class_name: str, name: str, processor_type: str = "basic"
    ) -> str:
        return f'''"""
Tests for {name}
"""

import pytest
from {name.replace(" ", "_").lower()} import {class_name}


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
        return f"""# {name}

{description}

## Usage

```python
from {name.replace(" ", "_").lower()} import {class_name}

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
        if "logger" in code.lower() or "logging" in code.lower():
            score += 0.1
        if "try:" in code and "except" in code:
            score += 0.1
        if "async" in code:
            score += 0.1

        return min(1.0, score)

    def save_extension(
        self, extension: GeneratedExtension, output_dir: str
    ) -> dict[str, str]:
        os.makedirs(output_dir, exist_ok=True)

        code_path = os.path.join(output_dir, self._generate_file_name(extension.name))
        with open(code_path, "w") as f:
            f.write(extension.code)

        if extension.test_code:
            test_path = os.path.join(
                output_dir, f"test_{self._generate_file_name(extension.name)}"
            )
            with open(test_path, "w") as f:
                f.write(extension.test_code)

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

        return {
            "code": code_path,
            "test": test_path if extension.test_code else None,
            "doc": doc_path if extension.doc_code else None,
        }

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
        name="new-data-processor",
        description="Processes data from external sources",
        gap_id="gap_missing_processor",
    )
    print(
        json.dumps(
            {
                "id": ext.id,
                "name": ext.name,
                "type": ext.type.value,
                "quality_score": ext.quality_score,
                "checksum": ext.checksum,
            },
            indent=2,
            sort_keys=True,
        )
    )

    print("\n=== SAVING EXTENSION ===")
    paths = gen.save_extension(ext, "/tmp/denis_extensions")
    print(json.dumps(paths, indent=2))

    print("\n=== STATS ===")
    print(json.dumps(gen.get_stats(), indent=2))
