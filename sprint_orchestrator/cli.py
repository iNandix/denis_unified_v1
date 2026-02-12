"""Interactive sprint CLI for multi-worker terminal sessions."""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Iterator
import contextlib
import json
from pathlib import Path
import re
import select
import shlex
import subprocess
import sys
import time
try:
    import termios
    import tty
except Exception:  # pragma: no cover - non-POSIX terminals
    termios = None  # type: ignore[assignment]
    tty = None  # type: ignore[assignment]

from .auto_dispatch import run_auto_dispatch
from .change_guard import ChangeGuard
from .config import load_sprint_config
from .git_projects import read_commit_tree
from .intent_router_rasa import IntentRoute, RasaIntentRouter
from .mcp_bridge import MCPBridge
from .model_adapter import build_provider_request
from .orchestrator import SprintOrchestrator
from .proposal_pipeline import ProposalPipeline, pick_file_with_zenity
from .proposal_normalizer import normalize_proposal_markdown
from .providers import (
    load_provider_statuses,
    ordered_configured_provider_ids,
    provider_status_map,
)
from .shell_stream import run_command_stream
from .terminal_ui import (
    accent,
    clear_screen,
    done_tick,
    gray_dark,
    gray_light,
    h1,
    line,
    muted,
    ok,
    panel,
    render_table,
    status_badge,
    warn,
)
from .validation import TARGET_NAMES, resolve_target, run_validation_target
from .worker_dispatch import dispatch_worker_task


def _print_projects(projects: list[dict]) -> None:
    if not projects:
        print(warn("No git repositories discovered."))
        return
    rows = []
    for p in projects:
        rows.append(
            [
                p["name"],
                p["branch"],
                "dirty" if p["dirty"] else "clean",
                f"+{p['ahead']}/-{p['behind']}",
                p["head_sha"],
                p["last_commit"],
            ]
        )
    print(render_table(["project", "branch", "state", "ahead/behind", "sha", "last commit"], rows))


def _print_assignments(assignments: list[dict]) -> None:
    rows = []
    for a in assignments:
        rows.append(
            [
                a["worker_id"],
                a["role"],
                a["provider"],
                a["priority"],
                a["status"],
                a["task"],
            ]
        )
    print(render_table(["worker", "role", "provider", "priority", "status", "task"], rows, widths=[10, 12, 14, 8, 10, 56]))


def _filter_events(
    events: list[dict],
    *,
    worker_filter: str | None = None,
    kind_filter: str | None = None,
) -> list[dict]:
    filtered = events
    if worker_filter not in (None, "", "all"):
        filtered = [e for e in filtered if e.get("worker_id") == worker_filter]
    if kind_filter not in (None, "", "all"):
        filtered = [e for e in filtered if str(e.get("kind", "")).startswith(str(kind_filter))]
    return filtered


def _print_events(
    events: list[dict],
    worker_filter: str | None = None,
    kind_filter: str | None = None,
    limit: int = 60,
) -> None:
    filtered = _filter_events(events, worker_filter=worker_filter, kind_filter=kind_filter)
    if not filtered:
        print(muted("(sin eventos para ese filtro)"))
        return
    selected = filtered[-limit:]
    for idx, evt in enumerate(selected, start=max(1, len(filtered) - len(selected) + 1)):
        worker = evt.get("worker_id", "?")
        kind = evt.get("kind", "event")
        ts = evt.get("timestamp_utc", "")
        msg = evt.get("message", "")
        short_ts = ts[11:19] if len(ts) >= 19 else ts
        print(f"{muted(str(idx).rjust(4))} [{short_ts}] {accent(worker)} {muted(kind)} {msg}", flush=True)


def _render_session_dashboard(session: dict) -> None:
    print(panel(
        f"DENIS Sprint Orchestrator :: {session['session_id']}",
        [
            muted(
                f"created={session['created_utc']} status={session.get('status', 'active')} workers={session['workers_requested']}"
            ),
            muted(f"prompt: {session['prompt']}"),
        ],
    ))
    _print_projects(session.get("projects") or [])
    print()
    _print_assignments(session.get("assignments") or [])


def _event_stats(events: list[dict]) -> dict[str, object]:
    by_worker = Counter(str(e.get("worker_id", "?")) for e in events)
    by_kind = Counter(str(e.get("kind", "event")) for e in events)
    return {
        "total": len(events),
        "workers": dict(by_worker),
        "kinds": dict(by_kind),
        "last": events[-1] if events else {},
    }


def _print_dashboard(orch: SprintOrchestrator, session_id: str) -> None:
    session = orch.store.load_session(session_id)
    events = orch.store.read_events(session_id)
    providers = _load_provider_rows(orch)
    stats = _event_stats(events)

    configured = len([p for p in providers if p.get("configured")])
    total_providers = len(providers)
    workers = session.get("assignments") or []
    high_priority = len([w for w in workers if w.get("priority") == "high"])
    last = stats.get("last", {})
    last_kind = last.get("kind", "-") if isinstance(last, dict) else "-"

    print(panel(
        f"Sprint Dashboard :: {session_id}",
        [
            f"events={stats['total']} workers={len(workers)} high_priority={high_priority}",
            f"providers_configured={configured}/{total_providers}",
            f"last_event={last_kind}",
        ],
        border_char="-",
    ))

    worker_rows = []
    workers_stats = stats.get("workers", {})
    if isinstance(workers_stats, dict):
        for worker, count in sorted(workers_stats.items()):
            worker_rows.append([worker, str(count)])
    if worker_rows:
        print(render_table(["worker", "events"], worker_rows, widths=[16, 8]))
    kind_rows = []
    kinds_stats = stats.get("kinds", {})
    if isinstance(kinds_stats, dict):
        for kind, count in sorted(kinds_stats.items()):
            kind_rows.append([kind, str(count)])
    if kind_rows:
        print(render_table(["event_kind", "count"], kind_rows, widths=[36, 8]))
    print()
    print(panel(
        "Quick Actions",
        [
            "1) dashboard  2) autodispatch  3) workers  4) providers",
            "5) mcp-tools  6) tail eventos  7) follow eventos  8) noc live",
            "9) journal  10) manager  11) monitor  12) guide  13) logs  14) commit-tree  0) salir",
        ],
        border_char=".",
    ))


def _print_providers(rows: list[dict]) -> None:
    if not rows:
        print(warn("No provider status available."))
        return
    table_rows = []
    for item in rows:
        table_rows.append(
            [
                item["provider"],
                item["mode"],
                item["request_format"],
                "yes" if item["configured"] else "no",
                ",".join(item["missing_env"]) or "-",
                item["endpoint"] or "-",
                item["queue"] or "-",
                item["notes"] or "-",
            ]
        )
    print(
        render_table(
            ["provider", "mode", "request_format", "configured", "missing_env", "endpoint", "queue", "notes"],
            table_rows,
            widths=[14, 8, 18, 11, 24, 36, 18, 24],
        )
    )


def _load_orchestrator() -> SprintOrchestrator:
    config = load_sprint_config(Path.cwd())
    return SprintOrchestrator(config)


def _load_provider_rows(orch: SprintOrchestrator) -> list[dict]:
    return [s.as_dict() for s in load_provider_statuses(orch.config)]


def _print_stage(*, idx: int, total: int, name: str, status: str, detail: str = "") -> None:
    pct = int((idx / max(1, total)) * 100)
    filled = max(1, int((pct / 100.0) * 20))
    bar = ("#" * filled).ljust(20, ".")
    print(f"[{str(pct).rjust(3)}%] [{bar}] {name}: {status_badge(status)} {detail}".rstrip())


def _apply_dispatch_result_to_registry(
    orch: SprintOrchestrator,
    *,
    session_id: str,
    worker_id: str,
    provider: str,
    status: str,
) -> None:
    if status != "ok":
        return
    orch.registry.mark_task_done_for_worker(
        session_id=session_id,
        worker_id=worker_id,
        provider=provider,
    )


def _render_journal(orch: SprintOrchestrator, session_id: str) -> None:
    session = orch.store.load_session(session_id)
    projects = session.get("projects") or []
    project_path = ""
    if projects:
        project_path = str(projects[0].get("path") or "")
    if not project_path:
        assignments = session.get("assignments") or []
        if assignments:
            project_path = str(assignments[0].get("project_path") or "")
    if not project_path:
        project_path = str(Path.cwd())

    journal = orch.registry.build_journal(project_path=project_path, session_id=session_id)
    pending = journal.get("pending") or []
    in_progress = journal.get("in_progress") or []
    done = journal.get("done") or []

    print(panel(
        f"Git Journal :: {session_id}",
        [
            f"proposal_id={journal.get('proposal_id') or '-'}",
            f"pending={len(pending)} in_progress={len(in_progress)} done={len(done)}",
            f"project={project_path}",
        ],
        border_char="~",
    ))
    if pending:
        print(gray_dark("Pending"))
        for item in pending[:40]:
            print(gray_dark(f"- [{item.get('phase')}] {item.get('task')}"))
    if in_progress:
        print(gray_light("In Progress"))
        for item in in_progress[:40]:
            print(gray_light(f"- [{item.get('phase')}] {item.get('task')}"))
    if done:
        print(ok("Done"))
        for item in done[:80]:
            ts = str(item.get("completed_utc") or item.get("updated_utc") or "")
            provider = str(item.get("provider") or "unknown")
            print(f"{done_tick()} [{item.get('phase')}] {item.get('task')} ({provider}, {ts})")

    stubs = orch.registry.list_stub_validations(project_path=project_path, limit=12)
    if stubs:
        print()
        print(panel("Stub Validations", [f"records={len(stubs)}"], border_char=":"))
        for row in stubs:
            marker = done_tick() if str(row.get("decision")) == "approved" else warn("⛔")
            print(
                f"{marker} {row.get('decision')} {row.get('file_path')}:{row.get('line_no')} "
                f"{row.get('category')} ({row.get('provider')}, {row.get('created_utc')})"
            )

    cmd = ["git", "-C", str(project_path), "log", "--oneline", "-n", "8"]
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if proc.returncode == 0 and (proc.stdout or "").strip():
        print()
        print(panel("Recent Git Commits", [], border_char="."))
        for line in (proc.stdout or "").splitlines()[:8]:
            print(muted(f"- {line}"))


def _resolve_projects_for_commit_view(
    orch: SprintOrchestrator,
    *,
    session_id: str | None = None,
    scan_root: str | None = None,
) -> list[dict]:
    if session_id:
        session = orch.store.load_session(session_id)
        projects = session.get("projects") or []
        if projects:
            return [dict(item) for item in projects]
    discovered = orch.discover_projects(Path(scan_root) if scan_root else None)
    return [item.as_dict() for item in discovered]


def _render_commit_tree_view(
    orch: SprintOrchestrator,
    *,
    projects: list[dict],
    max_commits: int = 30,
    all_branches: bool = True,
) -> None:
    if not projects:
        print(warn("No projects found for commit-tree view."))
        return

    print(panel(
        "Project Commit Tree",
        [
            f"projects={len(projects)} max_commits={max_commits} all_branches={all_branches}",
            "Tree is commit-oriented (not file-oriented).",
        ],
        border_char="^",
    ))
    for item in projects:
        path = str(item.get("path") or "").strip()
        if not path:
            continue
        name = str(item.get("name") or Path(path).name)
        branch = str(item.get("branch") or "unknown")
        dirty = bool(item.get("dirty"))
        ahead = int(item.get("ahead") or 0)
        behind = int(item.get("behind") or 0)
        print()
        print(panel(
            f"{name} ({branch})",
            [f"path={path}", f"state={'dirty' if dirty else 'clean'} ahead=+{ahead} behind=-{behind}"],
            border_char="-",
        ))
        lines = read_commit_tree(Path(path), max_commits=max_commits, all_branches=all_branches)
        for line_item in lines:
            print(gray_light(line_item))


