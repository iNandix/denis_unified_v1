"""E2E Tests - High-Value End-to-End Validations

Tests that validate the complete DENIS unified system flow from user request to execution.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
import pytest
import httpx
from typing import Dict, Any

# Import the components we need to test
# Skip all E2E tests - require full server runtime
pytestmark = pytest.mark.skip(reason="Requires full server runtime")

try:
    from denis_unified_v1.kernel.decision_trace import get_trace_sink
    from denis_unified_v1.sprint_orchestrator import get_sprint_manager

    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False


@pytest.fixture(scope="session")
def api_client():
    """FastAPI test client configured for DENIS."""
    from fastapi.testclient import TestClient
    from api.fastapi_server import create_app

    app = create_app()
    return TestClient(app)


@pytest.fixture
def temp_trace_sink(tmp_path):
    """Temporary trace sink for testing."""
    from denis_unified_v1.kernel.decision_trace import JsonlTraceSink

    trace_file = tmp_path / "test_traces.jsonl"
    sink = JsonlTraceSink(str(trace_file))
    return sink, trace_file


@pytest.mark.e2e
@pytest.mark.skipif(not HAS_DEPS, reason="DENIS dependencies not available")
class TestE2EHappyPath:
    """E2E-1: Happy path with tools + evidence validation."""

    def test_happy_path_with_tools_and_evidence(
        self, api_client, temp_trace_sink, monkeypatch
    ):
        """Test complete pipeline: API → Kernel → Tools → Verify → Trace → Response."""
        # Skip if running in contract test mode (would make responses deterministic)
        if os.getenv("DENIS_CONTRACT_TEST_MODE") == "1":
            pytest.skip("E2E-1 skipped in contract test mode (deterministic responses)")

        # Skip if we can't test real tools (no external deps in CI)
        if os.getenv("CI") and not os.getenv("DENIS_TEST_REAL_TOOLS"):
            pytest.skip(
                "E2E-1 requires real tool execution, skipped in CI without DENIS_TEST_REAL_TOOLS"
            )

        sink, trace_file = temp_trace_sink

        # Set up temp trace sink for this test
        import denis_unified_v1.kernel.decision_trace as dt

        original_sink = dt._trace_sink
        dt._trace_sink = sink

        try:
            # Input: prompt that requires tool usage
            prompt = "Analyze this Python file and tell me what functions it contains"

            # Create a test Python file for the tool to analyze
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write("""
def calculate_fibonacci(n):
    '''Calculate nth fibonacci number'''
    if n <= 1:
        return n
    return calculate_fibonacci(n-1) + calculate_fibonacci(n-2)

def is_prime(num):
    '''Check if a number is prime'''
    if num < 2:
        return False
    for i in range(2, int(num**0.5) + 1):
        if num % i == 0:
            return False
    return True

class MathUtils:
    '''Utility class for mathematical operations'''

    @staticmethod
    def factorial(n):
        '''Calculate factorial of n'''
        if n == 0:
            return 1
        return n * MathUtils.factorial(n-1)
