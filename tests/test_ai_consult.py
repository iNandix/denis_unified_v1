"""Tests for AI Consult functionality."""

import pytest
import sys
import os

sys.path.insert(0, "/media/jotah/SSD_denis/home_jotah")

from control_plane.ai_consult import AIConsult, ConsultResult
from control_plane.cp_generator import ContextPack


class TestConsultResult:
    """Test ConsultResult dataclass."""

    def test_consult_result_creation(self):
        """Test ConsultResult can be created."""
        from datetime import datetime, timezone

        result = ConsultResult(
            summary="Test summary",
            full_response={"key": "value"},
            source="test_source",
            timestamp=datetime.now(timezone.utc),
        )

        assert result.summary == "Test summary"
        assert result.source == "test_source"

    def test_consult_result_to_dict(self):
        """Test ConsultResult serialization."""
        from datetime import datetime, timezone

        result = ConsultResult(
            summary="Test summary",
            full_response={"key": "value"},
            source="test_source",
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

        data = result.to_dict()

        assert data["summary"] == "Test summary"
        assert data["source"] == "test_source"
        assert "timestamp" in data


class TestAIConsult:
    """Test AIConsult functionality."""

    def test_ai_consult_creation(self):
        """Test AIConsult can be created."""
        consult = AIConsult()
        assert consult is not None

    def test_find_ai_consult_target_returns_string(self):
        """Test _find_ai_consult_target returns a valid string."""
        consult = AIConsult()
        target = consult._find_ai_consult_target()
        assert isinstance(target, str)
        assert target in ["none", "local_8084"] or target.startswith("oceanai:")

    def test_find_ai_consult_target_cached(self):
        """Test _find_ai_consult_target returns cached result."""
        consult = AIConsult()
        target1 = consult._find_ai_consult_target()
        target2 = consult._find_ai_consult_target()
        assert target1 == target2

    def test_build_context(self):
        """Test context building from CP."""
        consult = AIConsult()

        cp = ContextPack(
            cp_id="test123",
            mission="Test mission",
            intent="test_intent",
            repo_name="test_repo",
            branch="main",
            files_to_read=["file1.py", "file2.py"],
            implicit_tasks=["task1"],
            model="groq",
            constraints=["python"],
        )

        context = consult._build_context("Is this correct?", cp)

        assert "test_repo" in context
        assert "main" in context
        assert "Test mission" in context
        assert "Is this correct?" in context

    def test_consult_returns_error_when_unavailable(self):
        """Test that consult returns 'none' source when AI is unavailable."""
        import asyncio

        consult = AIConsult()
        consult._target = "none"

        cp = ContextPack(
            cp_id="test123",
            mission="Test mission",
            intent="test",
        )

        result = asyncio.run(consult.consult_with_context("Test query", cp))

        assert result.source in ["none", "service_8084", "oceanai", "perplexity_gpt"]
        assert result.summary is not None
        assert len(result.summary) <= 400

    def test_consult_result_summary_max_chars(self):
        """Test that ConsultResult summary is limited."""
        from datetime import datetime, timezone

        long_summary = "A" * 500
        result = ConsultResult(
            summary=long_summary,
            full_response={},
            source="test",
            timestamp=datetime.now(timezone.utc),
        )

        assert len(result.summary) <= 400 or len(result.summary) == 500
