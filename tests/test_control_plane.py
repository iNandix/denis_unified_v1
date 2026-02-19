"""Tests for Control Plane CPGenerator and ContextPack."""

import pytest
import sys
import os

sys.path.insert(0, "/media/jotah/SSD_denis/home_jotah")

from control_plane.cp_generator import CPGenerator, ContextPack
from control_plane.repo_context import RepoContext


class TestCPGenerator:
    """Test CPGenerator functionality."""

    def test_from_agent_result_creates_valid_cp(self):
        """Test that from_agent_result creates a valid ContextPack."""
        generator = CPGenerator()

        result = {
            "intent": "implement_feature",
            "files_touched": ["kernel/ghost_ide/context_harvester.py"],
            "constraints": ["python", "neo4j"],
            "mission_completed": "bricks completos",
            "success": True,
        }

        cp = generator.from_agent_result(result)

        assert cp is not None
        assert cp.cp_id is not None
        assert cp.mission is not None
        assert cp.intent == "implement_feature"
        assert cp.model is not None

    def test_from_agent_result_with_repo_info(self):
        """Test from_agent_result with explicit repo info."""
        generator = CPGenerator()

        result = {
            "intent": "debug_repo",
            "files_touched": ["src/main.py"],
            "constraints": ["python"],
            "mission": "Fix bug in main",
            "success": True,
            "repo_id": "test123",
            "repo_name": "test_repo",
            "branch": "main",
        }

        cp = generator.from_agent_result(result)

        assert cp.repo_id is not None
        assert cp.repo_name is not None
        assert cp.branch is not None

    def test_from_manual_creates_valid_cp(self):
        """Test that from_manual creates a valid ContextPack."""
        generator = CPGenerator()

        cp = generator.from_manual(
            mission="Test mission",
            cwd="/media/jotah/SSD_denis/home_jotah/denis_unified_v1",
        )

        assert cp is not None
        assert cp.cp_id is not None
        assert cp.mission == "Test mission"
        assert cp.source == "manual"

    def test_intent_next_map(self):
        """Test intent prediction mapping."""
        generator = CPGenerator()

        result = {"intent": "implement_feature", "mission": "test"}
        next_intent = generator._predict_next_intent(result)
        assert next_intent == "run_tests_ci"

        result = {"intent": "debug_repo", "mission": "test"}
        next_intent = generator._predict_next_intent(result)
        assert next_intent == "explain_concept"


class TestContextPack:
    """Test ContextPack dataclass."""

    def test_context_pack_to_dict(self):
        """Test ContextPack serialization."""
        cp = ContextPack(
            cp_id="test123",
            mission="Test mission",
            intent="test",
        )

        data = cp.to_dict()

        assert data["cp_id"] == "test123"
        assert data["mission"] == "Test mission"
        assert "generated_at" in data
        assert "expires_at" in data

    def test_context_pack_from_dict(self):
        """Test ContextPack deserialization."""
        data = {
            "cp_id": "test456",
            "mission": "Loaded mission",
            "intent": "test",
            "repo_name": "test_repo",
            "branch": "main",
        }

        cp = ContextPack.from_dict(data)

        assert cp.cp_id == "test456"
        assert cp.mission == "Loaded mission"

    def test_context_pack_is_expired(self):
        """Test expiration check."""
        from datetime import datetime, timedelta, timezone

        cp = ContextPack(
            cp_id="expired",
            mission="test",
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=10),
        )

        assert cp.is_expired() is True

        cp2 = ContextPack(
            cp_id="not_expired",
            mission="test",
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=120),
        )

        assert cp2.is_expired() is False


class TestRepoContext:
    """Test RepoContext functionality."""

    def test_repo_context_creation(self):
        """Test RepoContext can be created."""
        repo = RepoContext(cwd="/media/jotah/SSD_denis/home_jotah/denis_unified_v1")

        assert repo.git_root is not None
        assert repo.repo_id is not None

    def test_repo_context_to_dict(self):
        """Test RepoContext serialization."""
        repo = RepoContext(cwd="/media/jotah/SSD_denis/home_jotah/denis_unified_v1")

        data = repo.to_dict()

        assert "repo_id" in data
        assert "repo_name" in data
        assert "branch" in data
