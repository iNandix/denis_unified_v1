"""E2E WebSocket test: voice request with barge-in (client.interrupt).

Verifies:
  1. WS /chat accepts connection
  2. voice_enabled=true produces render.text.delta + render.voice.delta events
  3. client.interrupt mid-stream produces render.voice.cancelled
  4. render.outcome has cancelled=true (or false if interrupt missed the window)
  5. Neo4j VoiceRequest + VoiceOutcome are projected correctly
  6. bytes_streamed stops growing after cancel

Prerequisites:
  - service_8084.py running on localhost:8084
  - Piper TTS on 10.10.10.2:8005
  - Neo4j on bolt://localhost:7687

Run:
    NEO4J_PASSWORD='Leon1234$' python3 -m denis_unified_v1.tests.test_ws_bargein_e2e
"""

import asyncio
import json
import os
import time

import websockets


PERSONA_URL = os.getenv("PERSONA_WS_URL", "ws://localhost:8084/chat")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "Leon1234$")

# How long to wait before sending interrupt (seconds)
INTERRUPT_DELAY = 1.5
# Max wait for the full exchange
TIMEOUT = 20


async def run_bargein_test():
    request_id = f"bargein_test_{int(time.time())}"
    events_received = []
    voice_deltas_before_cancel = 0
    voice_deltas_after_cancel = 0
    got_cancelled = False
    got_outcome = False
    outcome_payload = {}
    cancel_sent = False

    print(f"Request ID: {request_id}")
    print(f"Connecting to {PERSONA_URL} ...")

    try:
        async with websockets.connect(PERSONA_URL, close_timeout=5) as ws:
            print("Connected.")

            # Send chat with voice_enabled
            msg = json.dumps({
                "message": "Cuéntame una historia larga sobre un dragón que vivía en una montaña muy alta y tenía muchos amigos en el bosque cercano.",
                "voice_enabled": True,
                "request_id": request_id,
                "user_id": "test_bargein",
            })
            await ws.send(msg)
            print(f"Sent request: voice_enabled=true")

            # Schedule interrupt after delay
            async def send_interrupt():
                nonlocal cancel_sent
                await asyncio.sleep(INTERRUPT_DELAY)
                interrupt = json.dumps({
                    "type": "client.interrupt",
                    "request_id": request_id,
                })
                await ws.send(interrupt)
                cancel_sent = True
                print(f">>> Sent client.interrupt after {INTERRUPT_DELAY}s")

            interrupt_task = asyncio.create_task(send_interrupt())

            # Collect events until outcome or timeout
            deadline = time.time() + TIMEOUT
            while time.time() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                except asyncio.TimeoutError:
                    if got_outcome:
                        break
                    continue

                ev = json.loads(raw)
                ev_type = ev.get("type", "unknown")
                events_received.append(ev_type)

                if ev_type == "render.voice.delta":
                    if cancel_sent:
                        voice_deltas_after_cancel += 1
                    else:
                        voice_deltas_before_cancel += 1

                elif ev_type == "render.voice.cancelled":
                    got_cancelled = True
                    print(f"  <<< render.voice.cancelled: {ev.get('payload', {})}")

                elif ev_type == "render.outcome":
                    got_outcome = True
                    outcome_payload = ev.get("payload", {})
                    print(f"  <<< render.outcome: {json.dumps(outcome_payload, indent=2)}")
                    break

            interrupt_task.cancel()

    except ConnectionRefusedError:
        print("ERROR: Cannot connect to service_8084. Is it running?")
        return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False

    # Report
    print()
    print("=" * 50)
    print("  RESULTS")
    print("=" * 50)

    checks = []

    # Check 1: Got text events
    text_events = [e for e in events_received if e == "render.text.delta"]
    ok = len(text_events) > 0
    checks.append(("render.text.delta received", ok, f"count={len(text_events)}"))

    # Check 2: Got voice deltas before cancel
    ok = voice_deltas_before_cancel > 0
    checks.append(("render.voice.delta before cancel", ok, f"count={voice_deltas_before_cancel}"))

    # Check 3: Got cancelled event
    checks.append(("render.voice.cancelled received", got_cancelled, ""))

    # Check 4: voice_deltas_after_cancel is small (barge-in stopped streaming)
    ok = voice_deltas_after_cancel <= 2  # allow 1-2 in-flight
    checks.append(("voice deltas stopped after cancel", ok, f"after_cancel={voice_deltas_after_cancel}"))

    # Check 5: outcome received
    checks.append(("render.outcome received", got_outcome, ""))

    # Check 6: outcome shows cancelled (if we actually cancelled in time)
    if got_cancelled:
        ok = outcome_payload.get("voice_cancelled", False) is True
        checks.append(("outcome.voice_cancelled=true", ok, f"got={outcome_payload.get('voice_cancelled')}"))

    # Check 7: Neo4j projection
    neo4j_ok = False
    try:
        from denis_unified_v1.connections import get_neo4j_driver
        driver = get_neo4j_driver()
        if driver:
            with driver.session() as session:
                r = session.run(
                    "MATCH (r:VoiceRequest {id:$rid})-[:HAS_OUTCOME]->(o:VoiceOutcome) "
                    "RETURN r.voice_enabled AS voice, o.voice_ttfc_ns AS ttfc_ns, "
                    "o.bytes_streamed AS bytes, o.cancelled AS cancelled, o.tts_backend AS backend",
                    rid=request_id,
                ).single()
                if r:
                    neo4j_ok = True
                    checks.append(("Neo4j: VoiceRequest+Outcome projected", True,
                                   f"ttfc_ns={r['ttfc_ns']}, bytes={r['bytes']}, cancelled={r['cancelled']}, backend={r['backend']}"))

                    # Check steps
                    s = session.run(
                        "MATCH (r:VoiceRequest {id:$rid})-[:HAS_STEP]->(s:ToolchainStep) "
                        "RETURN count(s) AS steps",
                        rid=request_id,
                    ).single()
                    if s:
                        checks.append(("Neo4j: ToolchainSteps linked", s["steps"] > 0, f"count={s['steps']}"))
                else:
                    checks.append(("Neo4j: VoiceRequest+Outcome projected", False, "not found"))
    except Exception as e:
        checks.append(("Neo4j: VoiceRequest+Outcome projected", False, str(e)))

    # Print results
    passed = 0
    failed = 0
    for desc, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1
        suffix = f" ({detail})" if detail else ""
        print(f"  [{'PASS' if ok else 'FAIL'}] {desc}{suffix}")

    print()
    print(f"  {passed} passed, {failed} failed")
    print("=" * 50)

    # Don't cleanup - leave data for inspection
    if neo4j_ok:
        print()
        print("Neo4j inspection queries:")
        print(f"  MATCH (r:VoiceRequest {{id:'{request_id}'}})-[:HAS_OUTCOME]->(o) RETURN r, o;")
        print(f"  MATCH (r:VoiceRequest {{id:'{request_id}'}})-[:HAS_STEP]->(s) RETURN s ORDER BY s.segment_idx;")

    return failed == 0


def main():
    ok = asyncio.run(run_bargein_test())
    exit(0 if ok else 1)


if __name__ == "__main__":
    main()
