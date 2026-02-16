"""Tool Registry Wiring Tests.

Verifies that the tool registry is populated and the Executor can
actually execute steps using real tool implementations.
"""

import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from denis_unified_v1.cognition.tools import build_tool_registry, list_files, grep_search, read_file, run_command
from denis_unified_v1.cognition.executor import Executor, save_toolchain_log
from denis_unified_v1.actions.models import (
    ActionPlanCandidate,
    ActionStep,
    ToolCall,
    StopCondition,
    StopOp,
)


def test_build_tool_registry_has_all_planner_tools():
    """Registry must contain all tools referenced by the planner."""
    registry = build_tool_registry()
    required = {"list_files", "grep_search", "read_file", "run_command"}
    assert required.issubset(set(registry.keys())), (
        f"Missing tools: {required - set(registry.keys())}"
    )


def test_list_files_finds_python_files():
    """list_files should find .py files in the project."""
    result = list_files(pattern="*.py", directory="denis_unified_v1/cognition")
    assert "executor.py" in result
    assert "tools.py" in result


def test_grep_search_finds_pattern():
    """grep_search should find known patterns in the codebase."""
    result = grep_search(pattern="class Executor", path="denis_unified_v1/cognition/executor.py")
    assert "class Executor" in result
    assert "no_matches_found" not in result


def test_read_file_returns_content():
    """read_file should return file contents."""
    result = read_file("denis_unified_v1/actions/models.py")
    assert "class StepStatus" in result
    assert "file_not_found" not in result


def test_read_file_not_found():
    """read_file should return error for missing files."""
    result = read_file("nonexistent_file_xyz.py")
    assert "file_not_found" in result


def test_run_command_echo():
    """run_command should execute simple shell commands."""
    result = run_command("echo hello_denis")
    assert "hello_denis" in result


def test_run_command_exit_code():
    """run_command should report non-zero exit codes."""
    result = run_command("false")
    assert "exit_code=" in result


def test_executor_with_real_tools_runs_plan(tmp_path):
    """Executor with real tool registry should execute a plan to completion."""
    registry = build_tool_registry()
    executor = Executor(tool_registry=registry, evidence_dir=tmp_path)

    plan = ActionPlanCandidate(
        candidate_id="test_real_tools",
        intent="run_tests_ci",
        steps=[
            ActionStep(
                step_id="step_list",
                description="List test files",
                read_only=True,
                tool_calls=[ToolCall(name="list_files", args={"pattern": "*test*.py", "directory": "tests"})],
            ),
            ActionStep(
                step_id="step_echo",
                description="Run echo command",
                read_only=True,
                tool_calls=[ToolCall(name="run_command", args={"cmd": "echo 'tests passed'"})],
            ),
        ],
    )

    result = executor.execute_plan(plan, context={})

    assert result.status == "success", f"Expected success, got {result.status}: {result.reason_code}"
    assert len(result.step_results) == 2
    assert result.step_results[0].status.value == "ok"
    assert result.step_results[1].status.value == "ok"
    assert "test_" in result.step_results[0].output  # should find test files


def test_executor_blocked_steps_still_logged(tmp_path):
    """Steps with missing tools should be blocked, not silently dropped."""
    # Only register list_files, not run_command
    registry = {"list_files": list_files}
    executor = Executor(tool_registry=registry, evidence_dir=tmp_path)

    plan = ActionPlanCandidate(
        candidate_id="test_partial",
        intent="debug_repo",
        steps=[
            ActionStep(
                step_id="step_ok",
                description="List files (tool exists)",
                read_only=True,
                tool_calls=[ToolCall(name="list_files", args={"pattern": "*.py"})],
            ),
            ActionStep(
                step_id="step_blocked",
                description="Run command (tool missing)",
                read_only=True,
                tool_calls=[ToolCall(name="run_command", args={"cmd": "echo x"})],
                on_failure="fallback",
            ),
        ],
    )

    result = executor.execute_plan(plan, context={})

    assert len(result.step_results) == 2
    assert result.step_results[0].status.value == "ok"
    assert result.step_results[1].status.value == "blocked"
    assert "capability_missing" in result.step_results[1].reason_codes