def _render_commit_tree_compact(
    *,
    projects: list[dict],
    max_commits: int = 10,
    all_branches: bool = True,
    max_projects: int = 3,
) -> None:
    if not projects:
        print(muted("(no projects)"))
        return
    for item in projects[:max_projects]:
        path = str(item.get("path") or "").strip()
        if not path:
            continue
        name = str(item.get("name") or Path(path).name)
        branch = str(item.get("branch") or "unknown")
        dirty = bool(item.get("dirty"))
        ahead = int(item.get("ahead") or 0)
        behind = int(item.get("behind") or 0)
        print(gray_light(f"{name} ({branch}) dirty={dirty} +{ahead}/-{behind}"))
        lines = read_commit_tree(Path(path), max_commits=max_commits, all_branches=all_branches)
        for line_item in lines[:max_commits]:
            print(gray_light(f"  {line_item}"))
        print()


def _extract_commit_sha(line_item: str) -> str:
    match = re.search(r"\b([0-9a-f]{7,40})\b", str(line_item))
    return str(match.group(1)) if match else ""


def _read_commit_entries(repo_path: Path, *, max_commits: int, all_branches: bool = True) -> list[dict[str, str]]:
    lines = read_commit_tree(repo_path, max_commits=max_commits, all_branches=all_branches)
    entries: list[dict[str, str]] = []
    for raw in lines[:max_commits]:
        entries.append({"line": raw, "sha": _extract_commit_sha(raw)})
    if not entries:
        entries.append({"line": "(no commits found)", "sha": ""})
    return entries


def _read_commit_detail(repo_path: Path, sha: str, *, max_lines: int = 30) -> list[str]:
    if not sha:
        return ["(commit hash not detected for this line)"]
    cmd = [
        "git",
        "-C",
        str(repo_path),
        "show",
        "--stat",
        "--name-only",
        "--date=iso-strict",
        "--pretty=format:%h %d%nAuthor: %an <%ae>%nDate: %ad%n%n%s%n%n%b",
        "-n",
        "1",
        sha,
    ]
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "unknown git show error").strip()
        return [f"(git show error: {err})"]
    lines = [line.rstrip() for line in (proc.stdout or "").splitlines()]
    if len(lines) > max_lines:
        return lines[:max_lines] + ["..."]
    return lines or ["(no detail available)"]


@contextlib.contextmanager
def _raw_stdin_mode(enabled: bool) -> Iterator[bool]:
    if not enabled or not sys.stdin.isatty() or termios is None or tty is None:
        yield False
        return
    try:
        fd = sys.stdin.fileno()
        old_state = termios.tcgetattr(fd)
    except Exception:
        yield False
        return
    try:
        tty.setcbreak(fd)
        yield True
    finally:
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_state)
        except Exception:
            pass


def _read_keypress(timeout_sec: float = 0.25) -> str | None:
    if not sys.stdin.isatty():
        time.sleep(max(0.01, timeout_sec))
        return None
    wait = max(0.01, float(timeout_sec))
    ready, _, _ = select.select([sys.stdin], [], [], wait)
    if not ready:
        return None
    ch = sys.stdin.read(1)
    if ch != "\x1b":
        return ch

    # Translate arrows to vim-like keys for a single control path.
    ready, _, _ = select.select([sys.stdin], [], [], 0.01)
    if not ready:
        return ch
    nxt = sys.stdin.read(1)
    if nxt != "[":
        return ch + nxt
    ready, _, _ = select.select([sys.stdin], [], [], 0.01)
    if not ready:
        return ch + nxt
    code = sys.stdin.read(1)
    mapping = {"A": "k", "B": "j", "C": "l", "D": "h"}
    return mapping.get(code, ch + nxt + code)


def _cycle_filter_option(options: list[str | None], current: str | None, *, forward: bool = True) -> str | None:
    if not options:
        return current
    try:
        idx = options.index(current)
    except ValueError:
        idx = 0
    step = 1 if forward else -1
    return options[(idx + step) % len(options)]


def _render_phase_progress(orch: SprintOrchestrator, session_id: str) -> None:
    session = orch.store.load_session(session_id)
    projects = session.get("projects") or []
    project_path = ""
    if projects:
        project_path = str(projects[0].get("path") or "")
    if not project_path:
        project_path = str(Path.cwd())
    journal = orch.registry.build_journal(project_path=project_path, session_id=session_id)

    phase_stats: dict[str, dict[str, int]] = {}
    for bucket in ("pending", "in_progress", "done"):
        for item in journal.get(bucket) or []:
            phase = str(item.get("phase") or "unknown")
            phase_stats.setdefault(phase, {"pending": 0, "in_progress": 0, "done": 0})
            phase_stats[phase][bucket] += 1

    if not phase_stats:
        print(muted("No phase data in registry yet."))
        return

    rows = []
    for phase in sorted(phase_stats.keys()):
        data = phase_stats[phase]
        total = data["pending"] + data["in_progress"] + data["done"]
        pct = int((data["done"] / max(1, total)) * 100)
        rows.append(
            [
                phase,
                str(data["pending"]),
                str(data["in_progress"]),
                str(data["done"]),
                f"{pct}%",
            ]
        )
    print(render_table(["phase", "pending", "in_progress", "done", "progress"], rows, widths=[10, 9, 12, 8, 10]))


