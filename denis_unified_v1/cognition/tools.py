"""Core tool implementations for the Executor.

Local-first tools that action plans can invoke. Each tool is a callable
that accepts **kwargs and returns a string result. The executor maps
tool_call.name -> function from this registry.

Security: these run locally on the user's machine. The action_authorizer
gate (not yet wired) will eventually control which tools can be invoked
based on confidence band and risk level.
"""

from __future__ import annotations

import json
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


def _workdir_resolved() -> Path:
    try:
        return _WORK_DIR.expanduser().resolve()
    except Exception:
        return _WORK_DIR.expanduser().absolute()


def _resolve_in_workdir(path: str) -> Path | None:
    """
    Resolve a user-provided path into an absolute path under _WORK_DIR.

    Accepts absolute or relative paths. Returns None if the resolved path
    escapes the workdir (basic sandboxing).
    """
    raw = str(path or "").strip()
    if not raw:
        return None

    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = _WORK_DIR / p

    try:
        resolved = p.resolve()
    except Exception:
        resolved = p.absolute()

    wd = _workdir_resolved()
    try:
        if resolved == wd or resolved.is_relative_to(wd):
            return resolved
        return None
    except Exception:
        # Py<3.9 fallback or weird path behavior; do string prefix check.
        wd_s = str(wd)
        res_s = str(resolved)
        if res_s == wd_s or res_s.startswith(wd_s.rstrip(os.sep) + os.sep):
            return resolved
        return None


def list_files(pattern: str = "*", directory: str = ".") -> str:
    """List files matching a glob pattern.

    Args:
        pattern: Glob pattern (e.g., "*test*.py", "*.md").
        directory: Subdirectory to search in (relative to work dir).
    """
    search_dir = _resolve_in_workdir(directory) if directory else _WORK_DIR
    if not search_dir:
        return "path_outside_workdir"
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


def grep_search(pattern: str, path: str = ".", glob: str = "", include: str = "") -> str:
    """Search for a regex pattern in files using grep.

    Args:
        pattern: Regex pattern to search for.
        path: Directory or file to search in (relative to work dir).
        glob: Optional file glob filter (e.g., "*.py").
    """
    if not glob and include:
        glob = include

    cmd = ["grep", "-rn", "--color=never", "-I"]
    if glob:
        cmd.extend(["--include", glob])
    resolved_path = _resolve_in_workdir(path or ".")
    if not resolved_path:
        return "path_outside_workdir"
    cmd.extend([pattern, str(resolved_path)])

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


def read_file(
    path: str | None = None,
    max_lines: int = 200,
    *,
    file_path: str | None = None,
    offset: int = 0,
    limit: int | None = None,
) -> str:
    """Read contents of a file.

    Args:
        path: File path (relative to work dir). Back-compat.
        max_lines: Maximum number of lines to return (legacy).
        file_path: Absolute/relative file path (OpenCode compat).
        offset: Line offset to start reading from (OpenCode compat).
        limit: Maximum lines from offset (OpenCode compat). If None, uses max_lines.
    """
    target = file_path or path
    if not target:
        return "file_path_required"

    resolved = _resolve_in_workdir(str(target))
    if not resolved:
        return "path_outside_workdir"
    if not resolved.exists():
        return f"file_not_found: {target}"
    if not resolved.is_file():
        return f"not_a_file: {target}"

    try:
        text = resolved.read_text(errors="replace")
        lines = text.splitlines()
        off = max(0, int(offset or 0))
        lim = max_lines if limit is None else max(1, int(limit))
        sliced = lines[off : off + lim]
        out = "\n".join(sliced)
        if off + lim < len(lines):
            out += f"\n... truncated ({len(lines)} total lines)"
        return out
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


def glob_files(pattern: str, path: str | None = None) -> str:
    """Search for files using glob patterns (supports ** recursion)."""
    base = _resolve_in_workdir(path or ".")
    if not base:
        return "path_outside_workdir"
    if not base.exists():
        return f"directory_not_found: {path or '.'}"
    matches = sorted(base.glob(pattern))
    if not matches:
        return "no_files_found"
    lines = [str(m.relative_to(_WORK_DIR)) for m in matches[:200]]
    result = "\n".join(lines)
    if len(matches) > 200:
        result += f"\n... and {len(matches) - 200} more files"
    return result


def list_directory(dir_path: str = ".", *, path: str | None = None) -> str:
    """List contents of a directory with basic metadata (JSON string)."""
    target = path if path is not None else dir_path
    resolved = _resolve_in_workdir(target or ".")
    if not resolved:
        return "path_outside_workdir"
    if not resolved.exists():
        return f"directory_not_found: {target or '.'}"
    if not resolved.is_dir():
        return f"not_a_directory: {target}"

    entries = []
    try:
        for child in sorted(resolved.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))[:500]:
            try:
                stat = child.stat()
            except Exception:
                stat = None
            entries.append(
                {
                    "name": child.name,
                    "path": str(child.relative_to(_WORK_DIR)),
                    "type": "dir" if child.is_dir() else "file",
                    "size": int(getattr(stat, "st_size", 0) or 0),
                    "mtime": int(getattr(stat, "st_mtime", 0) or 0),
                }
            )
    except Exception as e:
        return f"list_directory_error: {e}"

    return json.dumps({"dir": str(resolved.relative_to(_WORK_DIR)), "entries": entries}, ensure_ascii=False)


def write_file(
    *,
    file_path: str | None = None,
    path: str | None = None,
    content: str,
    append: bool = False,
) -> str:
    """Write or append content to a file (OpenCode compat)."""
    target = file_path or path
    if not target:
        return "file_path_required"
    resolved = _resolve_in_workdir(str(target))
    if not resolved:
        return "path_outside_workdir"
    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with resolved.open(mode, encoding="utf-8") as f:
            f.write(content)
        return f"ok: wrote {len(content.encode('utf-8', errors='ignore'))} bytes to {resolved.relative_to(_WORK_DIR)}"
    except Exception as e:
        return f"write_error: {e}"


def edit_file(
    *,
    file_path: str | None = None,
    path: str | None = None,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
) -> str:
    """Edit a file by replacing exact text strings (OpenCode compat)."""
    target = file_path or path
    if not target:
        return "file_path_required"
    resolved = _resolve_in_workdir(str(target))
    if not resolved:
        return "path_outside_workdir"
    if not resolved.exists():
        return f"file_not_found: {target}"
    if not resolved.is_file():
        return f"not_a_file: {target}"

    try:
        text = resolved.read_text(errors="replace")
        if replace_all:
            count = text.count(old_string)
            if count == 0:
                return "no_changes"
            new_text = text.replace(old_string, new_string)
        else:
            idx = text.find(old_string)
            if idx == -1:
                return "no_changes"
            count = 1
            new_text = text[:idx] + new_string + text[idx + len(old_string) :]
        resolved.write_text(new_text, encoding="utf-8")
        return f"ok: replaced {count} occurrence(s) in {resolved.relative_to(_WORK_DIR)}"
    except Exception as e:
        return f"edit_error: {e}"


def execute_bash(command: str, timeout: int = 120000, description: str = "") -> str:
    """Execute a shell command (OpenCode compat)."""
    # Note: policy gating is enforced in legacy_tools_v2 for execute_bash as well.
    timeout_sec = max(1, int(timeout) // 1000) if timeout is not None else 120
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
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
        "glob_files": glob_files,
        "list_directory": list_directory,
        "grep_search": grep_search,
        "read_file": read_file,
        "write_file": write_file,
        "edit_file": edit_file,
        "run_command": run_command,
        "execute_bash": execute_bash,
    }