""")
                test_file_path = f.name

            # Make the request with tools
            response = api_client.post(
                "/v1/chat/completions",
                json={
                    "model": "denis-cognitive",
                    "messages": [
                        {
                            "role": "user",
                            "content": f"{prompt}\n\nFile to analyze: {test_file_path}",
                        }
                    ],
                    "tools": [
                        {
                            "type": "function",
                            "function": {
                                "name": "analyze_python_file",
                                "description": "Analyze a Python file and extract information",
                                "parameters": {
                                    "type": "object",
                                    "properties": {
                                        "file_path": {
                                            "type": "string",
                                            "description": "Path to the Python file to analyze",
                                        }
                                    },
                                    "required": ["file_path"],
                                },
                            },
                        }
                    ],
                    "max_tokens": 200,
                },
            )

            # Assert: /v1/chat/completions responds OK
            assert response.status_code == 200
            data = response.json()

            # Assert: extensions["denis.ai"].evidence_refs not empty
            extensions = data.get("extensions", {})
            denis_extensions = extensions.get("denis.ai", {})
            evidence_refs = denis_extensions.get("evidence_refs", [])
            assert len(evidence_refs) > 0, (
                f"Expected evidence_refs, got: {evidence_refs}"
            )

            # Assert: attribution_flags contains DERIVED_FROM_TOOL_OUTPUT
            attribution_flags = denis_extensions.get("attribution_flags", [])
            assert "DERIVED_FROM_TOOL_OUTPUT" in attribution_flags, (
                f"Expected DERIVED_FROM_TOOL_OUTPUT in flags, got: {attribution_flags}"
            )

            # Assert: Header X-Denis-Trace-Id present
            assert "X-Denis-Trace-Id" in response.headers, (
                f"Missing X-Denis-Trace-Id header, got headers: {dict(response.headers)}"
            )

            trace_id = response.headers["X-Denis-Trace-Id"]
            assert trace_id, f"Empty trace ID: {trace_id}"

            # Assert: DecisionTrace in sink has complete phases, budget, spans
            # Wait a bit for trace to be written
            time.sleep(0.1)

            traces = []
            if trace_file.exists():
                with open(trace_file, "r") as f:
                    for line in f:
                        if line.strip():
                            traces.append(json.loads(line))

            # Find our trace
            our_trace = None
            for trace in traces:
                if trace.get("trace_id") == trace_id:
                    our_trace = trace
                    break

            assert our_trace is not None, (
                f"Trace {trace_id} not found in {len(traces)} traces"
            )

            # Assert phases are complete
            phases = our_trace.get("phases", [])
            assert len(phases) > 0, f"Expected phases, got: {phases}"

            # Check each phase has required fields
            for phase in phases:
                required_fields = [
                    "name",
                    "span_id",
                    "start_ts_ms",
                    "end_ts_ms",
                    "duration_ms",
                    "budget_planned",
                    "budget_actual",
                    "budget_delta",
                ]
                for field in required_fields:
                    assert field in phase, f"Phase missing field '{field}': {phase}"

            # Assert budget structure
            budget = our_trace.get("budget", {})
            assert "planned_total" in budget, (
                f"Missing planned_total in budget: {budget}"
            )
            assert "actual_total" in budget, f"Missing actual_total in budget: {budget}"
            assert "delta_total" in budget, f"Missing delta_total in budget: {budget}"

            # Assert spans structure
            spans = our_trace.get("spans", [])
            assert len(spans) > 0, f"Expected spans, got: {spans}"

            # Check span structure
            for span in spans:
                required_span_fields = [
                    "span_id",
                    "name",
                    "start_ts_ms",
                    "parent_span_id",
                    "duration_ms",
                ]
                for field in required_span_fields:
                    assert field in span, f"Span missing field '{field}': {span}"

            print(f"✅ E2E-1 PASSED: Complete pipeline validated")
            print(f"   - Trace ID: {trace_id}")
            print(f"   - Evidence refs: {len(evidence_refs)}")
            print(f"   - Attribution flags: {attribution_flags}")
            print(f"   - Phases: {len(phases)}, Spans: {len(spans)}")

        finally:
            # Clean up temp file
            try:
                os.unlink(test_file_path)
            except:
                pass
            # Restore original sink
            dt._trace_sink = original_sink


@pytest.mark.e2e
@pytest.mark.skipif(not HAS_DEPS, reason="DENIS dependencies not available")
class TestE2EStrictMode:
    """E2E-2: Strict mode without evidence validation."""

    def test_strict_mode_without_evidence(self, api_client, temp_trace_sink):
        """Test safety seam: strict mode with unverifiable claims."""
        sink, trace_file = temp_trace_sink

        # Set up temp trace sink for this test
        import denis_unified_v1.kernel.decision_trace as dt

        original_sink = dt._trace_sink
        dt._trace_sink = sink

        try:
            # Input: prompt that cannot generate real evidence + safety_mode=strict
            prompt = "What do you think about the meaning of life? Give me a philosophical answer."

            response = api_client.post(
                "/v1/chat/completions",
                json={
                    "model": "denis-cognitive",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 150,
                },
                headers={"X-Denis-Safety-Mode": "strict"},
            )

            assert response.status_code == 200
            data = response.json()

            # Assert: extensions present and contain safety info
            extensions = data.get("extensions", {})
            denis_extensions = extensions.get("denis.ai", {})
            assert denis_extensions, f"Expected denis.ai extensions, got: {extensions}"

            # Assert: SAFETY_MODE_STRICT_APPLIED flag
            attribution_flags = denis_extensions.get("attribution_flags", [])
            assert "SAFETY_MODE_STRICT_APPLIED" in attribution_flags, (
                f"Expected SAFETY_MODE_STRICT_APPLIED in flags, got: {attribution_flags}"
            )

            # Assert: disclaimers not empty
            disclaimers = denis_extensions.get("disclaimers", [])
            assert len(disclaimers) > 0, (
                f"Expected disclaimers in strict mode, got: {disclaimers}"
            )

            # Assert: evidence_refs empty or with low confidence
            evidence_refs = denis_extensions.get("evidence_refs", [])
            if evidence_refs:
                # If evidence exists, check confidence is low
                for ref in evidence_refs:
                    confidence = ref.get("confidence", 1.0)
                    assert confidence < 0.7, (
                        f"High confidence evidence in strict mode: {ref}"
                    )

            # Assert: either NO_EVIDENCE_AVAILABLE or ASSUMPTION_MADE
            has_no_evidence = "NO_EVIDENCE_AVAILABLE" in attribution_flags
            has_assumption = "ASSUMPTION_MADE" in attribution_flags
            assert has_no_evidence or has_assumption, (
                f"Expected NO_EVIDENCE_AVAILABLE or ASSUMPTION_MADE, got: {attribution_flags}"
            )

            # Assert: Trace exists and has verify phase
            assert "X-Denis-Trace-Id" in response.headers
            trace_id = response.headers["X-Denis-Trace-Id"]

            # Wait for trace
            time.sleep(0.1)

            traces = []
            if trace_file.exists():
                with open(trace_file, "r") as f:
                    for line in f:
                        if line.strip():
                            traces.append(json.loads(line))

            our_trace = None
            for trace in traces:
                if trace.get("trace_id") == trace_id:
                    our_trace = trace
                    break

            assert our_trace is not None, f"Trace {trace_id} not found"

            # Check for verify phase
            phases = our_trace.get("phases", [])
            verify_phases = [p for p in phases if p.get("name") == "verify"]
            assert len(verify_phases) > 0, (
                f"Expected verify phase, got phases: {[p.get('name') for p in phases]}"
            )

            print(f"✅ E2E-2 PASSED: Strict mode safety validated")
            print(f"   - Trace ID: {trace_id}")
            print(f"   - Attribution flags: {attribution_flags}")
            print(f"   - Disclaimers: {len(disclaimers)}")
            print(f"   - Evidence refs: {len(evidence_refs)}")
            print(f"   - Verify phases: {len(verify_phases)}")

        finally:
            # Restore original sink
            dt._trace_sink = original_sink


@pytest.mark.e2e
@pytest.mark.skipif(not HAS_DEPS, reason="DENIS dependencies not available")
class TestE2ESprintManagerIntegration:
    """E2E-3: Sprint Manager integration with Denis and planning."""

    @pytest.mark.asyncio
    async def test_sprint_manager_integration(self, tmp_path, monkeypatch):
        """Test Sprint Manager → Denis → Plan integration."""
        # Set state directory to temp path for complete isolation
        state_dir = tmp_path / "denis_state"
        state_dir.mkdir()
        monkeypatch.setenv("DENIS_STATE_DIR", str(state_dir))

        from denis_unified_v1.sprint_orchestrator import (
            get_sprint_manager,
            SprintRequest,
        )

        # Create a temp project for testing
        project_path = tmp_path / "test_project"
        project_path.mkdir()

        # Create git repo
        import subprocess

        subprocess.run(
            ["git", "init"], cwd=project_path, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=project_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=project_path,
            check=True,
            capture_output=True,
        )

        # Add a Python file
        test_file = project_path / "main.py"
        test_file.write_text("""
