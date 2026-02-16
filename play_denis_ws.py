#!/usr/bin/env python3
import asyncio
import base64
import json
import os
import sys
import time
import websockets

WS_URL = os.getenv("DENIS_WS_URL", "ws://10.10.10.1:8084/chat")

DEFAULT_PROMPT = os.getenv(
    "DENIS_PROMPT", "Hola Denis, prueba de voz en streaming. Cuenta 1 a 5."
)


def eprint(*a):
    print(*a, file=sys.stderr, flush=True)


async def main():
    eprint(f"[ws] connecting: {WS_URL}")
    cancelled = set()
    current_audio_fmt = None
    got_any_audio = False
    last_audio_ts = None
    start_ts = time.time()

    async with websockets.connect(
        WS_URL, ping_interval=20, ping_timeout=20, max_size=50_000_000
    ) as ws:
        init_msg = {
            "type": "chat.request",
            "request_id": f"pc-audio-{int(time.time() * 1000)}",
            "payload": {
                "input_text": DEFAULT_PROMPT,
                "modalities": ["text", "voice"],
            },
        }
        await ws.send(json.dumps(init_msg))
        eprint("[ws] sent init request")

        while True:
            raw = await ws.recv()
            if isinstance(raw, bytes):
                eprint(f"[ws] got unexpected binary frame: {len(raw)} bytes")
                continue

            try:
                evt = json.loads(raw)
            except Exception:
                eprint("[ws] non-json frame:", raw[:200])
                continue

            etype = evt.get("type")
            rid = evt.get("request_id")
            payload = evt.get("payload") or {}

            if etype in ("render.text.delta", "render.text.final"):
                txt = payload.get("text") or payload.get("delta") or ""
                if txt:
                    eprint(f"[text] {txt}")

            elif etype == "render.voice.cancelled":
                if rid:
                    cancelled.add(rid)
                eprint(f"[voice] CANCELLED rid={rid} -> ignore future deltas")

            elif etype == "render.voice.delta":
                if rid and rid in cancelled:
                    continue

                enc = payload.get("encoding")
                sr = payload.get("sample_rate")
                ch = payload.get("channels")
                b64 = payload.get("audio_b64")

                if not b64:
                    continue

                if enc != "pcm_s16le":
                    eprint(
                        f"[voice] unexpected encoding={enc} (expected pcm_s16le). Drop."
                    )
                    continue

                fmt = (enc, sr, ch)
                if current_audio_fmt is None:
                    current_audio_fmt = fmt
                    eprint(f"[voice] first audio fmt: encoding={enc} sr={sr} ch={ch}")
                    eprint("[voice] NOTE: ensure ffplay args match sr/ch")

                elif fmt != current_audio_fmt:
                    eprint(f"[voice] WARNING fmt changed {current_audio_fmt} -> {fmt}")

                try:
                    pcm = base64.b64decode(b64, validate=True)
                except Exception:
                    eprint("[voice] base64 decode failed; drop chunk")
                    continue

                sys.stdout.buffer.write(pcm)
                sys.stdout.buffer.flush()

                got_any_audio = True
                last_audio_ts = time.time()

            elif etype == "render.outcome":
                eprint(f"[outcome] {json.dumps(payload, ensure_ascii=False)}")
                break

            else:
                if etype:
                    eprint(f"[evt] {etype}")

            if not got_any_audio and (time.time() - start_ts) > 3.0:
                eprint("[diag] 3s and still no audio. Check:")
                eprint("       - server emits render.voice.delta?")
                eprint("       - payload.audio_b64 present?")
                eprint("       - encoding/sample_rate/channels match ffplay args?")
                got_any_audio = True

        try:
            sys.stdout.buffer.flush()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
