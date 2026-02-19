from __future__ import annotations


def test_graph_guardrails_drop_denied_keys_and_truncate(monkeypatch):
    monkeypatch.setenv("MAX_STR_LEN_GRAPH", "16")
    monkeypatch.setenv("DENY_KEYS_GRAPH", "prompt,token,secret,authorization,content")

    from denis_unified_v1.guardrails.graph_write_policy import sanitize_graph_props

    res = sanitize_graph_props(
        {
            "ok": "short",
            "prompt": "THIS MUST DROP",
            "authorization_header": "Bearer abc.def.ghi",
            "big": "x" * 200,
            "nested": {"a": 1, "b": 2},
        }
    )

    props = res.props
    assert "prompt" not in props
    assert "authorization_header" not in props
    assert "ok" in props and props["ok"] == "short"
    assert "big" in props and isinstance(props["big"], str) and len(props["big"]) <= 16
    # Non-scalars are stringified (capped).
    assert "nested" in props and isinstance(props["nested"], str)
    # Guardrails metadata present when violations occur.
    assert props.get("_guardrails_violations", 0) >= 1


def test_event_guardrails_drop_denied_keys(monkeypatch):
    monkeypatch.setenv("DENY_KEYS_EVENT", "prompt,token,secret,authorization,content")
    monkeypatch.setenv("MAX_STR_LEN_EVENT", "32")

    from denis_unified_v1.guardrails.event_payload_policy import sanitize_event_payload

    out = sanitize_event_payload(
        {
            "content": "should drop",
            "token": "should drop",
            "safe": "hello",
            "big": "y" * 200,
        }
    ).payload
    assert "content" not in out
    assert "token" not in out
    assert out.get("safe") == "hello"
    assert isinstance(out.get("big"), str) and len(out["big"]) <= 32

