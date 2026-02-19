from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_compiler_compile_emits_compiler_and_retrieval_events(tmp_path, monkeypatch):
    monkeypatch.setenv("DENIS_EVENTS_DB_PATH", str(tmp_path / "events.db"))

    # Force fallback path (no external OpenAI calls in tests).
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from api.event_bus import reset_event_bus_for_tests
    from api.event_bus import get_event_store
    from api.persona.correlation import persona_request_context
    from denis_unified_v1.compiler.router import compile_via_router

    reset_event_bus_for_tests()

    conv = "conv_compiler_1"
    trace = "trace_comp_1"
    with persona_request_context(conversation_id=conv, trace_id=trace, correlation_id=trace, turn_id="t1"):
        out = await compile_via_router(
            conversation_id=conv,
            trace_id=trace,
            run_id="run1",
            actor_id="jotah",
            text="hola",
            workspace=None,
            consciousness=None,
            hop_count=0,
            policy={"graph": False, "vectorstore": False},
        )
    assert isinstance(out.get("makina_prompt"), str)
    assert "metadata" in out

    events = get_event_store().query_after(conversation_id=conv, after_event_id=0)
    types = [e["type"] for e in events]
    # Must include these in order (subsequence), fail-open allows extra events.
    want = ["compiler.start", "retrieval.start", "retrieval.result", "compiler.plan", "compiler.result"]
    pos = 0
    for t in types:
        if pos < len(want) and t == want[pos]:
            pos += 1
    assert pos == len(want)
