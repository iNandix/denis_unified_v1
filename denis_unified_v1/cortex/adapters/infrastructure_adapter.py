"""Infrastructure adapter for node health checks and minimal remote actions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import os
import shlex
import socket
from typing import Any

from denis_unified_v1.cortex.world_interface import BaseAdapter


@dataclass(frozen=True)
class NodeTarget:
    name: str
    host: str
    tailscale_ip: str | None = None
    tailscale_name: str | None = None


def _default_nodes() -> dict[str, NodeTarget]:
    return {
        "node1": NodeTarget(
            name="node1",
            host=os.getenv("DENIS_NODE1_HOST", "10.10.10.1"),
            tailscale_ip=os.getenv("DENIS_NODE1_TAILSCALE", "100.86.69.108"),
            tailscale_name=os.getenv("DENIS_NODE1_TAILSCALE_NAME", "node1"),
        ),
        "node2": NodeTarget(
            name="node2",
            host=os.getenv("DENIS_NODE2_HOST", "10.10.10.2"),
            tailscale_ip=os.getenv("DENIS_NODE2_TAILSCALE", "100.93.192.27"),
            tailscale_name=os.getenv("DENIS_NODE2_TAILSCALE_NAME", "node2"),
        ),
        "node3": NodeTarget(
            name="node3",
            host=os.getenv("DENIS_NODE3_HOST", "10.10.10.3"),
            tailscale_ip=os.getenv("DENIS_NODE3_TAILSCALE"),
            tailscale_name=os.getenv("DENIS_NODE3_TAILSCALE_NAME", "node3"),
        ),
        "nodomac": NodeTarget(
            name="nodomac",
            host=os.getenv("DENIS_NODOMAC_HOST", "192.168.1.65"),
            tailscale_ip=os.getenv("DENIS_NODOMAC_TAILSCALE", "100.117.11.87"),
            tailscale_name=os.getenv("DENIS_NODOMAC_TAILSCALE_NAME", "nodoMac"),
        ),
    }


def _get_ssh_pass(host: str) -> str | None:
    key = f"DENIS_SSH_PASS_{host.replace('.', '_').replace('-', '_')}"
    return os.getenv(key) or os.getenv("DENIS_SSH_PASS_DEFAULT")


async def _get_tailscale_status() -> dict[str, Any]:
    """Get current tailscale status for all peers."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "tailscale",
            "status",
            "--json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {}
        if proc.returncode == 0:
            return json.loads(stdout.decode("utf-8", errors="replace"))
    except Exception:
        pass
    return {}


class InfrastructureAdapter(BaseAdapter):
    name = "infrastructure"

    def __init__(self) -> None:
        self.nodes = _default_nodes()

    def _prefer_tailscale(self) -> bool:
        return os.getenv("DENIS_PREFER_TAILSCALE", "true").strip().lower() == "true"

    async def refresh_tailscale_ips(self) -> dict[str, str]:
        """Refresh tailscale IPs from local `tailscale status --json`."""
        ts_status = await _get_tailscale_status()
        peers = ts_status.get("Peer", {})
        if not isinstance(peers, dict):
            return {}

        host_to_ip: dict[str, str] = {}
        for peer in peers.values():
            if not isinstance(peer, dict):
                continue
            host_name = str(peer.get("HostName") or "").strip()
            if not host_name:
                continue
            ips = peer.get("TailscaleIPs") or []
            if not isinstance(ips, list) or not ips:
                continue
            ip = str(ips[0]).strip()
            if not ip:
                continue
            host_to_ip[host_name.lower()] = ip

        updated: dict[str, str] = {}
        for node_id, node in list(self.nodes.items()):
            ts_name = (node.tailscale_name or "").strip().lower()
            if not ts_name:
                continue
            new_ip = host_to_ip.get(ts_name)
            if not new_ip or new_ip == node.tailscale_ip:
                continue
            self.nodes[node_id] = NodeTarget(
                name=node.name,
                host=node.host,
                tailscale_ip=new_ip,
                tailscale_name=node.tailscale_name,
            )
            updated[node_id] = new_ip
        return updated

    async def _run_cmd(self, args: list[str], timeout_sec: int = 5) -> dict[str, Any]:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_sec
            )
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
            node = self.nodes[entity_id]
            if self._prefer_tailscale() and node.tailscale_ip:
                return node.tailscale_ip
            return node.host
        if entity_id.startswith("node") and entity_id[4:].isdigit():
            key = entity_id
            if key in self.nodes:
                node = self.nodes[key]
                if self._prefer_tailscale() and node.tailscale_ip:
                    return node.tailscale_ip
                return node.host
        return entity_id

    async def perceive(self, entity_id: str, **kwargs: Any) -> dict[str, Any]:
        host = self._resolve_host(entity_id)
        node = self.nodes.get(entity_id)
        static_host = node.host if node else host
        tailscale_ip = node.tailscale_ip if node else None
        ping = await self._run_cmd(["ping", "-c", "1", "-W", "1", host], timeout_sec=3)

        local_hosts = {
            "127.0.0.1",
            "localhost",
            socket.gethostname(),
            socket.gethostbyname(socket.gethostname()),
        }
        is_local = host in local_hosts or host == socket.gethostname()

        if is_local:
            ssh = {
                "ok": False,
                "exit_code": -1,
                "stdout": "skipped (local node)",
                "stderr": "",
                "cmd": "ssh (skipped for local)",
            }
        else:
            ssh_pass = _get_ssh_pass(host)
            if ssh_pass:
                ssh = await self._run_cmd(
                    [
                        "sshpass",
                        "-p",
                        ssh_pass,
                        "ssh",
                        "-o",
                        "BatchMode=no",
                        "-o",
                        "ConnectTimeout=3",
                        host,
                        "uname -a",
                    ],
                    timeout_sec=5,
                )
            else:
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
                "static_host": static_host,
                "tailscale_ip": tailscale_ip,
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
