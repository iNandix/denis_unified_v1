// =============================================================================
// CODECRAFT CORE CHUNKS
// =============================================================================

// License nodes
MERGE (l1:License {spdx_id: 'MIT'})
SET l1.name = 'MIT License', l1.category = 'permissive';

MERGE (l2:License {spdx_id: 'Apache-2.0'})
SET l2.name = 'Apache License 2.0', l2.category = 'permissive';

MERGE (l3:License {spdx_id: 'BSD-3-Clause'})
SET l3.name = 'BSD 3-Clause', l3.category = 'permissive';

MERGE (l4:License {spdx_id: 'GPL-3.0'})
SET l4.name = 'GPL 3.0', l4.category = 'copyleft';

// Chunk: Python Module Template
MERGE (c1:Chunk {chunk_id: 'chunk_py_module_v1'})
SET c1.name = 'Python Module Template',
    c1.kind = 'module',
    c1.lang = 'python',
    c1.tags = ['python', 'module', 'template'],
    c1.inputs_schema_json = '{"module_name": "str", "author": "str", "description": "str"}',
    c1.output_contract_json = '{"files_created": ["{module_name}/__init__.py", "{module_name}/main.py"], "symbols_exported": ["main"], "commands_to_run": []}',
    c1.quality_grade = 0.9,
    c1.risk_level = 'low',
    c1.template_content = '''"""{module_name} - {description}

Author: {author}
"""

def main():
    """Main entry point."""
    pass

if __name__ == "__main__":
    main()
''';
MERGE (c1)-[:LICENSED_AS]->(l1);
MERGE (c1)-[:BELONGS_TO_SPECIALTY]->(sa);

MERGE (c2:Chunk {chunk_id: 'chunk_py_class_v1'})
SET c2.name = 'Python Class Template',
    c2.kind = 'class',
    c2.lang = 'python',
    c2.tags = ['python', 'class', 'oop', 'template'],
    c2.inputs_schema_json = '{"class_name": "str", "base_class": "str|null", "attributes": "list", "methods": "list"}',
    c2.output_contract_json = '{"files_modified": ["{module}.py"], "symbols_exported": ["{class_name}"]}',
    c2.quality_grade = 0.85,
    c2.risk_level = 'low',
    c2.template_content = '''class {class_name}{% if base_class %}({base_class}){% endif %}:
    """{class_name} description."""

    def __init__(self{% if attributes %}, {% for attr in attributes %}{attr}{% endfor %}{% endif %}):
        {% for attr in attributes %}self.{attr} = {attr}
        {% endfor %}pass

    def __repr__(self):
        return f"{self.__class__.__name__}()"
''';
MERGE (c2)-[:LICENSED_AS]->(l1);
MERGE (c2)-[:BELONGS_TO_SPECIALTY]->(ir);

// Chunk: Python Function Template
MERGE (c3:Chunk {chunk_id: 'chunk_py_function_v1'})
SET c3.name = 'Python Function Template',
    c3.kind = 'function',
    c3.lang = 'python',
    c3.tags = ['python', 'function', 'template'],
    c3.inputs_schema_json = '{"func_name": "str", "args": "list", "return_type": "str", "docstring": "str"}',
    c3.output_contract_json = '{"files_modified": ["{module}.py"], "symbols_exported": ["{func_name}"]}',
    c3.quality_grade = 0.9,
    c3.risk_level = 'low',
    c3.template_content = '''def {func_name}({args}) -> {return_type}:
    """{docstring}

    Args:
    {% for arg in args %}:param {arg}: description
    {% endfor %}
    Returns:
        {return_type}: description
    """
    pass
''';
MERGE (c3)-[:LICENSED_AS]->(l1);
MERGE (:CodeSpecialty {id: 'impl_refactor'})-[:BELONGS_TO_SPECIALTY]->(c3);

