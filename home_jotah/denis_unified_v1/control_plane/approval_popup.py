#!/usr/bin/env python3
"""
Approval Popup - Zenity-based approval dialog for Control Plane.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import threading
from datetime import datetime, timezone
from typing import Any, Optional, Tuple

from control_plane.ai_consult import AIConsult, ConsultResult
from control_plane.cp_generator import ContextPack

logger = logging.getLogger(__name__)


class ApprovalPopup:
    """Zenity-based approval popup for ContextPacks."""

    RETURN_APPROVED = 0
    RETURN_REJECTED = 1
    RETURN_EDIT = 2
    RETURN_TIMEOUT = 5

    def __init__(self):
        self._ai_consult = AIConsult()

    def _run_zenity(self, args: list, timeout: int = 120) -> Tuple[int, str]:
        """Run zenity command and return (returncode, output)."""
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")},
            )
            return result.returncode, result.stdout
        except subprocess.TimeoutExpired:
            return self.RETURN_TIMEOUT, ""
        except Exception as e:
            logger.error(f"Zenity error: {e}")
            return self.RETURN_REJECTED, ""

    def _notify(self, title: str, message: str, expire: int = 3000) -> None:
        """Show notification."""
        try:
            subprocess.Popen(
                ["notify-send", title, message, "--expire-time={}".format(expire)],
                env={**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")},
            )
        except Exception as e:
            logger.warning(f"notify-send failed: {e}")

    def _format_cp_text(self, cp: ContextPack) -> str:
        """Format ContextPack details for zenity display."""
        lines = []
        status_icon = "✅" if cp.success else "❌"
        lines.append(f"🎯 Intent:   {cp.intent} {status_icon}")
        lines.append(f"📋 Misión:   {cp.mission[:80]}")
        lines.append(f"🤖 Modelo:   {cp.model}")
        lines.append(f"🌿 Repo:     {cp.repo_name} · {cp.branch}")
        lines.append(f"🔑 CP ID:    {cp.cp_id}")
        lines.append("")
        if cp.files_touched:
            lines.append(f"✋ Archivos tocados ({len(cp.files_touched)}):")
            for f in cp.files_touched[:6]:
                lines.append(f"   · {f}")
            if len(cp.files_touched) > 6:
                lines.append(f"   · ... +{len(cp.files_touched) - 6} más")
            lines.append("")
        if cp.files_to_read:
            lines.append(f"📖 Archivos a leer ({len(cp.files_to_read)}):")
            for f in cp.files_to_read[:4]:
                lines.append(f"   · {f}")
            if len(cp.files_to_read) > 4:
                lines.append(f"   · ... +{len(cp.files_to_read) - 4} más")
            lines.append("")
        if cp.implicit_tasks:
            lines.append(f"⚙️  Tareas implícitas:")
            for t in cp.implicit_tasks[:4]:
                lines.append(f"   · {t}")
            lines.append("")
        if cp.constraints:
            lines.append(f"🔒 Constraints: {', '.join(cp.constraints)}")
            lines.append("")
        if cp.notes:
            lines.append(f"💬 Nota: {cp.notes[:100]}")
            lines.append("")
        lines.append(
            f"⏱️  Expira en 120s · {'✅ validado' if cp.human_validated else '⏳ pendiente'}"
        )
        return "\n".join(lines)

    def show_cp_approval(self, cp: ContextPack) -> Tuple[str, Optional[ConsultResult]]:
        """
        Show approval dialog for a ContextPack.

        Returns:
            ('approved'|'rejected'|'edit'|'timeout', ConsultResult|None)
        """
        self._notify("Denis", f"CP {cp.cp_id} pendiente de aprobación")

        text = self._format_cp_text(cp)

        args = [
            "zenity",
            "--forms",
            "--title=f'Denis · {cp.repo_name} · {cp.branch}'",
            f"--text={text}",
            "--add-entry=💬 Consultar antes de aprobar (opcional)",
            "--ok-label=Siguiente →",
            "--cancel-label=❌ Rechazar",
            "--extra-button=📂 Cargar otro CP",
            "--width=560",
            "--timeout=120",
        ]

        returncode, output = self._run_zenity(args)

        if returncode == self.RETURN_TIMEOUT:
            self._write_expired(cp)
            self._notify("❌ CP expirado", f"CP {cp.cp_id} rechazado por timeout")
            return "timeout", None

        if returncode == self.RETURN_REJECTED:
            return "rejected", None

        if returncode == 1 and "load_file" in output.lower():
            loaded_cp = load_cp_from_file()
            if loaded_cp:
                return self.show_cp_approval(loaded_cp)
            return self.show_cp_approval(cp)

        query = output.strip()

        if not query:
            returncode2, _ = self._run_zenity(
                [
                    "zenity",
                    "--question",
                    "--title=Denis · Aprobar",
                    f"--text=¿Aprobar CP {cp.cp_id}?",
                    "--ok-label=✅ Aprobar",
                    "--cancel-label=❌ Rechazar",
                    "--extra-button=✏️ Editar",
                    "--width=560",
                ]
            )
            if returncode2 == self.RETURN_APPROVED:
                cp.human_validated = True
                cp.validated_by = "human_direct"
                self._send_webhook(cp, "approved")
                return "approved", None
            elif returncode2 == 3:
                return self._handle_edit(cp)
            self._send_webhook(cp, "rejected")
            return "rejected", None

        self._notify("Denis", "🔍 Consultando...", expire=3000)

        consult_result = self._ai_consult.consult_with_context_sync(query, cp)

        returncode3, _ = self._run_zenity(
            [
                "zenity",
                "--question",
                f"--title=Denis · Respuesta · {consult_result.source}",
                f"--text=💬 {consult_result.summary}\n\n¿Aprobar CP con esta validación?",
                "--ok-label=✅ Aprobar",
                "--cancel-label=❌ Rechazar",
                "--extra-button=🔄 Otra consulta",
                "--width=560",
            ]
        )

        if returncode3 == self.RETURN_APPROVED:
            cp.notes = consult_result.summary
            cp.extra_context = consult_result.full_response
            cp.human_validated = True
            cp.validated_by = consult_result.source
            self._notify("✅ CP aprobado", f"{cp.repo_name} · {cp.intent}")
            self._send_webhook(cp, "approved")
            return "approved", consult_result
        elif returncode3 == 3:
            return self.show_cp_approval(cp)

        self._send_webhook(cp, "rejected")
        return "rejected", consult_result

    def _handle_edit(self, cp: ContextPack) -> Tuple[str, Optional[ConsultResult]]:
        """Handle edit flow."""
        edit_file = "/tmp/denis_cp_edit.json"
        with open(edit_file, "w") as f:
            json.dump(cp.to_dict(), f, indent=2)

        editor = os.environ.get("EDITOR", "gedit")
        subprocess.run(
            [editor, edit_file],
            env={**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")},
        )

        try:
            with open(edit_file, "r") as f:
                edited = json.load(f)
            return self.show_cp_approval(ContextPack.from_dict(edited))
        except Exception as e:
            logger.error(f"Error reading edited CP: {e}")
            return "rejected", None

    def _write_expired(self, cp: ContextPack) -> None:
        """Write expired CP to file."""
        expired_file = "/tmp/denis_cp_expired.json"
        with open(expired_file, "w") as f:
            json.dump(cp.to_dict(), f, indent=2)

    def _send_webhook(self, cp: ContextPack, decision: str) -> None:
        """Send webhook notification after approval/rejection."""
        webhook_url = os.environ.get("DENIS_CP_WEBHOOK")
        if not webhook_url:
            return

        payload = {
            "cp_id": cp.cp_id,
            "decision": decision,
            "intent": cp.intent,
            "repo_name": cp.repo_name,
            "branch": cp.branch,
            "validated_by": cp.validated_by or "human",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        def _async_post():
            try:
                import requests

                requests.post(webhook_url, json=payload, timeout=5)
            except Exception as e:
                logger.warning(f"Webhook failed: {e}")

        threading.Thread(target=_async_post, daemon=True).start()


def show_cp_approval(cp: ContextPack) -> Tuple[str, Optional[ConsultResult]]:
    """Convenience function."""
    popup = ApprovalPopup()
    return popup.show_cp_approval(cp)


def load_cp_from_file(initial_dir: str = "/tmp") -> Optional[ContextPack]:
    """
    Load a ContextPack from a JSON file using zenity file picker.

    Returns:
        ContextPack if loaded successfully, None if cancelled or invalid.
    """
    try:
        result = subprocess.run(
            [
                "zenity",
                "--file-selection",
                "--title=Denis · Cargar Context Pack",
                f"--filename={initial_dir}/",
                "--file-filter=JSON files | *.json",
                "--width=600",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            env={**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")},
        )

        if result.returncode != 0 or not result.stdout.strip():
            return None

        filepath = result.stdout.strip()

        with open(filepath, "r") as f:
            data = json.load(f)

        required_fields = ["mission", "intent", "files_to_read", "repo_name"]
        missing = [f for f in required_fields if f not in data or not data[f]]

        if missing:
            subprocess.run(
                [
                    "zenity",
                    "--error",
                    f"--text=❌ JSON inválido o campos faltantes: {', '.join(missing)}",
                ],
                env={**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")},
            )
            return None

        cp = ContextPack.from_dict(data)
        cp.source = "manual_file"
        cp.requires_human_approval = True
        cp.human_validated = False

        return cp

    except json.JSONDecodeError as e:
        subprocess.run(
            [
                "zenity",
                "--error",
                f"--text=❌ JSON inválido: {e}",
            ],
            env={**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")},
        )
        return None
    except Exception as e:
        logger.error(f"Error loading CP from file: {e}")
        return None


__all__ = ["ApprovalPopup", "show_cp_approval", "load_cp_from_file"]
