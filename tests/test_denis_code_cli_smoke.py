"""Tests for Denis Code CLI."""

import pytest
from denis_unified_v1.cli.tool_schema import DenisResponse, ToolCall


def test_tool_schema():
    """Test schema validation."""
    data = {
        "assistant_message": "Testing",
        "tool_calls": [
            {
                "tool": "read_file",
                "args": {"path": "test.py"},
                "rationale": "Need to read",
                "risk_level": "low"
            }
        ],
        "done": True
    }
    resp = DenisResponse(**data)
    assert resp.assistant_message == "Testing"
    assert len(resp.tool_calls) == 1
    assert resp.done is True


def test_workspace_detection():
    """Test workspace detection (mock)."""
    # Mock test
    pass
