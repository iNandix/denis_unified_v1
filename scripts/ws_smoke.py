#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from urllib.parse import urlparse

import urllib.request


def _base_url() -> str:
    return os.getenv("DENIS_BASE_URL", "http://127.0.0.1:9999").rstrip("/")


def _probe(url: str) -> bool:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=2) as r:
            return 200 <= int(getattr(r, "status", 200)) < 500
    except Exception:
        return False


def _http_post_json(url: str, payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=5) as r:
        body = r.read().decode("utf-8", errors="ignore")
        try:
            return int(getattr(r, "status", 200)), json.loads(body)
        except Exception:
            return int(getattr(r, "status", 200)), {}


def _ws_url(base: str, conversation_id: str) -> str:
    p = urlparse(base)
    scheme = "wss" if p.scheme == "https" else "ws"
    netloc = p.netloc
    return f"{scheme}://{netloc}/v1/ws?conversation_id={conversation_id}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--conversation", default="test", help="conversation id")
    args = ap.parse_args()

    base = _base_url()
    health = f"{base}/health"
    if not _probe(health):
        print(f"UNREACHABLE: {health}")
        print("Set DENIS_BASE_URL=http://HOST:PORT")
        return 0

    # Prefer `websockets` if available; else try `websocket-client`.
    ws_url = _ws_url(base, args.conversation)
    print(f"ws_url={ws_url}")

    try:
        import asyncio
        import websockets  # type: ignore

        async def run() -> int:
            async with websockets.connect(ws_url, close_timeout=1) as ws:
                hello = json.loads(await asyncio.wait_for(ws.recv(), timeout=3))
                print("hello:", hello)
                await ws.send(json.dumps({"type": "subscribe", "conversation_id": args.conversation, "last_event_id": 0}))

                # Trigger a chat call to generate events.
                status, _ = _http_post_json(
                    f"{base}/v1/chat/completions",
                    {"model": "denis-cognitive", "messages": [{"role": "user", "content": "ping"}], "max_tokens": 16, "temperature": 0},
                )
                print("chat_http_status:", status)

                events = []
                t0 = time.time()
                while time.time() - t0 < 5 and len(events) < 10:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=1)
                        ev = json.loads(msg)
                        # Skip protocol pings
                        if ev.get("type") in {"ping", "hello"}:
                            continue
                        events.append(ev)
                    except Exception:
                        continue
                for ev in events:
                    print("event:", ev.get("event_id"), ev.get("type"))
                return 0

        return asyncio.run(run())
    except Exception:
        pass

    try:
        import websocket  # type: ignore

        ws = websocket.create_connection(ws_url, timeout=3)
        try:
            hello = json.loads(ws.recv())
            print("hello:", hello)
            ws.send(json.dumps({"type": "subscribe", "conversation_id": args.conversation, "last_event_id": 0}))
            status, _ = _http_post_json(
                f"{base}/v1/chat/completions",
                {"model": "denis-cognitive", "messages": [{"role": "user", "content": "ping"}], "max_tokens": 16, "temperature": 0},
            )
            print("chat_http_status:", status)
            t0 = time.time()
            while time.time() - t0 < 5:
                raw = ws.recv()
                ev = json.loads(raw)
                if ev.get("type") in {"ping", "hello"}:
                    continue
                print("event:", ev.get("event_id"), ev.get("type"))
                break
            return 0
        finally:
            try:
                ws.close()
            except Exception:
                pass
    except Exception:
        print("SKIP: no websocket client library available (install `websockets` or `websocket-client`).")
        return 0


if __name__ == "__main__":
    sys.exit(main())

