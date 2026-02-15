"""Core tool implementations for the Executor.

Local-first tools that action plans can invoke. Each tool is a callable
that accepts **kwargs and returns a string result. The executor maps
tool_call.name -> function from this registry.

Security: these run locally on the user's machine. The action_authorizer
gate (not yet wired) will eventually control which tools can be invoked
based on confidence band and risk level.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any


# Default working directory for all tools
_WORK_DIR = Path(
    os.getenv(
        "DENIS_WORK_DIR",
        "/media/jotah/SSD_denis/home_jotah/denis_unified_v1",
    )
)

# Safety limits
_MAX_OUTPUT_CHARS = 8000
_COMMAND_TIMEOUT_SEC = 30


def list_files(pattern: str = "*", directory: str = ".") -> str:
    """List files matching a glob pattern.

    Args:
        pattern: Glob pattern (e.g., "*test*.py", "*.md").
        directory: Subdirectory to search in (relative to work dir).
    """
    search_dir = _WORK_DIR / directory
    if not search_dir.exists():
        return f"directory_not_found: {directory}"

    matches = sorted(search_dir.glob(pattern))
    if not matches:
        return "no_files_found"

    lines = [str(m.relative_to(_WORK_DIR)) for m in matches[:100]]
    result = "\n".join(lines)
    if len(matches) > 100:
        result += f"\n... and {len(matches) - 100} more files"
    return result


def grep_search(pattern: str, path: str = ".", glob: str = "") -> str:
    """Search for a regex pattern in files using grep.

    Args:
        pattern: Regex pattern to search for.
        path: Directory or file to search in (relative to work dir).
        glob: Optional file glob filter (e.g., "*.py").
    """
    cmd = ["grep", "-rn", "--color=never", "-I"]
    if glob:
        cmd.extend(["--include", glob])
    cmd.extend([pattern, str(_WORK_DIR / path)])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_COMMAND_TIMEOUT_SEC,
            cwd=str(_WORK_DIR),
        )
        output = result.stdout.strip()
        if not output:
            return "no_matches_found"
        return _truncate(output)
    except subprocess.TimeoutExpired:
        return "grep_timeout"
    except Exception as e:
        return f"grep_error: {e}"


def read_file(path: str, max_lines: int = 200) -> str:
    """Read contents of a file.

    Args:
        path: File path (relative to work dir).
        max_lines: Maximum number of lines to return.
    """
    file_path = _WORK_DIR / path
    if not file_path.exists():
        return f"file_not_found: {path}"
    if not file_path.is_file():
        return f"not_a_file: {path}"

    try:
        text = file_path.read_text(errors="replace")
        lines = text.splitlines()
        if len(lines) > max_lines:
            return "\n".join(lines[:max_lines]) + f"\n... truncated ({len(lines)} total lines)"
        return text
    except Exception as e:
        return f"read_error: {e}"


def run_command(cmd: str) -> str:
    """Run a shell command and return its output.

    Args:
        cmd: Shell command to execute.
    """
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=_COMMAND_TIMEOUT_SEC,
            cwd=str(_WORK_DIR),
        )
        output = result.stdout.strip()
        if result.returncode != 0:
            error = result.stderr.strip()
            output = f"exit_code={result.returncode}\n{output}\nSTDERR: {error}"
        return _truncate(output) if output else f"exit_code={result.returncode}"
    except subprocess.TimeoutExpired:
        return "command_timeout"
    except Exception as e:
        return f"command_error: {e}"


def _truncate(text: str) -> str:
    """Truncate output to safety limit."""
    if len(text) > _MAX_OUTPUT_CHARS:
        return text[:_MAX_OUTPUT_CHARS] + f"\n... truncated ({len(text)} chars total)"
    return text


def build_tool_registry() -> dict[str, Any]:
    """Build the default tool registry for the Executor.

    Returns a dict mapping tool_name -> callable(**kwargs) -> str.
    """
    return {
        "list_files": list_files,
        "grep_search": grep_search,
        "read_file": read_file,
        "run_command": run_command,
    }
