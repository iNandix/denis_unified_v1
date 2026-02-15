"""Entity extractors for intent detection.

Extracts:
- File paths (src/..., *.py, *.md, etc.)
- Commands (pytest, docker, git, kubectl, make, etc.)
- Ports (:8084, :8000)
- Services (persona, router, scheduler, api, ci)
- Environment flags (DENIS_*)
"""

from __future__ import annotations

import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from denis_unified_v1.intent.intent_v1 import IntentEntity, ConfidenceSource


# Entity extraction patterns
ENTITY_PATTERNS = {
    # File paths - various formats
    "path": [
        r"(?:[\w\-]+/)+[\w\-]+\.[\w]+",  # unix paths with extension
        r"\b[\w\-]+\.[\w]{1,10}\b",  # filenames with extension
        r"tests?/[\w\-/]+\.py",  # test paths
        r"denis_unified_v1/[\w\-/]+",  # project paths
        r"src/[\w\-/]+",  # src paths
        r"api/[\w\-/]+",  # api paths
    ],
    # Commands
    "command": [
        r"\bpytest\b(?:\s+-[\w]+)*",  # pytest with flags
        r"\bdocker\b(?:\s+\w+)*",  # docker commands
        r"\bgit\b(?:\s+\w+)*",  # git commands
        r"\bkubectl\b(?:\s+\w+)*",  # kubectl
        r"\bmake\b(?:\s+\w+)*",  # make
        r"\bpip\b(?:\s+\w+)*",  # pip
        r"\bnpm\b(?:\s+\w+)*",  # npm
        r"\bpython\b(?:\s+-[\w]+)*",  # python
        r"`([^`]+)`",  # inline code/commands
    ],
    # Ports
    "port": [
        r":(\d{2,5})\b",  # :8084, :8000, etc.
        r"\bport\s*:?\s*(\d{2,5})",  # "port 8084"
    ],
    # Services
    "service": [
        r"\b(persona|router|scheduler|api|ci|cd|gateway|engine)\b",
        r"\bservicio\s+(\w+)",
        r"\bservice\s+(\w+)",
    ],
    # Environment flags
    "env_flag": [
        r"\b(DENIS_\w+)\b",  # DENIS_* variables
        r"\$\{(\w+)\}",  # ${VAR} syntax
        r"\$(\w+)",  # $VAR syntax
    ],
    # URLs
    "url": [
        r"https?://[^\s\"<>]+",
        r"localhost:\d+",
        r"127\.0\.0\.\d+:\d+",
        r"10\.\d+\.\d+\.\d+:\d+",
    ],
}


@dataclass
class ExtractedEntities:
    """Container for all extracted entities."""

    paths: List[str]
    commands: List[str]
    ports: List[str]
    services: List[str]
    env_flags: List[str]
    urls: List[str]

    def to_intent_entities(self) -> List[IntentEntity]:
        """Convert to IntentEntity objects."""
        entities = []

        for path in self.paths:
            entities.append(
                IntentEntity(
                    type="path",
                    value=path,
                    confidence=0.85,
                    source=ConfidenceSource.HEURISTICS,
                )
            )

        for cmd in self.commands:
            entities.append(
                IntentEntity(
                    type="command",
                    value=cmd,
                    confidence=0.80,
                    source=ConfidenceSource.HEURISTICS,
                )
            )

        for port in self.ports:
            entities.append(
                IntentEntity(
                    type="port",
                    value=port,
                    confidence=0.90,
                    source=ConfidenceSource.HEURISTICS,
                )
            )

        for service in self.services:
            entities.append(
                IntentEntity(
                    type="service",
                    value=service,
                    confidence=0.75,
                    source=ConfidenceSource.HEURISTICS,
                )
            )

        for flag in self.env_flags:
            entities.append(
                IntentEntity(
                    type="env_flag",
                    value=flag,
                    confidence=0.85,
                    source=ConfidenceSource.HEURISTICS,
                )
            )

        for url in self.urls:
            entities.append(
                IntentEntity(
                    type="url",
                    value=url,
                    confidence=0.90,
                    source=ConfidenceSource.HEURISTICS,
                )
            )

        return entities

    def to_dict(self) -> Dict[str, List[str]]:
        return {
            "paths": self.paths,
            "commands": self.commands,
            "ports": self.ports,
            "services": self.services,
            "env_flags": self.env_flags,
            "urls": self.urls,
        }