def test_toolchain_log_with_real_execution(tmp_path):
    """Full flow: execute with real tools -> save toolchain log -> verify."""
    registry = build_tool_registry()
    executor = Executor(tool_registry=registry, evidence_dir=tmp_path)

    plan = ActionPlanCandidate(
        candidate_id="test_log_flow",
        intent="ops_health_check",
        steps=[
            ActionStep(
                step_id="check_disk",
                description="Check disk",
                read_only=True,
                tool_calls=[ToolCall(name="run_command", args={"cmd": "df -h /"})],
            ),
        ],
    )

    result = executor.execute_plan(plan, context={})
    path = save_toolchain_log(result, tmp_path, "test_log_real")

    import json

    with open(path) as f:
        data = json.load(f)

    assert data["kind"] == "toolchain_step_log_v1"
    assert data["status"] == "success"
    assert len(data["step_results"]) == 1
def test_executor_tools_medium_blocks_run_command(tmp_path):
    """run_command blocked in medium confidence."""
    registry = build_tool_registry_v2()
    executor = Executor(tool_registry=registry, evidence_dir=tmp_path)

    plan = ActionPlanCandidate(
        candidate_id="test_medium_run",
        intent="debug_repo",
        steps=[
            ActionStep(
                step_id="step_run",
                description="Run command",
                read_only=False,
                tool_calls=[ToolCall(name="run_command", args={"cmd": "echo test"})],
            ),
        ],
    )

    context = {"confidence_band": "medium"}
    result = executor.execute_plan(plan, context)

    assert len(result.step_results) == 1
    assert result.step_results[0].status.value == "failed"
    assert "belt_filtered" in result.step_results[0].reason_codes


def test_executor_tools_medium_allows_read_file(tmp_path):
    """read_file allowed in medium."""
    registry = build_tool_registry_v2()
    executor = Executor(tool_registry=registry, evidence_dir=tmp_path)

    plan = ActionPlanCandidate(
        candidate_id="test_medium_read",
        intent="debug_repo",
        steps=[
            ActionStep(
                step_id="step_read",
                description="Read file",
                read_only=True,
                tool_calls=[ToolCall(name="read_file", args={"path": "denis_unified_v1/actions/models.py", "max_lines": 10})],
            ),
        ],
    )

    context = {"confidence_band": "medium"}
    result = executor.execute_plan(plan, context)

    assert len(result.step_results) == 1
    assert result.step_results[0].status.value == "ok"
    assert "class StepStatus" in result.step_results[0].output


def test_executor_tools_high_allows_pytest_command(tmp_path):
    """pytest allowed in high."""
    registry = build_tool_registry_v2()
    executor = Executor(tool_registry=registry, evidence_dir=tmp_path)

    plan = ActionPlanCandidate(
        candidate_id="test_high_pytest",
        intent="run_tests_ci",
        steps=[
            ActionStep(
                step_id="step_pytest",
                description="Run pytest",
                read_only=True,
                tool_calls=[ToolCall(name="run_command", args={"cmd": "pytest --version"})],
            ),
        ],
    )

    context = {"confidence_band": "high"}
    result = executor.execute_plan(plan, context)

    assert len(result.step_results) == 1
    assert result.step_results[0].status.value == "ok"
    assert "pytest" in result.step_results[0].output


def test_executor_unknown_tool_logs_policy_error(tmp_path):
    """Unknown tool fails gracefully."""
    registry = build_tool_registry_v2()
    executor = Executor(tool_registry=registry, evidence_dir=tmp_path)

    plan = ActionPlanCandidate(
        candidate_id="test_unknown",
        intent="chat",
        steps=[
            ActionStep(
                step_id="step_unknown",
                description="Unknown tool",
                read_only=True,
                tool_calls=[ToolCall(name="unknown_tool", args={})],
            ),
        ],
    )

    context = {"confidence_band": "high"}
    result = executor.execute_plan(plan, context)

    assert len(result.step_results) == 1
    assert result.step_results[0].status.value == "failed"
    assert "Tool not found" in result.step_results[0].error