def hello_world():
    '''A simple hello world function'''
    return "Hello, World!"

if __name__ == "__main__":
    print(hello_world())
""")

        # Commit
        subprocess.run(
            ["git", "add", "."], cwd=project_path, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=project_path,
            check=True,
            capture_output=True,
        )

        # Get sprint manager
        sprint_mgr = get_sprint_manager()

        # Create sprint request
        request = SprintRequest(
            prompt="Implement a simple calculator class",
            project_paths=[str(project_path)],
            worker_count=2,
        )

        # Create sprint
        result = await sprint_mgr.create_sprint(request)

        assert result.status == "created"
        assert result.session_id
        assert len(result.assignments) == 2  # 2 workers
        assert result.level_analysis["summary"]["total_files"] > 0

        # Validate assignments have required structure
        for assignment in result.assignments:
            assert "worker_id" in assignment
            assert "level" in assignment
            assert "crew" in assignment
            assert "capabilities" in assignment
            assert "task_focus" in assignment
            assert "validation_requirements" in assignment

        print(f"✅ E2E-3 PASSED: Sprint Manager integration validated")
        print(f"   - Session ID: {result.session_id}")
        print(f"   - Assignments: {len(result.assignments)}")
        print(f"   - Files analyzed: {result.level_analysis['summary']['total_files']}")
        print(f"   - Health score: {result.health_score}/100")

        # Clean up
        await sprint_mgr.cleanup_sprint(result.session_id)


@pytest.mark.skipif(not HAS_DEPS, reason="DENIS dependencies not available")
class TestE2EHappyPath:
    """E2E-1: Happy path with tools + evidence validation."""

    def test_happy_path_with_tools_and_evidence(self, api_client, temp_trace_sink):
        """Test complete pipeline: API → Kernel → Tools → Verify → Trace → Response."""
        sink, trace_file = temp_trace_sink

        # Set up temp trace sink for this test
        import denis_unified_v1.kernel.decision_trace as dt

        original_sink = dt._trace_sink
        dt._trace_sink = sink

        try:
            # Input: prompt that requires tool usage
            prompt = "Analyze this Python file and tell me what functions it contains"

            # Create a test Python file for the tool to analyze
            test_code = """