class EntityExtractor:
    """Extract entities from prompts using regex patterns."""

    def __init__(self):
        self.patterns = ENTITY_PATTERNS

    def extract(self, prompt: str) -> ExtractedEntities:
        """Extract all entity types from prompt."""
        return ExtractedEntities(
            paths=self._extract_paths(prompt),
            commands=self._extract_commands(prompt),
            ports=self._extract_ports(prompt),
            services=self._extract_services(prompt),
            env_flags=self._extract_env_flags(prompt),
            urls=self._extract_urls(prompt),
        )

    def _extract_paths(self, prompt: str) -> List[str]:
        """Extract file paths."""
        paths = []
        for pattern in self.patterns["path"]:
            matches = re.finditer(pattern, prompt, re.IGNORECASE)
            for match in matches:
                value = match.group(0)
                # Clean up and validate
                if len(value) > 2 and not value.startswith("http"):
                    paths.append(value)
        return self._deduplicate(paths)

    def _extract_commands(self, prompt: str) -> List[str]:
        """Extract commands."""
        commands = []
        for pattern in self.patterns["command"]:
            matches = re.finditer(pattern, prompt, re.IGNORECASE)
            for match in matches:
                # Handle backtick groups
                if match.group(0).startswith("`") and len(match.groups()) > 0:
                    value = match.group(1) or match.group(0).strip("`")
                else:
                    value = match.group(0)
                if len(value) > 2:
                    commands.append(value)
        return self._deduplicate(commands)

    def _extract_ports(self, prompt: str) -> List[str]:
        """Extract port numbers."""
        ports = []
        for pattern in self.patterns["port"]:
            matches = re.finditer(pattern, prompt, re.IGNORECASE)
            for match in matches:
                # Get port number from group 1 if exists, else full match
                value = match.group(1) if match.groups() else match.group(0).lstrip(":")
                # Validate port range
                try:
                    port_num = int(value)
                    if 1 <= port_num <= 65535:
                        ports.append(str(port_num))
                except ValueError:
                    continue
        return self._deduplicate(ports)

    def _extract_services(self, prompt: str) -> List[str]:
        """Extract service names."""
        services = []
        for pattern in self.patterns["service"]:
            matches = re.finditer(pattern, prompt, re.IGNORECASE)
            for match in matches:
                # Get from group 1 if exists
                value = match.group(1) if match.groups() else match.group(0)
                if value:
                    services.append(value.lower())
        return self._deduplicate(services)

    def _extract_env_flags(self, prompt: str) -> List[str]:
        """Extract environment flags."""
        flags = []
        for pattern in self.patterns["env_flag"]:
            matches = re.finditer(pattern, prompt, re.IGNORECASE)
            for match in matches:
                # Get from group 1 for ${VAR} and $VAR patterns
                value = match.group(1) if match.groups() else match.group(0)
                if value:
                    flags.append(value)
        return self._deduplicate(flags)

    def _extract_urls(self, prompt: str) -> List[str]:
        """Extract URLs."""
        urls = []
        for pattern in self.patterns["url"]:
            matches = re.finditer(pattern, prompt, re.IGNORECASE)
            for match in matches:
                urls.append(match.group(0))
        return self._deduplicate(urls)

    def _deduplicate(self, items: List[str]) -> List[str]:
        """Remove duplicates while preserving order."""
        seen = set()
        result = []
        for item in items:
            item_lower = item.lower()
            if item_lower not in seen:
                seen.add(item_lower)
                result.append(item)
        return result


# Singleton instance
_extractor: Optional[EntityExtractor] = None


def get_entity_extractor() -> EntityExtractor:
    """Get singleton entity extractor."""
    global _extractor
    if _extractor is None:
        _extractor = EntityExtractor()
    return _extractor


def extract_entities(prompt: str) -> List[IntentEntity]:
    """Convenience function to extract entities."""
    return get_entity_extractor().extract(prompt).to_intent_entities()
