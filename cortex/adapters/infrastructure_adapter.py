"""Infrastructure adapter for node health checks and minimal remote actions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import os
import shlex
from typing import Any

from denis_unified_v1.cortex.world_interface import BaseAdapter


@dataclass(frozen=True)
class NodeTarget:
    name: str
    host: str


def _default_nodes() -> dict[str, NodeTarget]:
    return {
        "node1": NodeTarget(name="node1", host=os.getenv("DENIS_NODE1_HOST", "10.10.10.1")),
        "node2": NodeTarget(name="node2", host=os.getenv("DENIS_NODE2_HOST", "10.10.10.2")),
        "node3": NodeTarget(name="node3", host=os.getenv("DENIS_NODE3_HOST", "10.10.10.3")),
    }


class InfrastructureAdapter(BaseAdapter):
    name = "infrastructure"

    def __init__(self) -> None:
        self.nodes = _default_nodes()

    async def _run_cmd(self, args: list[str], timeout_sec: int = 5) -> dict[str, Any]:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {
                "ok": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": "timeout",
                "cmd": " ".join(shlex.quote(x) for x in args),
            }
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": stdout.decode("utf-8", errors="replace").strip(),
            "stderr": stderr.decode("utf-8", errors="replace").strip(),
            "cmd": " ".join(shlex.quote(x) for x in args),
        }

    def _resolve_host(self, entity_id: str) -> str:
        if entity_id in self.nodes:
            return self.nodes[entity_id].host
        if entity_id.startswith("node") and entity_id[4:].isdigit():
            key = entity_id
            if key in self.nodes:
                return self.nodes[key].host
        return entity_id

    async def perceive(self, entity_id: str, **kwargs: Any) -> dict[str, Any]:
        host = self._resolve_host(entity_id)
        ping = await self._run_cmd(["ping", "-c", "1", "-W", "1", host], timeout_sec=3)
        ssh = await self._run_cmd(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=3",
                host,
                "uname -a",
            ],
            timeout_sec=5,
        )
        return {
            "status": "ok" if ping["ok"] else "error",
            "adapter": self.name,
            "entity_id": entity_id,
            "state": {
                "host": host,
                "ping_ok": ping["ok"],
                "ssh_ok": ssh["ok"],
                "ssh_uname": ssh["stdout"][:200],
            },
            "checks": {"ping": ping, "ssh_uname": ssh},
        }

    async def act(self, entity_id: str, action: str, **kwargs: Any) -> dict[str, Any]:
        host = self._resolve_host(entity_id)
        if action != "run_command":
            return {
                "status": "error",
                "adapter": self.name,
                "entity_id": entity_id,
                "action": action,
                "error": "unsupported_action",
                "supported_actions": ["run_command"],
            }
        command = str(kwargs.get("command") or "").strip()
        if not command:
            return {
                "status": "error",
                "adapter": self.name,
                "entity_id": entity_id,
                "action": action,
                "error": "missing_command",
            }

        out = await self._run_cmd(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=3",
                host,
                command,
            ],
            timeout_sec=int(kwargs.get("timeout_sec", 8)),
        )
        return {
            "status": "ok" if out["ok"] else "error",
            "adapter": self.name,
            "entity_id": entity_id,
            "action": action,
            "result": out,
        }