def calculate_fibonacci(n):
    '''Calculate nth fibonacci number'''
    if n <= 1:
        return n
    return calculate_fibonacci(n-1) + calculate_fibonacci(n-2)

def is_prime(num):
    '''Check if a number is prime'''
    if num < 2:
        return False
    for i in range(2, int(num**0.5) + 1):
        if num % i == 0:
            return False
    return True

class MathUtils:
    '''Utility class for mathematical operations'''

    @staticmethod
    def factorial(n):
        '''Calculate factorial of n'''
        if n == 0:
            return 1
        return n * MathUtils.factorial(n-1)
"""

            # Make the request with tools
            response = api_client.post(
                "/v1/chat/completions",
                json={
                    "model": "denis-cognitive",
                    "messages": [{"role": "user", "content": prompt}],
                    "tools": [
                        {
                            "type": "function",
                            "function": {
                                "name": "analyze_python_file",
                                "description": "Analyze a Python file and extract information",
                                "parameters": {
                                    "type": "object",
                                    "properties": {
                                        "file_path": {
                                            "type": "string",
                                            "description": "Path to the Python file to analyze",
                                        }
                                    },
                                    "required": ["file_path"],
                                },
                            },
                        }
                    ],
                    "max_tokens": 200,
                },
            )

            # Assert: /v1/chat/completions responds OK
            assert response.status_code == 200
            data = response.json()

            # Assert: extensions["denis.ai"].evidence_refs not empty
            extensions = data.get("extensions", {})
            denis_extensions = extensions.get("denis.ai", {})
            evidence_refs = denis_extensions.get("evidence_refs", [])
            assert len(evidence_refs) > 0, (
                f"Expected evidence_refs, got: {evidence_refs}"
            )

            # Assert: attribution_flags contains DERIVED_FROM_TOOL_OUTPUT
            attribution_flags = denis_extensions.get("attribution_flags", [])
            assert "DERIVED_FROM_TOOL_OUTPUT" in attribution_flags, (
                f"Expected DERIVED_FROM_TOOL_OUTPUT in flags, got: {attribution_flags}"
            )

            # Assert: Header X-Denis-Trace-Id present
            assert "X-Denis-Trace-Id" in response.headers, (
                f"Missing X-Denis-Trace-Id header, got headers: {dict(response.headers)}"
            )

            trace_id = response.headers["X-Denis-Trace-Id"]
            assert trace_id, f"Empty trace ID: {trace_id}"

            # Assert: DecisionTrace in sink has complete phases, budget, spans
            # Wait a bit for trace to be written
            time.sleep(0.1)

            traces = []
            if trace_file.exists():
                with open(trace_file, "r") as f:
                    for line in f:
                        if line.strip():
                            traces.append(json.loads(line))

            # Find our trace
            our_trace = None
            for trace in traces:
                if trace.get("trace_id") == trace_id:
                    our_trace = trace
                    break

            assert our_trace is not None, (
                f"Trace {trace_id} not found in {len(traces)} traces"
            )

            # Assert phases are complete
            phases = our_trace.get("phases", [])
            assert len(phases) > 0, f"Expected phases, got: {phases}"

            # Check each phase has required fields
            for phase in phases:
                required_fields = [
                    "name",
                    "span_id",
                    "start_ts_ms",
                    "end_ts_ms",
                    "duration_ms",
                    "budget_planned",
                    "budget_actual",
                    "budget_delta",
                ]
                for field in required_fields:
                    assert field in phase, f"Phase missing field '{field}': {phase}"

            # Assert budget structure
            budget = our_trace.get("budget", {})
            assert "planned_total" in budget, (
                f"Missing planned_total in budget: {budget}"
            )
            assert "actual_total" in budget, f"Missing actual_total in budget: {budget}"
            assert "delta_total" in budget, f"Missing delta_total in budget: {budget}"

            # Assert spans structure
            spans = our_trace.get("spans", [])
            assert len(spans) > 0, f"Expected spans, got: {spans}"

            # Check span structure
            for span in spans:
                required_span_fields = [
                    "span_id",
                    "name",
                    "start_ts_ms",
                    "parent_span_id",
                    "duration_ms",
                ]
                for field in required_span_fields:
                    assert field in span, f"Span missing field '{field}': {span}"

            print(f"✅ E2E-1 PASSED: Complete pipeline validated")
            print(f"   - Trace ID: {trace_id}")
            print(f"   - Evidence refs: {len(evidence_refs)}")
            print(f"   - Attribution flags: {attribution_flags}")
            print(f"   - Phases: {len(phases)}, Spans: {len(spans)}")

        finally:
            # Restore original sink
            dt._trace_sink = original_sink


@pytest.mark.skipif(not HAS_DEPS, reason="DENIS dependencies not available")
class TestE2EStrictMode:
    """E2E-2: Strict mode without evidence validation."""

    def test_strict_mode_without_evidence(self, api_client, temp_trace_sink):
        """Test safety seam: strict mode with unverifiable claims."""
        sink, trace_file = temp_trace_sink

        # Set up temp trace sink for this test
        import denis_unified_v1.kernel.decision_trace as dt

        original_sink = dt._trace_sink
        dt._trace_sink = sink

        try:
            # Input: prompt that cannot generate real evidence + safety_mode=strict
            prompt = "What do you think about the meaning of life? Give me a philosophical answer."

            response = api_client.post(
                "/v1/chat/completions",
                json={
                    "model": "denis-cognitive",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 150,
                },
                headers={"X-Denis-Safety-Mode": "strict"},
            )

            assert response.status_code == 200
            data = response.json()

            # Assert: extensions present and contain safety info
            extensions = data.get("extensions", {})
            denis_extensions = extensions.get("denis.ai", {})
            assert denis_extensions, f"Expected denis.ai extensions, got: {extensions}"

            # Assert: SAFETY_MODE_STRICT_APPLIED flag
            attribution_flags = denis_extensions.get("attribution_flags", [])
            assert "SAFETY_MODE_STRICT_APPLIED" in attribution_flags, (
                f"Expected SAFETY_MODE_STRICT_APPLIED in flags, got: {attribution_flags}"
            )

            # Assert: disclaimers not empty
            disclaimers = denis_extensions.get("disclaimers", [])
            assert len(disclaimers) > 0, (
                f"Expected disclaimers in strict mode, got: {disclaimers}"
            )

            # Assert: evidence_refs empty or with low confidence
            evidence_refs = denis_extensions.get("evidence_refs", [])
            if evidence_refs:
                # If evidence exists, check confidence is low
                for ref in evidence_refs:
                    confidence = ref.get("confidence", 1.0)
                    assert confidence < 0.7, (
                        f"High confidence evidence in strict mode: {ref}"
                    )

            # Assert: either NO_EVIDENCE_AVAILABLE or ASSUMPTION_MADE
            has_no_evidence = "NO_EVIDENCE_AVAILABLE" in attribution_flags
            has_assumption = "ASSUMPTION_MADE" in attribution_flags
            assert has_no_evidence or has_assumption, (
                f"Expected NO_EVIDENCE_AVAILABLE or ASSUMPTION_MADE, got: {attribution_flags}"
            )

            # Assert: Trace exists and has verify phase
            assert "X-Denis-Trace-Id" in response.headers
            trace_id = response.headers["X-Denis-Trace-Id"]

            # Wait for trace
            time.sleep(0.1)

            traces = []
            if trace_file.exists():
                with open(trace_file, "r") as f:
                    for line in f:
                        if line.strip():
                            traces.append(json.loads(line))

            our_trace = None
            for trace in traces:
                if trace.get("trace_id") == trace_id:
                    our_trace = trace
                    break

            assert our_trace is not None, f"Trace {trace_id} not found"

            # Check for verify phase
            phases = our_trace.get("phases", [])
            verify_phases = [p for p in phases if p.get("name") == "verify"]
            assert len(verify_phases) > 0, (
                f"Expected verify phase, got phases: {[p.get('name') for p in phases]}"
            )

            print(f"✅ E2E-2 PASSED: Strict mode safety validated")
            print(f"   - Trace ID: {trace_id}")
            print(f"   - Attribution flags: {attribution_flags}")
            print(f"   - Disclaimers: {len(disclaimers)}")
            print(f"   - Evidence refs: {len(evidence_refs)}")
            print(f"   - Verify phases: {len(verify_phases)}")

        finally:
            # Restore original sink
            dt._trace_sink = original_sink


@pytest.mark.skipif(not HAS_DEPS, reason="DENIS dependencies not available")
class TestE2ESprintManagerIntegration:
    """E2E-3: Sprint Manager integration with Denis and planning."""

    @pytest.mark.asyncio
    async def test_sprint_manager_integration(self, tmp_path):
        """Test Sprint Manager → Denis → Plan integration."""
        from denis_unified_v1.sprint_orchestrator import (
            get_sprint_manager,
            SprintRequest,
        )

        # Create a temp project for testing
        project_path = tmp_path / "test_project"
        project_path.mkdir()

        # Create git repo
        import subprocess

        subprocess.run(
            ["git", "init"], cwd=project_path, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=project_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=project_path,
            check=True,
            capture_output=True,
        )

        # Add a Python file
        test_file = project_path / "main.py"
        test_file.write_text("""