def _render_journal_snapshot(
    orch: SprintOrchestrator,
    *,
    session_id: str,
    limit: int = 8,
) -> None:
    session = orch.store.load_session(session_id)
    projects = session.get("projects") or []
    project_path = ""
    if projects:
        project_path = str(projects[0].get("path") or "")
    if not project_path:
        project_path = str(Path.cwd())
    journal = orch.registry.build_journal(project_path=project_path, session_id=session_id)

    pending = journal.get("pending") or []
    in_progress = journal.get("in_progress") or []
    done = journal.get("done") or []
    print(muted(f"pending={len(pending)} in_progress={len(in_progress)} done={len(done)}"))
    for item in in_progress[:limit]:
        print(gray_light(f"~ [{item.get('phase')}] {item.get('task')}"))
    for item in done[: max(1, limit // 2)]:
        print(ok(f"{done_tick()} [{item.get('phase')}] {item.get('task')} ({item.get('provider')})"))


def _print_help_panel() -> None:
    print(panel(
        "Sprintctl Guide",
        [
            "Flujo recomendado:",
            "1) propose --file <md>  -> validar/rehacer/cancelar",
            "2) start --autodispatch  -> arranca workers",
            "3) manager <session_id>  -> vista unica (commit-tree + fases + chat)",
            "4) monitor <session_id>  -> fases + chat en vivo",
            "5) journal <session_id>  -> bitacora completa",
            "6) commit-tree [--session-id] -> gestion por arbol de commits",
            "Atajos:",
            "- ctrl+p o journal (en modo interactivo) para bitacora",
            "- manager para trabajar en modo gerencial completo",
            "- en manager: j/k commit, h/l proyecto, w/t filtros, d detalle, f scope, q salir",
            "- monitor --chat-only para foco en acciones de agentes/workers",
            "- logs --follow para stream de auditoria JSONL del bus",
            "- commit-tree muestra historia por proyecto (no por archivos)",
        ],
        border_char="+",
    ))


def _print_chat_events(
    events: list[dict],
    *,
    worker_filter: str | None = None,
    kind_filter: str | None = None,
    limit: int = 25,
) -> None:
    filtered = _filter_events(events, worker_filter=worker_filter, kind_filter=kind_filter)
    if not filtered:
        print(muted("(sin mensajes)"))
        return
    selected = filtered[-limit:]
    for evt in selected:
        ts = str(evt.get("timestamp_utc") or "")
        short_ts = ts[11:19] if len(ts) >= 19 else ts
        worker = str(evt.get("worker_id") or "system")
        kind = str(evt.get("kind") or "event")
        msg = str(evt.get("message") or "")
        print(f"[{short_ts}] {accent(worker)} {muted(kind)}")
        print(f"  {msg}")


def _monitor_loop(
    orch: SprintOrchestrator,
    session_id: str,
    *,
    worker_filter: str | None = None,
    kind_filter: str | None = None,
    limit: int = 25,
    interval_sec: float = 1.0,
    follow: bool = True,
    chat_only: bool = False,
) -> None:
    def render_once() -> None:
        clear_screen()
        print(panel(
            f"Sprint Monitor :: {session_id}",
            [
                f"worker_filter={worker_filter or 'all'} kind_filter={kind_filter or 'all'}",
                f"chat_only={chat_only} follow={follow} refresh={interval_sec:.1f}s",
                f"event_log={orch.bus.status().get('log_path', '')}",
            ],
            border_char="=",
        ))
        if not chat_only:
            _print_dashboard(orch, session_id)
            print()
            print(panel("Phase Progress", [], border_char="-"))
            _render_phase_progress(orch, session_id)
            print()
        print(panel("Agent/Worker Chat", [], border_char="-"))
        events = orch.store.read_events(session_id)
        _print_chat_events(
            events,
            worker_filter=worker_filter,
            kind_filter=kind_filter,
            limit=limit,
        )
        print()
        print(muted("Ctrl+C to stop monitor"))

    render_once()
    if not follow:
        return
    try:
        for _ in orch.bus.iter_live(
            session_id=session_id,
            worker_filter=worker_filter,
            kind_filter=kind_filter,
            interval_sec=interval_sec,
        ):
            render_once()
    except KeyboardInterrupt:
        print()
        print(muted("monitor stopped"))


def _manager_loop(
    orch: SprintOrchestrator,
    session_id: str,
    *,
    project_filter: str | None = None,
    worker_filter: str | None = None,
    kind_filter: str | None = None,
    max_commits: int = 10,
    limit: int = 20,
    interval_sec: float = 1.0,
    follow: bool = True,
) -> None:
    projects = _resolve_projects_for_commit_view(orch, session_id=session_id, scan_root=None)
    if project_filter:
        token = project_filter.strip().lower()
        projects = [
            item for item in projects
            if token in str(item.get("name") or "").lower()
            or token in str(item.get("path") or "").lower()
        ]
    current_worker_filter = None if worker_filter in {None, "", "all"} else worker_filter
    current_kind_filter = None if kind_filter in {None, "", "all"} else kind_filter
    project_scope = "all"
    focused_project_idx = 0
    show_commit_detail = True
    commit_cursor_by_path: dict[str, int] = {}
    focus_commit_counts: dict[str, int] = {}
    worker_options: list[str | None] = [None]
    kind_options: list[str | None] = [None]

    session = orch.store.load_session(session_id)
    assignment_workers = sorted(
        {
            str(item.get("worker_id") or "").strip()
            for item in (session.get("assignments") or [])
            if str(item.get("worker_id") or "").strip()
        }
    )

    def _focused_project() -> dict | None:
        nonlocal focused_project_idx
        if not projects:
            return None
        focused_project_idx = max(0, min(focused_project_idx, len(projects) - 1))
        return projects[focused_project_idx]

    def _visible_projects() -> tuple[list[dict], int]:
        project = _focused_project()
        if not projects:
            return [], 0
        if project_scope == "selected" and project is not None:
            return [project], 0
        return list(projects), max(0, min(focused_project_idx, len(projects) - 1))

    def _render_commit_tree_interactive(visible_projects: list[dict], selected_idx: int) -> tuple[dict | None, dict | None]:
        nonlocal focus_commit_counts
        focus_commit_counts = {}
        if not visible_projects:
            print(muted("(no projects)"))
            return None, None

        selected_project: dict | None = None
        selected_commit: dict | None = None
        for idx, item in enumerate(visible_projects):
            path = str(item.get("path") or "").strip()
            if not path:
                continue
            name = str(item.get("name") or Path(path).name)
            branch = str(item.get("branch") or "unknown")
            dirty = bool(item.get("dirty"))
            ahead = int(item.get("ahead") or 0)
            behind = int(item.get("behind") or 0)
            entries = _read_commit_entries(Path(path), max_commits=max_commits, all_branches=True)
            focus_commit_counts[path] = len(entries)
            cursor = commit_cursor_by_path.get(path, 0)
            cursor = max(0, min(cursor, max(0, len(entries) - 1)))
            commit_cursor_by_path[path] = cursor

            is_selected_project = idx == selected_idx
            header = f"{'>>' if is_selected_project else '  '} {name} ({branch}) dirty={dirty} +{ahead}/-{behind}"
            print(accent(header) if is_selected_project else gray_light(header))
            for cidx, entry in enumerate(entries):
                marker = ">" if is_selected_project and cidx == cursor else " "
                line_item = f"   {marker} {entry['line']}"
                if is_selected_project and cidx == cursor:
                    print(accent(line_item))
                else:
                    print(gray_light(line_item))
            print()

            if is_selected_project:
                selected_project = item
                selected_commit = entries[cursor] if entries else {"line": "(no commits)", "sha": ""}

        return selected_project, selected_commit

    def render_once() -> None:
        nonlocal worker_options, kind_options
        events = orch.store.read_events(session_id)
        event_workers = sorted({str(evt.get("worker_id") or "").strip() for evt in events if str(evt.get("worker_id") or "").strip()})
        worker_options = [None] + sorted(set(assignment_workers + event_workers))
        if current_worker_filter and current_worker_filter not in worker_options:
            worker_options.append(current_worker_filter)

        kinds = {str(evt.get("kind") or "").strip() for evt in events if str(evt.get("kind") or "").strip()}
        kind_prefixes = sorted({item.split(".")[0] for item in kinds})
        kind_options = [None] + kind_prefixes
        if current_kind_filter and current_kind_filter not in kind_options:
            kind_options.append(current_kind_filter)

        visible_projects, selected_idx = _visible_projects()
        selected_project, selected_commit = (None, None)

        clear_screen()
        print(panel(
            f"Sprint Manager :: {session_id}",
            [
                f"project_scope={project_scope} project_filter={project_filter or 'all'}",
                f"worker_filter={current_worker_filter or 'all'} kind_filter={current_kind_filter or 'all'}",
                f"max_commits={max_commits} follow={follow} refresh={interval_sec:.1f}s detail={'on' if show_commit_detail else 'off'}",
                f"event_log={orch.bus.status().get('log_path', '')}",
                "keys: j/k commits  h/l project  f scope  w/t filters  d detail  r reset  q quit",
            ],
            border_char="#",
        ))
        print(panel("Commit Tree", [], border_char="-"))
        selected_project, selected_commit = _render_commit_tree_interactive(visible_projects, selected_idx)
        if show_commit_detail:
            project_path = str((selected_project or {}).get("path") or "")
            project_name = str((selected_project or {}).get("name") or "")
            sha = str((selected_commit or {}).get("sha") or "")
            print(panel(
                "Selected Commit",
                [f"project={project_name or '-'}", f"sha={sha or '-'}"],
                border_char=".",
            ))
            if project_path and sha:
                for line_item in _read_commit_detail(Path(project_path), sha, max_lines=24):
                    print(gray_light(line_item))
            else:
                print(muted("(select a commit with j/k)"))
            print()
        print(panel("Phase Progress", [], border_char="-"))
        _render_phase_progress(orch, session_id)
        print()
        print(panel("Journal Snapshot", [], border_char="-"))
        _render_journal_snapshot(orch, session_id=session_id, limit=8)
        print()
        print(panel("Agent/Worker Chat", [], border_char="-"))
        _print_chat_events(
            events,
            worker_filter=current_worker_filter,
            kind_filter=current_kind_filter,
            limit=limit,
        )
        print()
        print(muted("Ctrl+C or q to stop manager"))

    render_once()
    if not follow:
        return
    if not sys.stdin.isatty():
        try:
            for _ in orch.bus.iter_live(
                session_id=session_id,
                worker_filter=current_worker_filter,
                kind_filter=current_kind_filter,
                interval_sec=interval_sec,
            ):
                render_once()
        except KeyboardInterrupt:
            print()
            print(muted("manager stopped"))
        return

    try:
        with _raw_stdin_mode(True) as raw_enabled:
            if not raw_enabled:
                for _ in orch.bus.iter_live(
                    session_id=session_id,
                    worker_filter=current_worker_filter,
                    kind_filter=current_kind_filter,
                    interval_sec=interval_sec,
                ):
                    render_once()
                return
            next_refresh = time.monotonic() + max(0.2, float(interval_sec))
            while True:
                now = time.monotonic()
                timeout = max(0.05, min(max(0.2, float(interval_sec)), next_refresh - now))
                key = _read_keypress(timeout)
                refresh = False
                if key is None:
                    if time.monotonic() >= next_refresh:
                        render_once()
                        next_refresh = time.monotonic() + max(0.2, float(interval_sec))
                    continue
                if key in {"\x03", "q", "Q"}:
                    break
                if key in {"j"}:
                    focused = _focused_project()
                    if focused:
                        path = str(focused.get("path") or "").strip()
                        if path:
                            count = int(focus_commit_counts.get(path) or max_commits)
                            current = int(commit_cursor_by_path.get(path) or 0)
                            commit_cursor_by_path[path] = min(max(0, count - 1), current + 1)
                            refresh = True
                elif key in {"k"}:
                    focused = _focused_project()
                    if focused:
                        path = str(focused.get("path") or "").strip()
                        if path:
                            current = int(commit_cursor_by_path.get(path) or 0)
                            commit_cursor_by_path[path] = max(0, current - 1)
                            refresh = True
                elif key in {"h", "p"}:
                    if projects:
                        focused_project_idx = (focused_project_idx - 1) % len(projects)
                        refresh = True
                elif key in {"l", "n"}:
                    if projects:
                        focused_project_idx = (focused_project_idx + 1) % len(projects)
                        refresh = True
                elif key in {"d", "\r", "\n", " "}:
                    show_commit_detail = not show_commit_detail
                    refresh = True
                elif key in {"f"}:
                    project_scope = "selected" if project_scope == "all" else "all"
                    refresh = True
                elif key in {"w"}:
                    current_worker_filter = _cycle_filter_option(worker_options, current_worker_filter, forward=True)
                    refresh = True
                elif key in {"W"}:
                    current_worker_filter = _cycle_filter_option(worker_options, current_worker_filter, forward=False)
                    refresh = True
                elif key in {"t"}:
                    current_kind_filter = _cycle_filter_option(kind_options, current_kind_filter, forward=True)
                    refresh = True
                elif key in {"T"}:
                    current_kind_filter = _cycle_filter_option(kind_options, current_kind_filter, forward=False)
                    refresh = True
                elif key in {"r"}:
                    current_worker_filter = None
                    current_kind_filter = None
                    project_scope = "all"
                    show_commit_detail = True
                    refresh = True
                if refresh or time.monotonic() >= next_refresh:
                    render_once()
                    next_refresh = time.monotonic() + max(0.2, float(interval_sec))
    except KeyboardInterrupt:
        pass
    print()
    print(muted("manager stopped"))


def _resolve_project_path_for_worker(
    orch: SprintOrchestrator,
    *,
    session_id: str,
    worker_id: str,
) -> Path:
    session = orch.store.load_session(session_id)
    assignments = session.get("assignments") or []
    for item in assignments:
        if str(item.get("worker_id") or "") == worker_id:
            path = str(item.get("project_path") or "").strip()
            if path:
                return Path(path)
    projects = session.get("projects") or []
    if projects:
        path = str(projects[0].get("path") or "").strip()
        if path:
            return Path(path)
    return Path.cwd()


def _resolve_assignment_task(
    orch: SprintOrchestrator,
    *,
    session_id: str,
    worker_id: str,
) -> str:
    session = orch.store.load_session(session_id)
    assignments = session.get("assignments") or []
    for item in assignments:
        if str(item.get("worker_id") or "") == worker_id:
            return str(item.get("task") or "").strip()
    return ""


def _ask_yes_no(*, prompt: str, default: str = "no", mode: str = "ask") -> bool:
    normalized = (mode or "ask").strip().lower()
    if normalized in {"yes", "y", "approve", "approved"}:
        return True
    if normalized in {"no", "n", "reject", "rejected"}:
        return False

    default_norm = "yes" if default.lower() in {"yes", "y"} else "no"
    if not sys.stdin.isatty():
        return default_norm == "yes"
    while True:
        try:
            raw = input(f"{prompt} [{'Y/n' if default_norm == 'yes' else 'y/N'}]: ").strip().lower()
        except EOFError:
            return default_norm == "yes"
        if not raw:
            return default_norm == "yes"
        if raw in {"y", "yes", "si", "s"}:
            return True
        if raw in {"n", "no"}:
            return False
        print("Respuesta no valida. Usa y/n.")


def _detect_contract_changes(project_path: Path) -> list[dict[str, str]]:
    cmd = ["git", "-C", str(project_path), "diff", "--name-status", "--", "contracts"]
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        return []
    out: list[dict[str, str]] = []
    for stdout_line in (proc.stdout or "").splitlines():
        raw = stdout_line.strip()
        if not raw:
            continue
        parts = raw.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0].strip().upper()
        path = parts[-1].strip()
        if not path:
            continue
        change = "modify"
        if status.startswith("A"):
            change = "create"
        elif status.startswith("M"):
            change = "modify"
        elif status.startswith("D"):
            change = "delete"
        elif status.startswith("R"):
            change = "rename"
        out.append({"status": status, "change_type": change, "file_path": path})
    return out


def _enforce_contract_approval(
    orch: SprintOrchestrator,
    *,
    session_id: str,
    worker_id: str,
    provider: str,
    project_path: Path,
    decision_mode: str = "ask",
) -> bool:
    changes = _detect_contract_changes(project_path)
    if not changes:
        return True
    for item in changes:
        file_path = str(item.get("file_path") or "")
        change_type = str(item.get("change_type") or "modify")
        orch.emit(
            session_id=session_id,
            worker_id=worker_id,
            kind="contract.change.detected",
            message=f"{change_type}:{file_path}",
            payload=item,
        )
        approved = _ask_yes_no(
            prompt=f"[CONTRACT] {change_type.upper()} {file_path}. Aprobar?",
            default="no",
            mode=decision_mode,
        )
        decision = "approved" if approved else "rejected"
        orch.emit(
            session_id=session_id,
            worker_id=worker_id,
            kind="contract.change.decision",
            message=f"{decision}:{file_path}",
            payload={"file_path": file_path, "change_type": change_type, "provider": provider},
        )
        orch.registry.record_contract_decision(
            session_id=session_id,
            worker_id=worker_id,
            provider=provider,
            file_path=file_path,
            change_type=change_type,
            decision=decision,
        )
        if not approved:
            return False
    return True


def _enforce_stub_guard(
    orch: SprintOrchestrator,
    *,
    session_id: str,
    worker_id: str,
    provider: str,
    project_path: Path,
    decision_mode: str = "ask",
) -> bool:
    guard = ChangeGuard(orch.config)
    report = guard.inspect_repo_diff(project_path)
    if report.status == "disabled":
        return True
    if report.status in {"error", "alert"} and report.error:
        orch.emit(
            session_id=session_id,
            worker_id=worker_id,
            kind="guard.stub.error",
            message=report.error[:300],
            payload=report.as_dict(),
        )
        if guard.fail_closed:
            return False
    if not report.violations:
        return True

    orch.emit(
        session_id=session_id,
        worker_id=worker_id,
        kind="guard.stub.detected",
        message=f"violations={len(report.violations)}",
        payload=report.as_dict(),
    )
    print(warn(f"Placeholder Guard alert: {len(report.violations)} issue(s)"))
    for violation in report.violations:
        preview = f"{violation.file_path}:{violation.line_no} {violation.category} -> {violation.line}"
        approved = _ask_yes_no(
            prompt=f"[STUB] {preview}\nAceptar este stub/placeholder?",
            default="no",
            mode=decision_mode,
        )
        decision = "approved" if approved else "rejected"
        orch.registry.record_stub_validation(
            session_id=session_id,
            worker_id=worker_id,
            provider=provider,
            file_path=violation.file_path,
            line_no=violation.line_no,
            category=violation.category,
            pattern=violation.pattern,
            line=violation.line,
            decision=decision,
        )
        orch.emit(
            session_id=session_id,
            worker_id=worker_id,
            kind="guard.stub.decision",
            message=f"{decision}:{violation.file_path}:{violation.line_no}",
            payload=violation.as_dict() | {"decision": decision},
        )
        if not approved:
            return False
    return True


def _enforce_post_dispatch_controls(
    orch: SprintOrchestrator,
    *,
    session_id: str,
    worker_id: str,
    provider: str,
    contract_decision_mode: str = "ask",
    stub_decision_mode: str = "ask",
) -> tuple[bool, str]:
    project_path = _resolve_project_path_for_worker(orch, session_id=session_id, worker_id=worker_id)
    contracts_ok = _enforce_contract_approval(
        orch,
        session_id=session_id,
        worker_id=worker_id,
        provider=provider,
        project_path=project_path,
        decision_mode=contract_decision_mode,
    )
    if not contracts_ok:
        return False, "contract_rejected"
    stubs_ok = _enforce_stub_guard(
        orch,
        session_id=session_id,
        worker_id=worker_id,
        provider=provider,
        project_path=project_path,
        decision_mode=stub_decision_mode,
    )
    if not stubs_ok:
        return False, "stub_rejected"
    return True, ""


def _resolve_dispatch_provider(orch: SprintOrchestrator, provider_hint: str | None = None) -> tuple[str | None, str]:
    statuses = load_provider_statuses(orch.config)
    status_map = provider_status_map(statuses)
    hint = (provider_hint or "").strip()
    if hint:
        status = status_map.get(hint)
        if status and status.configured:
            return status.provider, ""
        return None, f"provider_not_configured:{hint}"

    for item in statuses:
        if item.configured and item.request_format in {"openai_chat", "anthropic_messages", "celery_task"}:
            return item.provider, ""
    return None, "no_dispatchable_provider"


def _execute_intent_route(
    orch: SprintOrchestrator,
    session_id: str,
    route: IntentRoute,
    *,
    worker_id: str = "worker-1",
) -> int:
    print(json.dumps(route.as_dict(), indent=2, sort_keys=True))

    action = route.action
    slots = route.slots or {}
    if action == "dashboard":
        _print_dashboard(orch, session_id)
        return 0
    if action == "projects":
        session = orch.store.load_session(session_id)
        _print_projects(session.get("projects") or [])
        return 0
    if action == "tail":
        _tail_events_loop(
            orch,
            session_id,
            worker_filter=str(slots.get("worker_id") or "") or None,
            kind_filter=str(slots.get("kind") or "") or None,
            limit=60,
            follow=bool(slots.get("follow", False)),
            interval_sec=1.0,
        )
        return 0
    if action == "mcp_tools":
        bridge = MCPBridge(orch.config)
        snapshot = bridge.emit_catalog_snapshot(
            session_id=session_id,
            worker_id=worker_id,
            store=orch.store,
            bus=orch.bus,
        )
        print(json.dumps(snapshot, indent=2, sort_keys=True))
        return 0
    if action == "validate":
        target_name = str(slots.get("target") or "preflight")
        try:
            target = resolve_target(Path.cwd(), target_name)
        except ValueError:
            print(f"unknown validation target from route: {target_name}")
            return 2
        result = run_validation_target(
            session_id=session_id,
            worker_id=str(slots.get("worker_id") or worker_id),
            store=orch.store,
            target=target,
            bus=orch.bus,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if str(result.get("status")) == "ok" else 1
    if action == "autodispatch":
        return cmd_autodispatch(
            argparse.Namespace(
                session_id=session_id,
                worker=str(slots.get("worker_id") or "") or None,
                timeout_sec=45.0,
                stub_decision="ask",
                contract_decision="ask",
                rework_on_reject=True,
            )
        )
    if action == "note":
        note = str(slots.get("prompt") or route.raw.get("text") or "rasa-approved action")
        orch.emit(
            session_id=session_id,
            worker_id=str(slots.get("worker_id") or worker_id),
            kind="worker.note",
            message=note,
            payload={"source": route.source, "intent": route.intent},
        )
        print(ok("note emitted"))
        return 0
    if action == "dispatch":
        provider_hint = str(slots.get("provider") or "")
        provider, err = _resolve_dispatch_provider(orch, provider_hint or None)
        if provider is None:
            print(f"dispatch route failed: {err}")
            return 3
        payload = str(slots.get("prompt") or route.raw.get("text") or "")
        return cmd_dispatch(
            argparse.Namespace(
                session_id=session_id,
                provider=provider,
                worker=str(slots.get("worker_id") or worker_id),
                message=payload,
                timeout_sec=45.0,
                stub_decision="ask",
                contract_decision="ask",
                rework_on_reject=True,
            )
        )

    print(f"intent action not implemented: {action}")
    return 2


def _tail_events_loop(
    orch: SprintOrchestrator,
    session_id: str,
    *,
    worker_filter: str | None = None,
    kind_filter: str | None = None,
    limit: int = 60,
    follow: bool = False,
    interval_sec: float = 1.0,
) -> None:
    events = orch.store.read_events(session_id)
    _print_events(
        events,
        worker_filter=worker_filter,
        kind_filter=kind_filter,
        limit=limit,
    )
    if not follow:
        return

    try:
        for event in orch.bus.iter_live(
            session_id=session_id,
            worker_filter=worker_filter,
            kind_filter=kind_filter,
            interval_sec=interval_sec,
        ):
            _print_events([event], limit=1)
    except KeyboardInterrupt:
        print()
        print(muted("tail follow stopped"))


def _noc_loop(
    orch: SprintOrchestrator,
    session_id: str,
    *,
    worker_filter: str | None = None,
    kind_filter: str | None = None,
    limit: int = 20,
    interval_sec: float = 1.0,
) -> None:
    try:
        while True:
            clear_screen()
            print(panel(
                f"NOC Live :: {session_id}",
                [
                    f"worker_filter={worker_filter or 'all'} kind_filter={kind_filter or 'all'}",
                    f"limit={limit} refresh={interval_sec:.1f}s (Ctrl+C to stop)",
                ],
                border_char="=",
            ))
            _print_dashboard(orch, session_id)
            print()
            print(panel("Event Stream", [], border_char="-"))
            events = orch.store.read_events(session_id)
            _print_events(
                events,
                worker_filter=worker_filter,
                kind_filter=kind_filter,
                limit=limit,
            )
            time.sleep(max(0.2, interval_sec))
    except KeyboardInterrupt:
        print()
        print(muted("noc stopped"))


def _simple_menu_loop(orch: SprintOrchestrator, session_id: str) -> int:
    while True:
        clear_screen()
        _print_dashboard(orch, session_id)
        print()
        print(panel(
            "Modo Simple",
            [
                "1) Ver dashboard",
                "2) Ejecutar autodispatch",
                "3) Ver workers",
                "4) Ver providers",
                "5) Ver tools MCP",
                "6) Ver ultimos eventos",
                "7) Seguir eventos en vivo",
                "8) NOC live",
                "9) Journal (bitacora)",
                "10) Manager (commit+fases+chat)",
                "11) Monitor chat+fases",
                "12) Ayuda guiada",
                "13) Logs de auditoria",
                "14) Arbol de commits",
                "0) Salir",
            ],
            border_char="*",
        ))
        choice = input("Elige opcion [0-14]: ").strip()

        if choice == "1":
            continue
        if choice == "2":
            rc = cmd_autodispatch(
                argparse.Namespace(
                    session_id=session_id,
                    worker=None,
                    timeout_sec=45.0,
                    rework_on_reject=True,
                    stub_decision="ask",
                    contract_decision="ask",
                )
            )
            print(f"autodispatch exit_code={rc}")
            input("Enter para continuar...")
            continue
        if choice == "3":
            session = orch.store.load_session(session_id)
            _print_assignments(session.get("assignments") or [])
            input("Enter para continuar...")
            continue
        if choice == "4":
            _print_providers(_load_provider_rows(orch))
            input("Enter para continuar...")
            continue
        if choice == "5":
            bridge = MCPBridge(orch.config)
            payload = bridge.emit_catalog_snapshot(
                session_id=session_id,
                worker_id="worker-1",
                store=orch.store,
                bus=orch.bus,
            )
            print(json.dumps(payload, indent=2, sort_keys=True))
            input("Enter para continuar...")
            continue
        if choice == "6":
            _tail_events_loop(orch, session_id, limit=30)
            input("Enter para continuar...")
            continue
        if choice == "7":
            _tail_events_loop(orch, session_id, follow=True, interval_sec=1.0)
            input("Enter para continuar...")
            continue
        if choice == "8":
            _noc_loop(orch, session_id, limit=20, interval_sec=1.0)
            input("Enter para continuar...")
            continue
        if choice == "9":
            _render_journal(orch, session_id)
            input("Enter para continuar...")
            continue
        if choice == "10":
            _manager_loop(
                orch,
                session_id,
                max_commits=10,
                follow=True,
                interval_sec=1.0,
                limit=20,
            )
            input("Enter para continuar...")
            continue
        if choice == "11":
            _monitor_loop(orch, session_id, follow=True, interval_sec=1.0, limit=25)
            input("Enter para continuar...")
            continue
        if choice == "12":
            _print_help_panel()
            input("Enter para continuar...")
            continue
        if choice == "13":
            cmd_logs(
                argparse.Namespace(
                    session_id=session_id,
                    limit=60,
                    follow=False,
                    interval_sec=1.0,
                )
            )
            input("Enter para continuar...")
            continue
        if choice == "14":
            cmd_commit_tree(
                argparse.Namespace(
                    session_id=session_id,
                    scan_root=None,
                    project=None,
                    max_commits=30,
                    all_branches=True,
                )
            )
            input("Enter para continuar...")
            continue
        if choice == "0":
            return 0

        print("Opcion no valida.")
        time.sleep(0.7)


def cmd_list_projects(args: argparse.Namespace) -> int:
    orch = _load_orchestrator()
    projects = [p.as_dict() for p in orch.discover_projects(Path(args.scan_root) if args.scan_root else None)]
    print(h1("Git Projects"))
    _print_projects(projects)
    return 0


def _ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    raw = input(f"{prompt}{suffix}: ").strip()
    if raw:
        return raw
    return default or ""


def cmd_start(args: argparse.Namespace) -> int:
    orch = _load_orchestrator()
    workers = args.workers
    prompt = args.prompt
    simple_mode = bool(getattr(args, "simple", False))
    if args.interactive:
        if not prompt:
            prompt = _ask("Sprint prompt")
        if workers is None:
            workers = int(_ask("Workers (1-4)", "2"))
    if not prompt:
        print("--prompt is required (or use --interactive)")
        return 2
    if workers is None:
        workers = 2
    workers = max(1, min(4, int(workers)))

    provider_status = load_provider_statuses(orch.config)
    real_providers = ordered_configured_provider_ids(config=orch.config, statuses=provider_status)
    if not real_providers:
        print("No configured providers found. Run `sprintctl providers` and set keys/endpoints first.")
        return 3

    projects = orch.discover_projects(Path(args.scan_root) if args.scan_root else None)
    session = orch.create_session(
        prompt=prompt,
        workers=workers,
        projects=projects,
        provider_pool=real_providers,
        proposal_id=getattr(args, "proposal_id", None),
    )
    payload = session.as_dict()

    _render_session_dashboard(payload)
    print(ok("Session created."))
    print(muted(f"session_id={payload['session_id']}"))

    if args.autodispatch:
        rc = cmd_autodispatch(
            argparse.Namespace(
                session_id=payload["session_id"],
                worker=None,
                timeout_sec=float(args.timeout_sec),
                stub_decision=str(getattr(args, "stub_decision", "ask")),
                contract_decision=str(getattr(args, "contract_decision", "ask")),
                rework_on_reject=bool(getattr(args, "rework_on_reject", True)),
            )
        )
        print(h1("Auto-dispatch"))
        print(f"autodispatch exit_code={rc}")

    if simple_mode:
        return _simple_menu_loop(orch, payload["session_id"])
    if args.watch:
        return _interactive_loop(orch, payload["session_id"])
    return 0


def cmd_simple(args: argparse.Namespace) -> int:
    forwarded = argparse.Namespace(
        prompt=args.prompt,
        workers=args.workers,
        scan_root=args.scan_root,
        interactive=True,
        watch=False,
        simple=True,
        autodispatch=args.autodispatch,
        timeout_sec=args.timeout_sec,
        stub_decision=args.stub_decision,
        contract_decision=args.contract_decision,
        rework_on_reject=args.rework_on_reject,
    )
    return cmd_start(forwarded)


def _interactive_loop(orch: SprintOrchestrator, session_id: str) -> int:
    router = RasaIntentRouter(orch.config)
    print(h1(line("-")))
    print(muted("Interactive mode: help, guide, dashboard, journal, manager [project] [worker] [kind], commit-tree [project], monitor [worker] [kind], chat [worker] [kind], noc [worker] [kind], show, projects, workers, providers, mcp-tools, tail [worker] [kind], follow [worker] [kind], logs, validate <target> [worker], run <worker> -- <cmd>, adapt <provider> <msg>, dispatch <provider> <msg>, autodispatch [worker], propose --file <md>, intent <texto>, clear, quit"))
    print(h1(line("-")))
    while True:
        try:
            raw = input(f"sprintctl[{session_id[:12]}]> ").strip()
        except EOFError:
            print()
            return 0
        if not raw:
            continue

        parts = shlex.split(raw)
        cmd = parts[0].lower()
        if cmd in {"quit", "exit", "q"}:
            return 0

        if cmd == "help":
            print("commands: guide | dashboard | journal | manager [project] [worker] [kind] (j/k,h/l,w/t,d,f,q) | commit-tree [project] | monitor [worker] [kind] | chat [worker] [kind] | noc [worker] [kind] | show | projects | workers | providers | mcp-tools | tail [worker] [kind] | follow [worker] [kind] | logs [limit] | validate <target> [worker] | run <worker> -- <cmd> | adapt <provider> <msg> | dispatch <provider> <msg> | autodispatch [worker] | propose --file <md> | intent <texto> | clear | quit")
            continue
        if cmd == "guide":
            _print_help_panel()
            continue

        session = orch.store.load_session(session_id)
        if cmd == "dashboard":
            _print_dashboard(orch, session_id)
            continue
        if cmd in {"journal", "ctrl+p", "\u0010"}:
            _render_journal(orch, session_id)
            continue
        if cmd in {"commit-tree", "tree", "commits"}:
            project_filter = parts[1] if len(parts) > 1 else None
            cmd_commit_tree(
                argparse.Namespace(
                    session_id=session_id,
                    scan_root=None,
                    project=project_filter,
                    max_commits=30,
                    all_branches=True,
                )
            )
            continue
        if cmd in {"manager", "mgr"}:
            project_filter = parts[1] if len(parts) > 1 else None
            worker_filter = parts[2] if len(parts) > 2 else None
            kind_filter = parts[3] if len(parts) > 3 else None
            _manager_loop(
                orch,
                session_id,
                project_filter=project_filter,
                worker_filter=worker_filter,
                kind_filter=kind_filter,
                max_commits=10,
                limit=20,
                interval_sec=1.0,
                follow=True,
            )
            continue
        if cmd == "monitor":
            worker_filter = parts[1] if len(parts) > 1 else None
            kind_filter = parts[2] if len(parts) > 2 else None
            _monitor_loop(
                orch,
                session_id,
                worker_filter=worker_filter,
                kind_filter=kind_filter,
                follow=True,
                interval_sec=1.0,
                limit=25,
                chat_only=False,
            )
            continue
        if cmd == "chat":
            worker_filter = parts[1] if len(parts) > 1 else None
            kind_filter = parts[2] if len(parts) > 2 else None
            _monitor_loop(
                orch,
                session_id,
                worker_filter=worker_filter,
                kind_filter=kind_filter,
                follow=True,
                interval_sec=1.0,
                limit=30,
                chat_only=True,
            )
            continue
        if cmd == "noc":
            worker_filter = parts[1] if len(parts) > 1 else None
            kind_filter = parts[2] if len(parts) > 2 else None
            _noc_loop(
                orch,
                session_id,
                worker_filter=worker_filter,
                kind_filter=kind_filter,
                limit=20,
                interval_sec=1.0,
            )
            continue
        if cmd == "show":
            _render_session_dashboard(session)
            continue
        if cmd == "projects":
            _print_projects(session.get("projects") or [])
            continue
        if cmd == "workers":
            _print_assignments(session.get("assignments") or [])
            continue
        if cmd == "providers":
            _print_providers(_load_provider_rows(orch))
            continue
        if cmd == "mcp-tools":
            bridge = MCPBridge(orch.config)
            snapshot = bridge.emit_catalog_snapshot(
                session_id=session_id,
                worker_id="worker-1",
                store=orch.store,
                bus=orch.bus,
            )
            print(json.dumps(snapshot, indent=2, sort_keys=True))
            continue
        if cmd == "tail":
            worker_filter = parts[1] if len(parts) > 1 else None
            kind_filter = parts[2] if len(parts) > 2 else None
            _tail_events_loop(
                orch,
                session_id,
                worker_filter=worker_filter,
                kind_filter=kind_filter,
                limit=60,
                follow=False,
            )
            continue
        if cmd == "follow":
            worker_filter = parts[1] if len(parts) > 1 else None
            kind_filter = parts[2] if len(parts) > 2 else None
            _tail_events_loop(
                orch,
                session_id,
                worker_filter=worker_filter,
                kind_filter=kind_filter,
                limit=60,
                follow=True,
                interval_sec=1.0,
            )
            continue
        if cmd == "logs":
            limit = 40
            if len(parts) > 1:
                try:
                    limit = max(1, min(500, int(parts[1])))
                except ValueError:
                    print("usage: logs [limit]")
                    continue
            cmd_logs(
                argparse.Namespace(
                    session_id=session_id,
                    limit=limit,
                    follow=False,
                    interval_sec=1.0,
                )
            )
            continue
        if cmd == "run":
            if len(parts) < 4 or "--" not in parts:
                print("usage: run <worker_id> -- <command...>")
                continue
            sep = parts.index("--")
            worker_id = parts[1]
            command = parts[sep + 1 :]
            if not command:
                print("usage: run <worker_id> -- <command...>")
                continue
            result = run_command_stream(
                session_id=session_id,
                worker_id=worker_id,
                store=orch.store,
                command=command,
                cwd=Path.cwd(),
                bus=orch.bus,
            )
            print(f"run: {status_badge(str(result['status']))} rc={result['returncode']} duration_ms={result['duration_ms']} lines={result['lines']}")
            continue
        if cmd == "adapt":
            if len(parts) < 3:
                print("usage: adapt <provider> <message>")
                continue
            args = argparse.Namespace(provider=parts[1], message=" ".join(parts[2:]), max_tokens=None, stream=False)
            cmd_adapt(args)
            continue
        if cmd == "dispatch":
            if len(parts) < 3:
                print("usage: dispatch <provider> <message>")
                continue
            args = argparse.Namespace(
                session_id=session_id,
                provider=parts[1],
                worker="worker-1",
                message=" ".join(parts[2:]),
                timeout_sec=45.0,
                rework_on_reject=True,
                stub_decision="ask",
                contract_decision="ask",
            )
            cmd_dispatch(args)
            continue
        if cmd == "autodispatch":
            only_worker = parts[1] if len(parts) > 1 else None
            rc = cmd_autodispatch(
                argparse.Namespace(
                    session_id=session_id,
                    worker=only_worker,
                    timeout_sec=45.0,
                    rework_on_reject=True,
                    stub_decision="ask",
                    contract_decision="ask",
                )
            )
            print(f"autodispatch exit_code={rc}")
            continue
        if cmd == "propose":
            parser = argparse.ArgumentParser(prog="propose", add_help=False)
            parser.add_argument("--file", default=None)
            parser.add_argument("--pick-file", action="store_true")
            parser.add_argument("--topic", default=None)
            parser.add_argument("--decision", choices=["validar", "rehacer", "cancelar"], default=None)
            parser.add_argument("--feedback", default=None)
            parser.add_argument("--workers", type=int, default=2)
            parser.add_argument("--scan-root", default=None)
            parser.add_argument("--start-machinery", action=argparse.BooleanOptionalAction, default=True)
            parser.add_argument("--autodispatch", action="store_true")
            parser.add_argument("--timeout-sec", type=float, default=45.0)
            parser.add_argument("--stub-decision", choices=["ask", "yes", "no"], default="ask")
            parser.add_argument("--contract-decision", choices=["ask", "yes", "no"], default="ask")
            parser.add_argument("--rework-on-reject", action=argparse.BooleanOptionalAction, default=True)
            try:
                parsed = parser.parse_args(parts[1:])
            except SystemExit:
                print("usage: propose --file <markdown> [--pick-file] [--topic <label>] [--decision validar|rehacer|cancelar]")
                continue
            cmd_propose(parsed)
            continue
        if cmd == "clear":
            clear_screen()
            continue
        if cmd == "event":
            if len(parts) < 3:
                print("usage: event <worker_id> <message>")
                continue
            worker_id = parts[1]
            message = " ".join(parts[2:])
            orch.emit(session_id=session_id, worker_id=worker_id, kind="worker.note", message=message)
            print(ok("event appended"))
            continue
        if cmd == "validate":
            if len(parts) < 2:
                print(f"usage: validate <target> [worker_id], targets={', '.join(TARGET_NAMES)}")
                continue
            target_name = parts[1]
            worker_id = parts[2] if len(parts) > 2 else "worker-2"
            try:
                target = resolve_target(Path.cwd(), target_name)
            except ValueError as exc:
                print(str(exc))
                continue
            result = run_validation_target(
                session_id=session_id,
                worker_id=worker_id,
                store=orch.store,
                target=target,
                bus=orch.bus,
            )
            print(f"validation {target_name}: {status_badge(str(result['status']))} duration_ms={result['duration_ms']}")
            continue
        if cmd == "intent":
            if len(parts) < 2:
                print("usage: intent <texto>")
                continue
            route = router.route(" ".join(parts[1:]))
            _execute_intent_route(orch, session_id, route)
            continue
        route = router.route(raw)
        rc = _execute_intent_route(orch, session_id, route)
        if rc != 0:
            print(f"unknown command: {cmd}")


def cmd_tail(args: argparse.Namespace) -> int:
    orch = _load_orchestrator()
    _tail_events_loop(
        orch,
        args.session_id,
        worker_filter=args.worker,
        kind_filter=args.kind,
        limit=max(1, int(args.limit)),
        follow=bool(args.follow),
        interval_sec=float(args.interval_sec),
    )
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    orch = _load_orchestrator()
    target = resolve_target(Path.cwd(), args.target)
    result = run_validation_target(
        session_id=args.session_id,
        worker_id=args.worker,
        store=orch.store,
        target=target,
        bus=orch.bus,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if str(result.get("status")) == "ok" else 1


def cmd_providers(_: argparse.Namespace) -> int:
    orch = _load_orchestrator()
    print(h1("Provider Load"))
    _print_providers(_load_provider_rows(orch))
    return 0


def cmd_providers_template(args: argparse.Namespace) -> int:
    template = """# Sprint Orchestrator Provider Load (real tools only)
DENIS_USE_SPRINT_ORCHESTRATOR=true

# Pin slot-1 provider (overrides legacy pin)
DENIS_SPRINT_PRIMARY_PROVIDER=denis_canonical

# Terminal workers
DENIS_SPRINT_CODEX_CMD=codex
DENIS_SPRINT_CLAUDE_CMD=claude

# API providers
DENIS_CANONICAL_URL=http://127.0.0.1:9999/v1/chat/completions
DENIS_CANONICAL_MODEL=denis-cognitive
DENIS_CANONICAL_API_KEY=
GROQ_API_KEY=
OPENROUTER_API_KEY=
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
LLM_BASE_URL=
LLM_MODEL=
DENIS_VLLM_URL=http://10.10.10.2:9999/v1/chat/completions
DENIS_VLLM_MODEL=deepseek-coder

# llama.cpp as workers (recommended via celery/crewai)
DENIS_SPRINT_LLAMA_NODE1_MODE=celery
DENIS_SPRINT_LLAMA_NODE1_QUEUE=sprint:llama_node1
DENIS_SPRINT_LLAMA_NODE1_URL=http://10.10.10.1:8084/v1/chat/completions
DENIS_SPRINT_LLAMA_NODE2_MODE=celery
DENIS_SPRINT_LLAMA_NODE2_QUEUE=sprint:llama_node2
DENIS_SPRINT_LLAMA_NODE2_URL=http://10.10.10.2:8084/v1/chat/completions

# Celery/CrewAI dispatch
REDIS_URL=redis://127.0.0.1:6379/0
DENIS_SPRINT_CELERY_APP=denis_crew_tasks
DENIS_SPRINT_CELERY_TASK=denis.sprint.execute
DENIS_SPRINT_CREW_QUEUE=sprint:crewai

# Denis MCP bridge (real endpoint only)
DENIS_SPRINT_MCP_ENABLED=true
DENIS_SPRINT_MCP_BASE_URL=http://127.0.0.1:8084
DENIS_SPRINT_MCP_TOOLS_PATH=/tools
DENIS_SPRINT_MCP_AUTH_TOKEN=
DENIS_SPRINT_MCP_ALLOW_FILE_CATALOG=false

# Native event bus (store + optional redis pubsub)
DENIS_SPRINT_EVENT_BUS_REDIS_ENABLED=true
DENIS_SPRINT_EVENT_BUS_CHANNEL=denis:sprint:events
DENIS_SPRINT_EVENT_BUS_REDIS_URL=redis://127.0.0.1:6379/0
DENIS_SPRINT_EVENT_LOG_ENABLED=true
DENIS_SPRINT_EVENT_LOG_PATH=

# Rasa confidence gate (deterministic intent routing)
DENIS_USE_RASA_GATE=false
DENIS_SPRINT_RASA_URL=http://127.0.0.1:5005/model/parse
DENIS_SPRINT_RASA_TIMEOUT_SEC=5
DENIS_SPRINT_RASA_MIN_CONFIDENCE=0.85
DENIS_SPRINT_RASA_FALLBACK_PROVIDER=llama_node1

# Global project registry
DENIS_SPRINT_REGISTRY_DB=
DENIS_SPRINT_REGISTRY_ATLAS_ENABLED=false
DENIS_SPRINT_REGISTRY_ATLAS_URL=http://127.0.0.1:8084

# Placeholder/Stub guard
DENIS_SPRINT_PLACEHOLDER_GUARD_ENABLED=true
DENIS_SPRINT_PLACEHOLDER_GUARD_FAIL_CLOSED=true
DENIS_SPRINT_PLACEHOLDER_ALLOW_MARKER=denis:allow-placeholder
"""
    out_path = Path(args.out) if args.out else None
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(template, encoding="utf-8")
        print(f"Wrote provider template: {out_path}")
    else:
        print(template)
    return 0


def cmd_mcp_tools(args: argparse.Namespace) -> int:
    orch = _load_orchestrator()
    bridge = MCPBridge(orch.config)
    status = bridge.status()
    payload: dict[str, object] = {
        "status": status,
        "tools": bridge.list_tools(),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if args.session_id:
        bridge.emit_catalog_snapshot(
            session_id=args.session_id,
            worker_id=args.worker,
            store=orch.store,
            bus=orch.bus,
        )
    return 0 if bool(status.get("configured")) else 1


def cmd_dashboard(args: argparse.Namespace) -> int:
    orch = _load_orchestrator()
    _print_dashboard(orch, args.session_id)
    return 0


def cmd_guide(_: argparse.Namespace) -> int:
    _print_help_panel()
    return 0


def cmd_monitor(args: argparse.Namespace) -> int:
    orch = _load_orchestrator()
    _monitor_loop(
        orch,
        args.session_id,
        worker_filter=args.worker,
        kind_filter=args.kind,
        limit=max(1, int(args.limit)),
        interval_sec=float(args.interval_sec),
        follow=bool(args.follow),
        chat_only=bool(args.chat_only),
    )
    return 0


def cmd_manager(args: argparse.Namespace) -> int:
    orch = _load_orchestrator()
    _manager_loop(
        orch,
        args.session_id,
        project_filter=args.project,
        worker_filter=args.worker,
        kind_filter=args.kind,
        max_commits=max(1, int(args.max_commits)),
        limit=max(1, int(args.limit)),
        interval_sec=float(args.interval_sec),
        follow=bool(args.follow),
    )
    return 0


def cmd_logs(args: argparse.Namespace) -> int:
    orch = _load_orchestrator()
    status = orch.bus.status()
    log_path = Path(str(status.get("log_path") or ""))
    if not log_path.exists():
        print(f"log file not found: {log_path}")
        return 2

    session_id = str(args.session_id or "").strip()
    limit = max(1, min(1000, int(args.limit)))
    interval_sec = float(args.interval_sec)

    def read_rows() -> list[dict]:
        rows: list[dict] = []
        for log_line in log_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            raw = log_line.strip()
            if not raw:
                continue
            try:
                item = json.loads(raw)
            except Exception:
                continue
            if session_id and str(item.get("session_id") or "") != session_id:
                continue
            rows.append(item)
        return rows

    rows = read_rows()
    _print_chat_events(rows, limit=limit)
    if not bool(args.follow):
        return 0
    cursor = len(rows)
    try:
        while True:
            time.sleep(max(0.2, interval_sec))
            rows = read_rows()
            if len(rows) <= cursor:
                continue
            batch = rows[cursor:]
            cursor = len(rows)
            _print_chat_events(batch, limit=len(batch))
    except KeyboardInterrupt:
        print()
        print(muted("logs follow stopped"))
    return 0


def cmd_noc(args: argparse.Namespace) -> int:
    orch = _load_orchestrator()
    _noc_loop(
        orch,
        args.session_id,
        worker_filter=args.worker,
        kind_filter=args.kind,
        limit=max(1, int(args.limit)),
        interval_sec=float(args.interval_sec),
    )
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    orch = _load_orchestrator()
    result = run_command_stream(
        session_id=args.session_id,
        worker_id=args.worker,
        store=orch.store,
        command=list(args.command),
        cwd=Path.cwd(),
        bus=orch.bus,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if str(result.get("status")) == "ok" else 1


def cmd_adapt(args: argparse.Namespace) -> int:
    orch = _load_orchestrator()
    statuses = load_provider_statuses(orch.config)
    status_map = provider_status_map(statuses)
    status = status_map.get(args.provider)
    if status is None:
        print(f"Unknown provider: {args.provider}")
        return 2
    if not status.configured:
        print(f"Provider {args.provider} is not configured: missing_env={status.missing_env}")
        return 3
    if status.request_format == "celery_task":
        payload = {
            "provider": status.provider,
            "mode": status.mode,
            "request_format": status.request_format,
            "queue": status.queue,
            "task_name": "denis.sprint.execute",
            "kwargs": {
                "provider": status.provider,
                "messages": [{"role": "user", "content": args.message}],
                "session_id": "<session_id>",
                "requested_at": "<unix_ts>",
            },
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    request = build_provider_request(
        config=orch.config,
        status=status,
        messages=[{"role": "user", "content": args.message}],
        stream=args.stream,
        max_tokens=args.max_tokens,
    )
    print(json.dumps(request.as_dict(redact_headers=True), indent=2, sort_keys=True))
    return 0


def cmd_dispatch(args: argparse.Namespace) -> int:
    orch = _load_orchestrator()
    statuses = load_provider_statuses(orch.config)
    status_map = provider_status_map(statuses)
    status = status_map.get(args.provider)
    if status is None:
        print(f"Unknown provider: {args.provider}")
        return 2
    if not status.configured:
        print(f"Provider {args.provider} is not configured: missing_env={status.missing_env}")
        return 3
    result = dispatch_worker_task(
        config=orch.config,
        store=orch.store,
        session_id=args.session_id,
        worker_id=args.worker,
        provider_status=status,
        messages=[{"role": "user", "content": args.message}],
        timeout_sec=float(args.timeout_sec),
        bus=orch.bus,
    )
    if result.status == "ok":
        controls_ok, reason = _enforce_post_dispatch_controls(
            orch,
            session_id=args.session_id,
            worker_id=args.worker,
            provider=status.provider,
            contract_decision_mode=getattr(args, "contract_decision", "ask"),
            stub_decision_mode=getattr(args, "stub_decision", "ask"),
        )
        if not controls_ok and bool(getattr(args, "rework_on_reject", True)):
            rework_message = (
                f"{args.message}\n\n"
                "REWORK REQUIRED: remove/reduce placeholders/stubs/mocks/simulations unless explicitly approved. "
                "Complete with real implementation and contract-safe changes."
            )
            orch.emit(
                session_id=args.session_id,
                worker_id=args.worker,
                kind="worker.rework.requested",
                message=reason,
                payload={"provider": status.provider},
            )
            retry = dispatch_worker_task(
                config=orch.config,
                store=orch.store,
                session_id=args.session_id,
                worker_id=args.worker,
                provider_status=status,
                messages=[{"role": "user", "content": rework_message}],
                timeout_sec=float(args.timeout_sec),
                bus=orch.bus,
            )
            result = retry
            if result.status == "ok":
                controls_ok, reason = _enforce_post_dispatch_controls(
                    orch,
                    session_id=args.session_id,
                    worker_id=args.worker,
                    provider=status.provider,
                    contract_decision_mode=getattr(args, "contract_decision", "ask"),
                    stub_decision_mode=getattr(args, "stub_decision", "ask"),
                )
        if not controls_ok:
            print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
            print(warn(f"post-dispatch controls rejected: {reason}"))
            return 4

    _apply_dispatch_result_to_registry(
        orch,
        session_id=args.session_id,
        worker_id=args.worker,
        provider=status.provider,
        status=result.status,
    )
    print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    return 0 if result.status == "ok" else 1


def cmd_autodispatch(args: argparse.Namespace) -> int:
    orch = _load_orchestrator()
    summary = run_auto_dispatch(
        config=orch.config,
        store=orch.store,
        session_id=args.session_id,
        only_worker=args.worker,
        timeout_sec=float(args.timeout_sec),
        bus=orch.bus,
    )
    assignments_by_worker = {}
    session = orch.store.load_session(args.session_id)
    for assignment in session.get("assignments") or []:
        worker_id = str(assignment.get("worker_id") or "")
        if worker_id:
            assignments_by_worker[worker_id] = assignment

    reworked_results: list[dict] = []
    for item in summary.get("results") or []:
        if not isinstance(item, dict):
            continue
        worker_id = str(item.get("worker_id") or "")
        provider = str(item.get("used_provider") or item.get("assigned_provider") or "")
        status = str(item.get("status") or "")
        if status == "ok":
            controls_ok, reason = _enforce_post_dispatch_controls(
                orch,
                session_id=args.session_id,
                worker_id=worker_id,
                provider=provider,
                contract_decision_mode=getattr(args, "contract_decision", "ask"),
                stub_decision_mode=getattr(args, "stub_decision", "ask"),
            )
            if not controls_ok and bool(getattr(args, "rework_on_reject", True)):
                assignment = assignments_by_worker.get(worker_id, {})
                provider_status = provider_status_map(load_provider_statuses(orch.config)).get(provider)
                if provider_status is not None:
                    base_task = str(assignment.get("task") or "")
                    rework_message = (
                        f"{base_task}\n\n"
                        "REWORK REQUIRED: remove/reduce placeholders/stubs/mocks/simulations unless explicitly approved. "
                        "Complete with real implementation and contract-safe changes."
                    )
                    retry = dispatch_worker_task(
                        config=orch.config,
                        store=orch.store,
                        session_id=args.session_id,
                        worker_id=worker_id,
                        provider_status=provider_status,
                        messages=[{"role": "user", "content": rework_message}],
                        timeout_sec=float(args.timeout_sec),
                        bus=orch.bus,
                    )
                    controls_ok = retry.status == "ok"
                    if controls_ok:
                        controls_ok, _ = _enforce_post_dispatch_controls(
                            orch,
                            session_id=args.session_id,
                            worker_id=worker_id,
                            provider=provider,
                            contract_decision_mode=getattr(args, "contract_decision", "ask"),
                            stub_decision_mode=getattr(args, "stub_decision", "ask"),
                        )
                    item["status"] = "ok" if controls_ok else "error"
                    item["details"] = dict(item.get("details") or {})
                    item["details"]["rework_retry"] = retry.as_dict()
            if not controls_ok:
                item["status"] = "error"
                item["details"] = dict(item.get("details") or {})
                item["details"]["post_controls"] = "rejected"

        _apply_dispatch_result_to_registry(
            orch,
            session_id=args.session_id,
            worker_id=worker_id,
            provider=provider,
            status=str(item.get("status") or ""),
        )
        reworked_results.append(item)

    if reworked_results:
        summary["results"] = reworked_results
        summary["workers_ok"] = len([r for r in reworked_results if str(r.get("status")) == "ok"])
        summary["workers_error"] = len(reworked_results) - int(summary["workers_ok"])
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if int(summary.get("workers_error", 0)) == 0 else 1


def _resolve_proposal_file(args: argparse.Namespace) -> Path | None:
    explicit = (args.file or "").strip()
    if explicit:
        path = Path(explicit).expanduser().resolve()
        return path if path.exists() and path.is_file() else None
    if bool(args.pick_file):
        picked = pick_file_with_zenity(base_dir=Path.cwd())
        if picked is not None:
            return picked
    return None


def _proposal_decision(
    *,
    default_decision: str | None = None,
    default_feedback: str | None = None,
) -> tuple[str, str]:
    if default_decision:
        decision = default_decision.strip().lower()
        feedback = (default_feedback or "").strip()
        return decision, feedback

    while True:
        raw = input("Decision [validar/rehacer/cancelar]: ").strip().lower()
        if raw in {"validar", "v"}:
            return "validar", ""
        if raw in {"cancelar", "c", "cancel"}:
            return "cancelar", ""
        if raw in {"rehacer", "r"}:
            feedback = input("Feedback requerido para rehacer: ").strip()
            if feedback:
                return "rehacer", feedback
            print("Feedback obligatorio para rehacer.")
            continue
        print("Entrada no valida.")


def cmd_propose(args: argparse.Namespace) -> int:
    orch = _load_orchestrator()
    proposal_file = _resolve_proposal_file(args)
    if proposal_file is None:
        if args.file:
            print(f"Proposal file not found: {args.file}")
            return 2
        if args.pick_file:
            print("No se pudo seleccionar archivo con zenity.")
            return 2
        print("Use --file <path> o --pick-file.")
        return 2

    source_text = proposal_file.read_text(encoding="utf-8", errors="ignore")
    if not source_text.strip():
        print(f"Archivo vacio: {proposal_file}")
        return 2

    normalized = normalize_proposal_markdown(source_text).as_dict()
    pipeline = ProposalPipeline(orch.config)
    attempts = 0
    feedback = (args.feedback or "").strip()
    proposal_trace_id = f"proposal-{proposal_file.stem}"

    while True:
        attempts += 1
        _print_stage(idx=1, total=5, name="ingest", status="ok", detail=str(proposal_file))
        orch.emit(
            session_id=proposal_trace_id,
            worker_id="system",
            kind="proposal.ingest",
            message=f"source={proposal_file}",
            payload={"attempt": attempts, "normalized_title": normalized.get("title", "")},
        )

        proposal = pipeline.run(
            source_path=proposal_file,
            source_text=source_text,
            feedback=feedback,
        )
        _print_stage(
            idx=2,
            total=5,
            name="groq_fast",
            status=str((proposal.get("groq") or {}).get("status") or "ok"),
            detail=str((proposal.get("groq") or {}).get("provider") or "fallback"),
        )
        _print_stage(
            idx=3,
            total=5,
            name="rasa_struct",
            status=str((proposal.get("rasa") or {}).get("status") or "ok"),
            detail=str((proposal.get("rasa") or {}).get("lines_analyzed") or "0") + " lines",
        )
        _print_stage(idx=4, total=5, name="merge", status="ok", detail="")

        phase_file, todo_file = pipeline.write_generated_docs(root_dir=Path.cwd(), proposal=proposal)
        merged = proposal.get("merged") or {}
        phases = merged.get("phases") or []
        _print_stage(idx=5, total=5, name="review", status="ok", detail=f"phases={len(phases)}")

        orch.emit(
            session_id=proposal_trace_id,
            worker_id="system",
            kind="proposal.review",
            message=f"attempt={attempts} phases={len(phases)}",
            payload={
                "attempt": attempts,
                "phase_file": str(phase_file),
                "todo_file": str(todo_file),
                "summary": str(merged.get("summary") or ""),
            },
        )

        print()
        print(panel("Proposal Final", [str(merged.get("summary") or "")], border_char="-"))
        rows = []
        for phase in phases:
            rows.append(
                [
                    str(phase.get("id") or ""),
                    str(phase.get("name") or ""),
                    str(len(phase.get("tasks") or [])),
                    str(len(phase.get("validations") or [])),
                ]
            )
        if rows:
            print(render_table(["phase", "name", "tasks", "validations"], rows, widths=[8, 48, 8, 12]))
        print(f"Generated: {phase_file}")
        print(f"Generated: {todo_file}")

        decision, new_feedback = _proposal_decision(
            default_decision=(args.decision if attempts == 1 else None),
            default_feedback=(args.feedback if attempts == 1 else None),
        )
        orch.emit(
            session_id=proposal_trace_id,
            worker_id="system",
            kind="proposal.decision",
            message=decision,
            payload={"attempt": attempts},
        )

        if decision == "cancelar":
            print(warn("Flujo cancelado por usuario."))
            return 0
        if decision == "rehacer":
            feedback = new_feedback
            args.decision = None
            args.feedback = None
            continue

        contextpack = pipeline.write_contextpack(
            root_dir=Path.cwd(),
            source_path=proposal_file,
            proposal=proposal,
            topic=args.topic,
        )
        merged = proposal.get("merged") or {}
        proposal_registry_id = orch.registry.create_proposal(
            project_path=str(Path.cwd()),
            source_file=str(proposal_file),
            normalized=normalized,
            merged=merged,
        )
        print(ok(f"Contextpack creado: {contextpack}"))
        print(ok(f"Proposal registrada: {proposal_registry_id}"))

        if not args.start_machinery:
            return 0

        workers = max(1, min(4, int(args.workers)))
        provider_status = load_provider_statuses(orch.config)
        real_providers = ordered_configured_provider_ids(config=orch.config, statuses=provider_status)
        if not real_providers:
            print("No configured providers found. Run `sprintctl providers` and set keys/endpoints first.")
            return 3
        projects = orch.discover_projects(Path(args.scan_root) if args.scan_root else None)
        session = orch.create_session(
            prompt=str(merged.get("summary") or "Refactor incremental validated"),
            workers=workers,
            projects=projects,
            provider_pool=real_providers,
            proposal_id=proposal_registry_id,
        )
        print(ok(f"Sprint session creada: {session.session_id}"))
        if args.autodispatch:
            return cmd_autodispatch(
                argparse.Namespace(
                    session_id=session.session_id,
                    worker=None,
                    timeout_sec=float(args.timeout_sec),
                    rework_on_reject=bool(getattr(args, "rework_on_reject", True)),
                    stub_decision=str(getattr(args, "stub_decision", "ask")),
                    contract_decision=str(getattr(args, "contract_decision", "ask")),
                )
            )
        return 0


def cmd_intent(args: argparse.Namespace) -> int:
    orch = _load_orchestrator()
    router = RasaIntentRouter(orch.config)
    route = router.route(args.text)
    if args.execute:
        return _execute_intent_route(
            orch,
            args.session_id,
            route,
            worker_id=args.worker,
        )
    print(json.dumps(route.as_dict(), indent=2, sort_keys=True))
    return 0


def cmd_journal(args: argparse.Namespace) -> int:
    orch = _load_orchestrator()
    session_id = args.session_id
    if not session_id:
        sessions = orch.store.list_sessions()
        if not sessions:
            print("No sessions.")
            return 2
        session_id = str(sessions[-1].get("session_id") or "")
        if not session_id:
            print("No session id available.")
            return 2
    _render_journal(orch, session_id)
    return 0


def cmd_commit_tree(args: argparse.Namespace) -> int:
    orch = _load_orchestrator()
    projects = _resolve_projects_for_commit_view(
        orch,
        session_id=getattr(args, "session_id", None),
        scan_root=getattr(args, "scan_root", None),
    )
    if getattr(args, "project", None):
        match_project = str(args.project).strip().lower()
        projects = [
            item for item in projects
            if match_project in str(item.get("name") or "").lower()
            or match_project in str(item.get("path") or "").lower()
        ]
    _render_commit_tree_view(
        orch,
        projects=projects,
        max_commits=int(getattr(args, "max_commits", 30)),
        all_branches=bool(getattr(args, "all_branches", True)),
    )
    return 0


def cmd_sessions(_: argparse.Namespace) -> int:
    orch = _load_orchestrator()
    sessions = orch.store.list_sessions()
    if not sessions:
        print("No sessions.")
        return 0
    rows = []
    for item in sessions:
        rows.append(
            [
                item.get("session_id", ""),
                item.get("created_utc", ""),
                str(item.get("workers_requested", "")),
                item.get("status", ""),
                item.get("prompt", ""),
            ]
        )
    print(render_table(["session", "created_utc", "workers", "status", "prompt"], rows, widths=[20, 28, 8, 10, 52]))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DENIS Sprint Orchestrator CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_projects = sub.add_parser("list-projects", help="Discover git projects and show status")
    p_projects.add_argument("--scan-root", default=None)
    p_projects.set_defaults(func=cmd_list_projects)

    p_start = sub.add_parser("start", help="Create sprint session from prompt")
    p_start.add_argument("--prompt", default=None)
    p_start.add_argument("--workers", type=int, default=None)
    p_start.add_argument("--scan-root", default=None)
    p_start.add_argument("--interactive", action="store_true")
    p_start.add_argument("--watch", action="store_true", help="Enter interactive loop after session creation")
    p_start.add_argument("--autodispatch", action="store_true", help="Automatically dispatch tasks for all workers")
    p_start.add_argument("--timeout-sec", type=float, default=45.0, help="Timeout per worker dispatch")
    p_start.add_argument("--simple", action="store_true", help="Open guided simple menu after session creation")
    p_start.add_argument("--stub-decision", choices=["ask", "yes", "no"], default="ask")
    p_start.add_argument("--contract-decision", choices=["ask", "yes", "no"], default="ask")
    p_start.add_argument("--rework-on-reject", action=argparse.BooleanOptionalAction, default=True)
    p_start.set_defaults(func=cmd_start)

    p_simple = sub.add_parser("simple", help="Start sprint in guided simple mode (recommended)")
    p_simple.add_argument("--prompt", default=None)
    p_simple.add_argument("--workers", type=int, default=None)
    p_simple.add_argument("--scan-root", default=None)
    p_simple.add_argument("--autodispatch", action="store_true")
    p_simple.add_argument("--timeout-sec", type=float, default=45.0)
    p_simple.add_argument("--stub-decision", choices=["ask", "yes", "no"], default="ask")
    p_simple.add_argument("--contract-decision", choices=["ask", "yes", "no"], default="ask")
    p_simple.add_argument("--rework-on-reject", action=argparse.BooleanOptionalAction, default=True)
    p_simple.set_defaults(func=cmd_simple)

    p_providers = sub.add_parser("providers", help="Show provider load status (real-only)")
    p_providers.set_defaults(func=cmd_providers)

    p_template = sub.add_parser("providers-template", help="Print/write provider env template")
    p_template.add_argument("--out", default=None, help="Optional output file path")
    p_template.set_defaults(func=cmd_providers_template)

    p_mcp = sub.add_parser("mcp-tools", help="List real MCP tools from Denis MCP endpoint")
    p_mcp.add_argument("--session-id", default=None, help="Optional session id to append catalog event")
    p_mcp.add_argument("--worker", default="worker-1")
    p_mcp.set_defaults(func=cmd_mcp_tools)

    p_sessions = sub.add_parser("sessions", help="List saved sessions")
    p_sessions.set_defaults(func=cmd_sessions)

    p_guide = sub.add_parser("guide", help="Show guided help panel")
    p_guide.set_defaults(func=cmd_guide)

    p_journal = sub.add_parser("journal", help="Show git/sprint journal (pending/in-progress/done + providers)")
    p_journal.add_argument("session_id", nargs="?", default=None)
    p_journal.set_defaults(func=cmd_journal)

    p_commit_tree = sub.add_parser("commit-tree", help="Show commit-tree management view by project")
    p_commit_tree.add_argument("--session-id", default=None, help="Use projects from a known sprint session")
    p_commit_tree.add_argument("--scan-root", default=None, help="Optional root for project discovery")
    p_commit_tree.add_argument("--project", default=None, help="Optional project name/path filter")
    p_commit_tree.add_argument("--max-commits", type=int, default=30)
    p_commit_tree.add_argument("--all-branches", action=argparse.BooleanOptionalAction, default=True)
    p_commit_tree.set_defaults(func=cmd_commit_tree)

    p_dashboard = sub.add_parser("dashboard", help="Show visual dashboard for a session")
    p_dashboard.add_argument("session_id")
    p_dashboard.set_defaults(func=cmd_dashboard)

    p_manager = sub.add_parser("manager", help="Unified manager view with keyboard nav (j/k,h/l,w/t,d,f,q)")
    p_manager.add_argument("session_id")
    p_manager.add_argument("--project", default=None)
    p_manager.add_argument("--worker", default=None)
    p_manager.add_argument("--kind", default=None)
    p_manager.add_argument("--max-commits", type=int, default=10)
    p_manager.add_argument("--limit", type=int, default=20)
    p_manager.add_argument("--follow", action=argparse.BooleanOptionalAction, default=True)
    p_manager.add_argument("--interval-sec", type=float, default=1.0)
    p_manager.set_defaults(func=cmd_manager)

    p_monitor = sub.add_parser("monitor", help="Live monitor with phases and worker chat")
    p_monitor.add_argument("session_id")
    p_monitor.add_argument("--worker", default=None)
    p_monitor.add_argument("--kind", default=None)
    p_monitor.add_argument("--limit", type=int, default=25)
    p_monitor.add_argument("--follow", action=argparse.BooleanOptionalAction, default=True)
    p_monitor.add_argument("--interval-sec", type=float, default=1.0)
    p_monitor.add_argument("--chat-only", action=argparse.BooleanOptionalAction, default=False)
    p_monitor.set_defaults(func=cmd_monitor)

    p_noc = sub.add_parser("noc", help="Live NOC screen (dashboard + event stream)")
    p_noc.add_argument("session_id")
    p_noc.add_argument("--worker", default=None)
    p_noc.add_argument("--kind", default=None)
    p_noc.add_argument("--limit", type=int, default=20)
    p_noc.add_argument("--interval-sec", type=float, default=1.0)
    p_noc.set_defaults(func=cmd_noc)

    p_tail = sub.add_parser("tail", help="Show events from a session")
    p_tail.add_argument("session_id")
    p_tail.add_argument("--worker", default=None)
    p_tail.add_argument("--kind", default=None, help="Filter by event kind prefix")
    p_tail.add_argument("--limit", type=int, default=60)
    p_tail.add_argument("--follow", action="store_true")
    p_tail.add_argument("--interval-sec", type=float, default=1.0)
    p_tail.set_defaults(func=cmd_tail)

    p_logs = sub.add_parser("logs", help="Read event-bus audit log (JSONL) as chat stream")
    p_logs.add_argument("--session-id", default=None)
    p_logs.add_argument("--limit", type=int, default=60)
    p_logs.add_argument("--follow", action=argparse.BooleanOptionalAction, default=False)
    p_logs.add_argument("--interval-sec", type=float, default=1.0)
    p_logs.set_defaults(func=cmd_logs)

    p_validate = sub.add_parser("validate", help="Run validation target and log as events")
    p_validate.add_argument("session_id")
    p_validate.add_argument("target", choices=list(TARGET_NAMES))
    p_validate.add_argument("--worker", default="worker-2")
    p_validate.set_defaults(func=cmd_validate)

    p_run = sub.add_parser("run", help="Run a terminal command and stream output into session events")
    p_run.add_argument("session_id")
    p_run.add_argument("--worker", default="worker-1")
    p_run.add_argument("command", nargs=argparse.REMAINDER)
    p_run.set_defaults(func=cmd_run)

    p_adapt = sub.add_parser("adapt", help="Show provider-specific JSON payload adaptation")
    p_adapt.add_argument("provider")
    p_adapt.add_argument("--message", required=True)
    p_adapt.add_argument("--max-tokens", type=int, default=None)
    p_adapt.add_argument("--stream", action="store_true")
    p_adapt.set_defaults(func=cmd_adapt)

    p_dispatch = sub.add_parser("dispatch", help="Dispatch real worker call (API or Celery queue)")
    p_dispatch.add_argument("session_id")
    p_dispatch.add_argument("provider")
    p_dispatch.add_argument("--worker", default="worker-1")
    p_dispatch.add_argument("--message", required=True)
    p_dispatch.add_argument("--timeout-sec", type=float, default=45.0)
    p_dispatch.add_argument("--stub-decision", choices=["ask", "yes", "no"], default="ask")
    p_dispatch.add_argument("--contract-decision", choices=["ask", "yes", "no"], default="ask")
    p_dispatch.add_argument("--rework-on-reject", action=argparse.BooleanOptionalAction, default=True)
    p_dispatch.set_defaults(func=cmd_dispatch)

    p_autodispatch = sub.add_parser("autodispatch", help="Dispatch all worker tasks for a session automatically")
    p_autodispatch.add_argument("session_id")
    p_autodispatch.add_argument("--worker", default=None, help="Optional single worker_id filter")
    p_autodispatch.add_argument("--timeout-sec", type=float, default=45.0)
    p_autodispatch.add_argument("--stub-decision", choices=["ask", "yes", "no"], default="ask")
    p_autodispatch.add_argument("--contract-decision", choices=["ask", "yes", "no"], default="ask")
    p_autodispatch.add_argument("--rework-on-reject", action=argparse.BooleanOptionalAction, default=True)
    p_autodispatch.set_defaults(func=cmd_autodispatch)

    p_propose = sub.add_parser("propose", help="Build phased plan from proposal markdown using Groq+Rasa")
    p_propose.add_argument("--file", default=None, help="Path to proposal markdown")
    p_propose.add_argument("--pick-file", action="store_true", help="Open Ubuntu file selector (zenity)")
    p_propose.add_argument("--topic", default=None, help="Optional contextpack topic label")
    p_propose.add_argument("--decision", choices=["validar", "rehacer", "cancelar"], default=None)
    p_propose.add_argument("--feedback", default=None, help="Required when decision=rehacer")
    p_propose.add_argument("--workers", type=int, default=2)
    p_propose.add_argument("--scan-root", default=None)
    p_propose.add_argument("--start-machinery", action=argparse.BooleanOptionalAction, default=True)
    p_propose.add_argument("--autodispatch", action="store_true")
    p_propose.add_argument("--timeout-sec", type=float, default=45.0)
    p_propose.add_argument("--stub-decision", choices=["ask", "yes", "no"], default="ask")
    p_propose.add_argument("--contract-decision", choices=["ask", "yes", "no"], default="ask")
    p_propose.add_argument("--rework-on-reject", action=argparse.BooleanOptionalAction, default=True)
    p_propose.set_defaults(func=cmd_propose)

    p_intent = sub.add_parser("intent", help="Route natural language through Rasa gate")
    p_intent.add_argument("session_id")
    p_intent.add_argument("--text", required=True)
    p_intent.add_argument("--worker", default="worker-1")
    p_intent.add_argument("--execute", action="store_true", help="Execute routed action instead of printing route")
    p_intent.set_defaults(func=cmd_intent)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