// Chunk: Pytest Test Template
MERGE (c4:Chunk {chunk_id: 'chunk_pytest_v1'})
SET c4.name = 'Pytest Test Template',
    c4.kind = 'test',
    c4.lang = 'python',
    c4.tags = ['python', 'pytest', 'testing', 'template'],
    c4.inputs_schema_json = '{"test_name": "str", "module_under_test": "str", "fixtures": "list"}',
    c4.output_contract_json = '{"files_created": ["tests/test_{module_under_test}.py"], "tests_to_add": ["test_{test_name}"]}',
    c4.quality_grade = 0.95,
    c4.risk_level = 'low',
    c4.template_content = '''import pytest
from {module_under_test} import {% for symbol in symbols %}{symbol}{% if not loop.last %}, {% endif %}{% endfor %}

class Test{module_under_test.split('.')[-1].title()}:
    """Tests for {module_under_test}."""

    def test_{test_name}(self{% if fixtures %}, {% for f in fixtures %}{f}{% if not loop.last %}, {% endif %}{% endfor %}{% endif %}):
        """Test {test_name}."""
        # Arrange
        pass

        # Act
        result = None  # TODO: implement

        # Assert
        assert result is not None
''';
MERGE (c4)-[:LICENSED_AS]->(l1);
MERGE (:CodeSpecialty {id: 'quality_reliability'})-[:BELONGS_TO_SPECIALTY]->(c4);

// Chunk: CLI Command Template
MERGE (c5:Chunk {chunk_id: 'chunk_cli_command_v1'})
SET c5.name = 'CLI Command Template',
    c5.kind = 'cli_command',
    c5.lang = 'python',
    c5.tags = ['python', 'cli', 'argparse', 'template'],
    c5.inputs_schema_json = '{"command_name": "str", "description": "str", "arguments": "list"}',
    c5.output_contract_json = '{"files_created": ["cli.py"], "commands_to_run": ["python cli.py --help"]}',
    c5.quality_grade = 0.85,
    c5.risk_level = 'low',
    c5.template_content = '''#!/usr/bin/env python3
"""CLI for {command_name}."""

import argparse

def main():
    parser = argparse.ArgumentParser(description="{description}")
    {% for arg in arguments %}
    parser.add_argument("{arg.name}", "{arg.flag}", help="{arg.help}"{% if arg.default %}, default={arg.default}{% endif %})
    {% endfor %}
    args = parser.parse_args()
    # TODO: implement command logic

if __name__ == "__main__":
    main()
''';
MERGE (c5)-[:LICENSED_AS]->(l1);
MERGE (:CodeSpecialty {id: 'integration_tooling'})-[:BELONGS_TO_SPECIALTY]->(c5);

// Chunk: Docker Compose Template
MERGE (c6:Chunk {chunk_id: 'chunk_docker_compose_v1'})
SET c6.name = 'Docker Compose Template',
    c6.kind = 'config',
    c6.lang = 'yaml',
    c6.tags = ['docker', 'compose', 'yaml', 'template'],
    c6.inputs_schema_json = '{"services": "list", "version": "str"}',
    c6.output_contract_json = '{"files_created": ["docker-compose.yml"]}',
    c6.quality_grade = 0.9,
    c6.risk_level = 'medium',
    c6.template_content = '''version: '{version}'

services:
{% for service in services %}
  {service.name}:
    image: {service.image}
    ports:
      - "{service.port}:{service.port}"
{% if service.env %}
    environment:
{% for key, value in service.env.items() %}
      - {key}={value}
{% endfor %}{% endif %}
{% if service.volumes %}
    volumes:
      - {service.volumes}
{% endif %}
{% endfor %}
''';
MERGE (c6)-[:LICENSED_AS]->(l1);
MERGE (:CodeSpecialty {id: 'integration_tooling'})-[:BELONGS_TO_SPECIALTY]->(c6);

// Chunk: Error Handling Template
MERGE (c7:Chunk {chunk_id: 'chunk_error_handling_v1'})
SET c7.name = 'Error Handling Template',
    c7.kind = 'error_handling',
    c7.lang = 'python',
    c7.tags = ['python', 'exception', 'error', 'template'],
    c7.inputs_schema_json = '{"error_class": "str", "context": "str"}',
    c7.output_contract_json = '{"files_modified": ["{module}.py"]}',
    c7.quality_grade = 0.9,
    c7.risk_level = 'low',
    c7.template_content = '''class {error_class}(Exception):
    """Custom exception for {context}."""

    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {{"error": self.message, "details": self.details}}


def handle_{error_class.lower()}(func):
    """Decorator for handling {error_class}."""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except {error_class} as e:
            # Log and re-raise or handle
            raise
    return wrapper
''';
MERGE (c7)-[:LICENSED_AS]->(l1);
MERGE (:CodeSpecialty {id: 'quality_reliability'})-[:BELONGS_TO_SPECIALTY]->(c7);

