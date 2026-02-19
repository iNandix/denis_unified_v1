from __future__ import annotations

import pytest

from denis_unified_v1.chat_cp.contracts import ChatMessage, ChatRequest


def test_contract_validation():
    req = ChatRequest(
        messages=[ChatMessage(role="user", content="hello")],
        response_format="text",
        temperature=0.1,
        max_output_tokens=32,
        task_profile_id="control_plane_chat",
    )
    assert req.task_profile_id == "control_plane_chat"
    assert req.messages[0].role == "user"


def test_contract_json_mode():
    req = ChatRequest(
        messages=[ChatMessage(role="user", content="return json")],
        response_format="json",
        task_profile_id="control_plane_chat",
    )
    assert req.response_format == "json"


@pytest.mark.parametrize("role", ["tool", "developer", "invalid"])
def test_contract_invalid_role(role: str):
    with pytest.raises(ValueError):
        ChatRequest(
            messages=[ChatMessage(role=role, content="x")],  # type: ignore[arg-type]
            task_profile_id="control_plane_chat",
        )
