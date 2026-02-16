"""
Information Chunking - Extract and filter relevant content from scraped pages.

This module provides:
- Content extraction from raw HTML
- Relevance scoring based on query
- Chunking strategies (fixed, semantic, sliding window)
- Noise removal (ads, navigation, boilerplate)
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Chunk:
    """A chunk of extracted content."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    text: str = ""
    relevance_score: float = 0.0
    source_url: str = ""
    source_title: str = ""
    start_index: int = 0
    end_index: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_code: bool = False
    language: Optional[str] = None


@dataclass
class ChunkingConfig:
    """Configuration for chunking."""

    strategy: str = "semantic"  # "fixed", "semantic", "sliding"
    chunk_size: int = 1000
    chunk_overlap: int = 200
    min_chunk_size: int = 100
    max_chunk_size: int = 2000
    remove_boilerplate: bool = True
    extract_code: bool = True
    relevance_threshold: float = 0.3


class ContentExtractor:
    """Extract clean content from HTML/raw text."""

    BOILERPLATE_PATTERNS = [
        r"(?i)(advertisement|advert|sponsored)",
        r"(?i)(cookie|privacy policy|terms of service)",
        r"(?i)(subscribe|newsletter|sign up)",
        r"(?i)(follow us|social media|share)",
        r"(?i)(copyright|\d{4} \w+ rights reserved)",
    ]

    CODE_PATTERNS = [
        r"```\w*\n[\s\S]*?```",  # Fenced code
        r"`[^`]+`",  # Inline code
        r"(?s)<pre[^>]*>.*?</pre>",  # Pre blocks
        r"(?s)<code[^>]*>.*?</code>",  # Code blocks
    ]

    def __init__(self, config: Optional[ChunkingConfig] = None):
        self.config = config or ChunkingConfig()

    def extract_from_html(self, html: str, url: str = "") -> str:
        """Extract clean text from HTML."""
        import bs4

        soup = soup = bs4.BeautifulSoup(html, "html.parser")

        # Remove script/style/nav/footer
        for tag in soup(
            ["script", "style", "nav", "footer", "header", "aside", "form"]
        ):
            tag.decompose()

        # Try to find main content
        main = (
            soup.find("main")
            or soup.find("article")
            or soup.find("div", class_=re.compile("content|article|post"))
        )

        if main:
            text = main.get_text(separator="\n", strip=True)
        else:
            text = soup.get_text(separator="\n", strip=True)

        return self._clean_text(text)

    def extract_from_text(self, text: str) -> str:
        """Clean raw text."""
        return self._clean_text(text)

    def _clean_text(self, text: str) -> str:
        """Remove boilerplate and clean text."""
        lines = text.split("\n")
        cleaned = []

        for line in lines:
            # Skip empty lines
            if not line.strip():
                continue

            # Skip boilerplate
            is_boilerplate = False
            for pattern in self.BOILERPLATE_PATTERNS:
                if re.search(pattern, line):
                    is_boilerplate = True
                    break

            if is_boilerplate:
                continue

            # Skip very short lines that are likely UI elements
            if len(line.strip()) < 10 and not line.strip().endswith(
                (". ", ":", ")", "]")
            ):
                continue

            cleaned.append(line)

        return "\n".join(cleaned)

    def extract_code_blocks(self, text: str) -> List[Chunk]:
        """Extract code blocks from text."""
        chunks = []

        # Fenced code blocks
        for match in re.finditer(r"```(\w*)\n?([\s\S]*?)```", text):
            lang = match.group(1) or "text"
            code = match.group(2).strip()
            chunks.append(
                Chunk(
                    text=code,
                    is_code=True,
                    language=lang,
                    relevance_score=1.0,
                    metadata={"type": "fenced_code", "language": lang},
                )
            )

        # Inline code
        for match in re.finditer(r"`([^`]+)`", text):
            code = match.group(1)
            if len(code) > 20:  # Only substantial inline code
                chunks.append(
                    Chunk(
                        text=code,
                        is_code=True,
                        relevance_score=0.8,
                        metadata={"type": "inline_code"},
                    )
                )

        return chunks


class RelevanceScorer:
    """Score chunks by relevance to query."""

    def __init__(self):
        self.stop_words = frozenset(
            {
                "the",
                "a",
                "an",
                "and",
                "or",
                "but",
                "in",
                "on",
                "at",
                "to",
                "for",
                "of",
                "with",
                "by",
                "from",
                "as",
                "is",
                "was",
                "are",
                "were",
                "be",
                "been",
                "being",
                "have",
                "has",
                "had",
                "do",
                "does",
                "did",
                "will",
                "would",
                "should",
                "could",
                "may",
                "might",
                "must",
                "can",
                "this",
                "that",
                "these",
                "those",
                "i",
                "you",
                "he",
                "she",
                "it",
                "we",
                "they",
            }
        )

    def score(self, chunk: Chunk, query: str) -> float:
        """Calculate relevance score 0-1."""
        query_terms = self._tokenize(query)
        chunk_terms = self._tokenize(chunk.text)

        if not query_terms or not chunk_terms:
            return 0.0

        # Jaccard similarity
        intersection = query_terms & chunk_terms
        union = query_terms | chunk_terms

        base_score = len(intersection) / len(union) if union else 0

        # Boost for exact phrase matches
        query_lower = query.lower()
        chunk_lower = chunk.text.lower()

        if query_lower in chunk_lower:
            base_score = min(1.0, base_score + 0.3)

        # Boost for technical terms (longer words)
        tech_terms = [t for t in chunk_terms if len(t) > 8]
        tech_matches = len([t for t in tech_terms if t in query_lower])
        if tech_terms:
            base_score += tech_matches * 0.05

        return min(1.0, base_score)

    def _tokenize(self, text: str) -> frozenset[str]:
        """Tokenize text into terms."""
        text = text.lower()
        text = re.sub(r"[^\w\s]", " ", text)
        tokens = text.split()
        tokens = [t for t in tokens if t not in self.stop_words and len(t) > 2]
        return frozenset(tokens)


