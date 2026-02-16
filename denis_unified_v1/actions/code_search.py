"""
Code Search Tool - Search code repositories and technical resources.

Provides:
- GitHub code search
- StackOverflow search
- Documentation search (ReadTheDocs, etc.)
- Syntax-aware result extraction
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class CodeResult:
    """A code search result."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # Source info
    source: str = ""  # "github", "stackoverflow", "docs"
    url: str = ""
    title: str = ""

    # Code content
    code: str = ""
    language: str = ""
    file_path: str = ""
    line_start: int = 0
    line_end: int = 0

    # Context
    description: str = ""
    stars: int = 0
    relevance_score: float = 0.0

    # Metadata
    author: str = ""
    created_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "url": self.url,
            "title": self.title,
            "code": self.code,
            "language": self.language,
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "description": self.description,
            "stars": self.stars,
            "relevance_score": self.relevance_score,
            "author": self.author,
            "created_at": self.created_at,
        }

    def to_markdown(self) -> str:
        """Format as markdown code block."""
        lang = self.language or "text"
        return f"```{lang}\n{self.code}\n```\n\n*Source: [{self.title}]({self.url})*"


class CodeSearchTool:
    """Code-specific search tool with scraping."""

    def __init__(self):
        self.mock_mode = True  # Use mock data for now

    async def search(
        self,
        query: str,
        sources: List[str] = None,
        language: str = "",
        max_results: int = 5,
    ) -> List[CodeResult]:
        """Search code across multiple sources."""
        if sources is None:
            sources = ["github", "stackoverflow", "docs"]

        results = []

        if "github" in sources:
            results.extend(await self._search_github(query, language, max_results))

        if "stackoverflow" in sources:
            results.extend(await self._search_stackoverflow(query, max_results))

        if "docs" in sources:
            results.extend(await self._search_docs(query, language, max_results))

        # Sort by relevance
        results.sort(key=lambda r: r.relevance_score, reverse=True)

        return results[:max_results]

    async def _search_github(
        self, query: str, language: str, max_results: int
    ) -> List[CodeResult]:
        """Search GitHub code."""
        # In production, use GitHub API
        # For now, return mock results
        results = []

        mock_results = [
            {
                "title": f"GitHub: {query} implementation",
                "code": f"def {query.replace(' ', '_').lower()}():\n    # Implementation of {query}\n    pass",
                "language": "python",
                "url": f"https://github.com/search?q={query}",
                "stars": 1500,
            },
            {
                "title": f"GitHub: {query} usage example",
                "code": f"// Usage example for {query}\nconst result = await {query.replace(' ', '').lower()}();",
                "language": "javascript",
                "url": f"https://github.com/example/{query}",
                "stars": 890,
            },
        ]

        for i, mock in enumerate(mock_results[:max_results]):
            result = CodeResult(
                source="github",
                title=mock["title"],
                code=mock["code"],
                language=mock["language"],
                url=mock["url"],
                stars=mock["stars"],
                relevance_score=0.9 - (i * 0.2),
            )
            results.append(result)

        return results

    async def _search_stackoverflow(
        self, query: str, max_results: int
    ) -> List[CodeResult]:
        """Search StackOverflow."""
        results = []

        mock_results = [
            {
                "title": f"StackOverflow: How to {query}?",
                "code": f"# Solution for {query}\n# Here's how to do it:\n\nresult = process_{query.replace(' ', '_').lower()}()",
                "language": "python",
                "url": f"https://stackoverflow.com/search?q={query}",
                "votes": 42,
            },
            {
                "title": f"StackOverflow: Best practices for {query}",
                "code": f"// Recommended approach for {query}\n// Follow these steps:\n\nimplementation();",
                "language": "javascript",
                "url": f"https://stackoverflow.com/questions/12345/{query}",
                "votes": 28,
            },
        ]

        for i, mock in enumerate(mock_results[:max_results]):
            result = CodeResult(
                source="stackoverflow",
                title=mock["title"],
                code=mock["code"],
                language=mock["language"],
                url=mock["url"],
                stars=mock["votes"],
                relevance_score=0.85 - (i * 0.2),
            )
            results.append(result)

        return results

    async def _search_docs(
        self, query: str, language: str, max_results: int
    ) -> List[CodeResult]:
        """Search documentation."""
        results = []

        mock_results = [
            {
                "title": f"Docs: {query} - Official Guide",
                "code": f"# Official documentation for {query}\n# Reference: https://docs.example.com/{query.replace(' ', '-').lower()}",
                "language": language or "python",
                "url": f"https://docs.example.com/{query.replace(' ', '-').lower()}",
            },
        ]

        for mock in mock_results[:max_results]:
            result = CodeResult(
                source="docs",
                title=mock["title"],
                code=mock["code"],
                language=mock["language"],
                url=mock["url"],
                relevance_score=0.8,
            )
            results.append(result)

        return results

    def extract_syntax(self, code: str, language: str = "") -> Dict[str, Any]:
        """Extract syntax information from code."""
        info = {
            "language": language or "text",
            "has_imports": False,
            "has_functions": False,
            "has_classes": False,
            "has_async": False,
            "complexity": "simple",
        }

        # Detect language if not provided
        if not language:
            if "def " in code or "import " in code:
                info["language"] = "python"
            elif "function " in code or "const " in code or "let " in code:
                info["language"] = "javascript"
            elif "fn " in code and "->" in code:
                info["language"] = "rust"
            elif "func " in code and "(" in code:
                info["language"] = "go"

        # Analyze code structure
        if re.search(r"^import |^from ", code, re.MULTILINE):
            info["has_imports"] = True
        if re.search(r"^def |^function |^fn ", code, re.MULTILINE):
            info["has_functions"] = True
        if re.search(r"^class |^struct ", code, re.MULTILINE):
            info["has_classes"] = True
        if "async " in code or "await " in code:
            info["has_async"] = True

        # Complexity estimation
        if code.count("\n") > 20 or code.count("if ") > 3:
            info["complexity"] = "complex"
        elif code.count("\n") > 10:
            info["complexity"] = "moderate"

        return info


class CodeSearchExecutor:
    """Execute code search as part of PRO_SEARCH toolchain."""

    def __init__(self):
        self.tool = CodeSearchTool()

    async def execute(
        self,
        query: str,
        language: str = "",
        sources: List[str] = None,
        max_results: int = 5,
    ) -> Dict[str, Any]:
        """Execute code search."""
        results = await self.tool.search(
            query=query,
            sources=sources,
            language=language,
            max_results=max_results,
        )

        return {
            "status": "success",
            "results": [r.to_dict() for r in results],
            "count": len(results),
            "query": query,
        }


async def search_code(
    query: str,
    language: str = "",
    sources: List[str] = None,
) -> List[CodeResult]:
    """Convenience function for code search."""
    tool = CodeSearchTool()
    return await tool.search(query, sources, language)