// Chunk: Observability Template
MERGE (c8:Chunk {chunk_id: 'chunk_observability_v1'})
SET c8.name = 'Observability Template',
    c8.kind = 'observability',
    c8.lang = 'python',
    c8.tags = ['python', 'logging', 'metrics', 'observability', 'template'],
    c8.inputs_schema_json = '{"module_name": "str", "log_level": "str"}',
    c8.output_contract_json = '{"files_modified": ["{module_name}/__init__.py"]}',
    c8.quality_grade = 0.9,
    c8.risk_level = 'low',
    c8.template_content = '''"""Observability for {module_name}."""

import logging
from functools import wraps

logger = logging.getLogger(__name__)
logging.basicConfig(level={log_level})


def traced(func):
    """Decorator to trace function calls."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        logger.debug(f"Calling {func.__name__}")
        try:
            result = func(*args, **kwargs)
            logger.debug(f"{func.__name__} returned")
            return result
        except Exception as e:
            logger.exception(f"{func.__name__} raised {type(e).__name__}")
            raise
    return wrapper
''';
MERGE (c8)-[:LICENSED_AS]->(l1);
MERGE (:CodeSpecialty {id: 'quality_reliability'})-[:BELONGS_TO_SPECIALTY]->(c8);

// Chunk: FastAPI Route Template
MERGE (c9:Chunk {chunk_id: 'chunk_fastapi_route_v1'})
SET c9.name = 'FastAPI Route Template',
    c9.kind = 'api_route',
    c9.lang = 'python',
    c9.tags = ['python', 'fastapi', 'api', 'rest', 'template'],
    c9.inputs_schema_json = '{"route_path": "str", "method": "str", "request_model": "str", "response_model": "str"}',
    c9.output_contract_json = '{"files_modified": ["api.py"], "symbols_exported": ["router"]}',
    c9.quality_grade = 0.85,
    c9.risk_level = 'medium',
    c9.template_content = '''from fastapi import APIRouter, Depends, HTTPException
from {request_model} import {request_model}Request
from {response_model} import {response_model}Response

router = APIRouter(prefix="/{route_path}", tags=["{route_path}"])


@{router.method}("/{item_id}")
async def {route_path}_item(
    item_id: str,
    data: {request_model}Request = None
) -> {response_model}Response:
    """Endpoint description."""
    # TODO: implement
    return {response_model}Response(id=item_id, status="ok")
''';
MERGE (c9)-[:LICENSED_AS]->(l1);
MERGE (:CodeSpecialty {id: 'integration_tooling'})-[:BELONGS_TO_SPECIALTY]->(c9);

// Chunk: Adapter Template
MERGE (c10:Chunk {chunk_id: 'chunk_adapter_v1'})
SET c10.name = 'Adapter Pattern Template',
    c10.kind = 'adapter',
    c10.lang = 'python',
    c10.tags = ['python', 'adapter', 'pattern', 'template'],
    c10.inputs_schema_json = '{"target_interface": "str", "adaptee_class": "str"}',
    c10.output_contract_json = '{"files_created": ["adapters.py"], "symbols_exported": ["{target_interface}Adapter"]}',
    c10.quality_grade = 0.85,
    c10.risk_level = 'low',
    c10.template_content = '''"""Adapter for {adaptee_class}."""

from abc import ABC, abstractmethod
from typing import Any


class TargetInterface(ABC):
    """Target interface to adapt to."""

    @abstractmethod
    def request(self) -> str:
        pass


class {adaptee_class}Adapter(TargetInterface):
    """Adapter wrapping {adaptee_class}."""

    def __init__(self, adaptee: {adaptee_class}):
        self.adaptee = adaptee

    def request(self) -> str:
        # Adapt adaptee's method to target interface
        return self.adaptee.specific_request()
''';
MERGE (c10)-[:LICENSED_AS]->(l1);
MERGE (:CodeSpecialty {id: 'impl_refactor'})-[:BELONGS_TO_SPECIALTY]->(c10);

RETURN 'Core chunks created';