class ChunkProcessor:
    """Main chunking engine."""

    def __init__(self, config: Optional[ChunkingConfig] = None):
        self.config = config or ChunkingConfig()
        self.extractor = ContentExtractor(self.config)
        self.scorer = RelevanceScorer()

    def process(
        self, content: str, query: str, url: str = "", title: str = ""
    ) -> List[Chunk]:
        """Process content and return relevant chunks."""
        # Extract code blocks first
        code_chunks = []
        if self.config.extract_code:
            code_chunks = self.extractor.extract_code_blocks(content)

        # Extract clean text
        if "<" in content:
            text = self.extractor.extract_from_html(content, url)
        else:
            text = self.extractor.extract_from_text(content)

        # Chunk based on strategy
        if self.config.strategy == "fixed":
            text_chunks = self._fixed_chunk(text)
        elif self.config.strategy == "sliding":
            text_chunks = self._sliding_chunk(text)
        else:  # semantic
            text_chunks = self._semantic_chunk(text)

        # Create chunk objects with relevance scoring
        chunks = []
        for tc in text_chunks:
            chunk = Chunk(
                text=tc["text"],
                source_url=url,
                source_title=title,
                start_index=tc["start"],
                end_index=tc["end"],
            )
            chunk.relevance_score = self.scorer.score(chunk, query)
            chunks.append(chunk)

        # Add code chunks
        for cc in code_chunks:
            cc.source_url = url
            cc.source_title = title
            chunks.append(cc)

        # Filter by relevance threshold
        chunks = [
            c for c in chunks if c.relevance_score >= self.config.relevance_threshold
        ]

        # Sort by relevance
        chunks.sort(key=lambda c: c.relevance_score, reverse=True)

        return chunks

    def _fixed_chunk(self, text: str) -> List[Dict[str, Any]]:
        """Fixed-size chunking."""
        chunks = []
        start = 0

        while start < len(text):
            end = min(start + self.config.chunk_size, len(text))

            # Try to break at sentence boundary
            if end < len(text):
                for sep in [". ", "\n\n", "! ", "? "]:
                    last_sep = text.rfind(sep, start, end)
                    if last_sep > start + self.config.chunk_size // 2:
                        end = last_sep + len(sep)
                        break

            chunks.append({"text": text[start:end].strip(), "start": start, "end": end})

            start = end - self.config.chunk_overlap

        return chunks

    def _sliding_chunk(self, text: str) -> List[Dict[str, Any]]:
        """Sliding window chunking with overlap."""
        chunks = []
        step = self.config.chunk_size - self.config.chunk_overlap

        for start in range(0, len(text), step):
            end = min(start + self.config.chunk_size, len(text))
            chunks.append({"text": text[start:end].strip(), "start": start, "end": end})

        return chunks

    def _semantic_chunk(self, text: str) -> List[Dict[str, Any]]:
        """Semantic chunking - split on natural boundaries."""
        chunks = []

        # Split on double newlines (paragraphs)
        paragraphs = text.split("\n\n")

        current_chunk = ""
        current_start = 0

        for para in paragraphs:
            if len(current_chunk) + len(para) < self.config.chunk_size:
                if current_chunk:
                    current_chunk += "\n\n" + para
                else:
                    current_chunk = para
            else:
                if current_chunk:
                    start_pos = text.find(current_chunk)
                    chunks.append(
                        {
                            "text": current_chunk.strip(),
                            "start": start_pos,
                            "end": start_pos + len(current_chunk),
                        }
                    )
                current_chunk = para
                current_start = text.find(para)

        if current_chunk:
            start_pos = text.find(current_chunk)
            chunks.append(
                {
                    "text": current_chunk.strip(),
                    "start": start_pos,
                    "end": start_pos + len(current_chunk),
                }
            )

        # Merge very small chunks
        merged = []
        for chunk in chunks:
            if merged and len(chunk["text"]) < self.config.min_chunk_size:
                merged[-1]["text"] += "\n\n" + chunk["text"]
                merged[-1]["end"] = chunk["end"]
            else:
                merged.append(chunk)

        return merged


def chunk_content(
    content: str,
    query: str,
    url: str = "",
    title: str = "",
    strategy: str = "semantic",
    relevance_threshold: float = 0.3,
) -> List[Chunk]:
    """Convenience function for chunking."""
    config = ChunkingConfig(
        strategy=strategy,
        relevance_threshold=relevance_threshold,
    )
    processor = ChunkProcessor(config)
    return processor.process(content, query, url, title)