def hello_world():
    '''A simple hello world function'''
    return "Hello, World!"

if __name__ == "__main__":
    print(hello_world())
""")

        # Commit
        subprocess.run(
            ["git", "add", "."], cwd=project_path, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=project_path,
            check=True,
            capture_output=True,
        )

        # Get sprint manager
        sprint_mgr = get_sprint_manager()

        # Create sprint request
        request = SprintRequest(
            prompt="Implement a simple calculator class",
            project_paths=[str(project_path)],
            worker_count=2,
        )

        # Create sprint
        result = await sprint_mgr.create_sprint(request)

        assert result.status == "created"
        assert result.session_id
        assert len(result.assignments) == 2  # 2 workers
        assert result.level_analysis["summary"]["total_files"] > 0

        # Validate assignments have required structure
        for assignment in result.assignments:
            assert "worker_id" in assignment
            assert "level" in assignment
            assert "crew" in assignment
            assert "capabilities" in assignment
            assert "task_focus" in assignment
            assert "validation_requirements" in assignment

        print(f"✅ E2E-3 PASSED: Sprint Manager integration validated")
        print(f"   - Session ID: {result.session_id}")
        print(f"   - Assignments: {len(result.assignments)}")
        print(f"   - Files analyzed: {result.level_analysis['summary']['total_files']}")
        print(f"   - Health score: {result.health_score}/100")

        # Clean up
        await sprint_mgr.cleanup_sprint(result.session_id)
