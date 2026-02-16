"""Tests for content chunking module."""

import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from denis_unified_v1.actions.content_chunker import (
    Chunk,
    ChunkingConfig,
    ChunkProcessor,
    ContentExtractor,
    RelevanceScorer,
    chunk_content,
)


def test_content_extractor_from_html():
    """Test HTML extraction."""
    html = """
    <html>
    <head><title>Test</title></head>
    <body>
    <nav>Navigation</nav>
    <main>
    <h1>Hello World</h1>
    <p>This is a test paragraph with important content.</p>
    </main>
    <footer>Copyright 2024</footer>
    </body>
    </html>
    """
    extractor = ContentExtractor()
    text = extractor.extract_from_html(html)
    assert "Hello World" in text
    assert "test paragraph" in text
    assert "Navigation" not in text
    assert "Copyright" not in text


def test_content_extractor_code_blocks():
    """Test code block extraction."""
    text = """
    Here is some code:
    ```python
    def hello():
        print('Hello')
    ```
    And some inline `code` here.
    """
    extractor = ContentExtractor()
    chunks = extractor.extract_code_blocks(text)

    assert len(chunks) >= 1
    assert any(c.is_code for c in chunks)
    assert any("def hello" in c.text for c in chunks if c.is_code)


def test_relevance_scorer():
    """Test relevance scoring."""
    scorer = RelevanceScorer()

    chunk = Chunk(
        text="Python is a programming language used for data science and machine learning"
    )
    score = scorer.score(chunk, "python machine learning")

    assert score > 0.3


def test_semantic_chunking():
    """Test semantic chunking strategy."""
    config = ChunkingConfig(strategy="semantic", chunk_size=100)
    processor = ChunkProcessor(config)

    text = "First paragraph with content. Second paragraph here. Third paragraph now."
    chunks = processor._semantic_chunk(text)

    assert len(chunks) > 0


def test_fixed_chunking():
    """Test fixed-size chunking."""
    config = ChunkingConfig(strategy="fixed", chunk_size=50)
    processor = ChunkProcessor(config)

    text = "A" * 200
    chunks = processor._fixed_chunk(text)

    assert len(chunks) > 1


def test_chunk_content_function():
    """Test convenience function."""
    chunks = chunk_content(
        "Python is great. JavaScript is popular.",
        query="python programming",
        relevance_threshold=0.1,
    )

    assert len(chunks) > 0
    assert all(c.relevance_score >= 0.1 for c in chunks)


def test_code_chunks():
    """Test that code blocks get high scores."""
    html = """
    <html><body>
    <pre><code>def process():
        return True</code></pre>
    <p>Some text about python programming.</p>
    </body></html>
    """

    config = ChunkingConfig(extract_code=True, relevance_threshold=0.1)
    processor = ChunkProcessor(config)
    chunks = processor.process(html, "python", "http://example.com")

    code_chunks = [c for c in chunks if c.is_code]
    assert len(code_chunks) > 0
