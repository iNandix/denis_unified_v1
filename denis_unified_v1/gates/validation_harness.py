"""
Validation Harness E2E - Suite determinista para gates y ops.

Provides:
- Deterministic test suite
- JSON report generation
- Baseline comparison
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from enum import Enum

from denis_unified_v1.gates.rate_limiter import (
    RateLimiterManager,
    RateLimitScope,
    get_rate_limiter_manager,
)
from denis_unified_v1.gates.budget import (
    BudgetEnforcer,
    BudgetConfig,
    get_budget_enforcer,
)
from denis_unified_v1.gates.audit import (
    AuditTrail,
    AuditEventType,
    AuditSeverity,
    get_audit_trail,
)
from denis_unified_v1.ops.config_store import (
    ConfigStore,
    ConfigStatus,
    ApprovalLevel,
    get_config_store,
)


class TestStatus(Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class TestResult:
    """Result of a single test."""

    test_name: str
    status: TestStatus
    duration_ms: float
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class TestSuite:
    """A test suite with results."""

    suite_name: str
    started_at: float
    completed_at: Optional[float] = None
    results: List[TestResult] = field(default_factory=list)
    baseline: Optional[Dict[str, Any]] = None

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.status == TestStatus.PASSED)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status == TestStatus.FAILED)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def success_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return self.passed / self.total

    def to_dict(self) -> Dict[str, Any]:
        return {
            "suite_name": self.suite_name,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "passed": self.passed,
            "failed": self.failed,
            "total": self.total,
            "success_rate": self.success_rate,
            "results": [
                {
                    "test_name": r.test_name,
                    "status": r.status.value,
                    "duration_ms": r.duration_ms,
                    "details": r.details,
                    "error": r.error,
                }
                for r in self.results
            ],
        }


class ValidationHarness:
    """
    E2E validation harness for gates and ops.
    Runs deterministic tests and generates JSON reports.
    """

    def __init__(self):
        self.rate_limiter = get_rate_limiter_manager()
        self.budget_enforcer = get_budget_enforcer()
        self.audit = get_audit_trail()
        self.config_store = get_config_store()

    async def run_gate_tests(self) -> TestSuite:
        """Run all gate-related tests."""
        suite = TestSuite(suite_name="gate_hardening", started_at=time.time())

        # Test 1: Rate limiter allows within limit
        await self._test_rate_limit_allowed(suite)

        # Test 2: Rate limiter blocks over limit
        await self._test_rate_limit_blocked(suite)

        # Test 3: Budget enforcement
        await self._test_budget_enforcement(suite)

        # Test 4: Budget TTFT
        await self._test_budget_ttft(suite)

        # Test 5: Audit trail logging
        await self._test_audit_logging(suite)

        # Test 6: Config guardrails
        await self._test_config_guardrails(suite)

        # Test 7: Config proposal workflow
        await self._test_proposal_workflow(suite)

        suite.completed_at = time.time()
        return suite

    async def _test_rate_limit_allowed(self, suite: TestSuite) -> None:
        test_name = "rate_limit_allowed_within_limit"
        start = time.time()

        try:
            limiter = self.rate_limiter.get_limiter(RateLimitScope.USER)
            result = await limiter.check_rate_limit("test_user", RateLimitScope.USER)

            duration_ms = (time.time() - start) * 1000

            suite.results.append(
                TestResult(
                    test_name=test_name,
                    status=TestStatus.PASSED if result.allowed else TestStatus.FAILED,
                    duration_ms=duration_ms,
                    details={
                        "allowed": result.allowed,
                        "remaining": result.remaining,
                        "scope": result.scope,
                    },
                )
            )
        except Exception as e:
            suite.results.append(
                TestResult(
                    test_name=test_name,
                    status=TestStatus.ERROR,
                    duration_ms=(time.time() - start) * 1000,
                    error=str(e),
                )
            )

    async def _test_rate_limit_blocked(self, suite: TestSuite) -> None:
        test_name = "rate_limit_blocks_over_limit"
        start = time.time()

        try:
            # Configure very restrictive limits
            self.rate_limiter.configure_scope(RateLimitScope.USER, rps=0.1, burst=1)

            limiter = self.rate_limiter.get_limiter(RateLimitScope.USER)

            # First should succeed
            r1 = await limiter.check_rate_limit("burst_test_user", RateLimitScope.USER)

            # Immediate second should fail
            r2 = await limiter.check_rate_limit("burst_test_user", RateLimitScope.USER)

            duration_ms = (time.time() - start) * 1000

            # Reset for future tests
            self.rate_limiter.configure_scope(RateLimitScope.USER, rps=10.0, burst=20)

            suite.results.append(
                TestResult(
                    test_name=test_name,
                    status=TestStatus.PASSED
                    if (r1.allowed and not r2.allowed)
                    else TestStatus.FAILED,
                    duration_ms=duration_ms,
                    details={
                        "first_allowed": r1.allowed,
                        "second_allowed": r2.allowed,
                    },
                )
            )
        except Exception as e:
            self.rate_limiter.configure_scope(RateLimitScope.USER, rps=10.0, burst=20)
            suite.results.append(
                TestResult(
                    test_name=test_name,
                    status=TestStatus.ERROR,
                    duration_ms=(time.time() - start) * 1000,
                    error=str(e),
                )
            )

    async def _test_budget_enforcement(self, suite: TestSuite) -> None:
        test_name = "budget_enforcement_total"
        start = time.time()

        try:
            config = BudgetConfig(
                total_budget_ms=100.0,  # Very short for test
                enable_cancellation=True,
            )
            enforcer = BudgetEnforcer(config)

            request_id = await enforcer.start_request(class_key="test")

            # Simulate work
            await asyncio.sleep(0.2)  # Exceed budget

            result = await enforcer.check_total(request_id)

            await enforcer.end_request(request_id)

            duration_ms = (time.time() - start) * 1000

            suite.results.append(
                TestResult(
                    test_name=test_name,
                    status=TestStatus.PASSED if result.exceeded else TestStatus.FAILED,
                    duration_ms=duration_ms,
                    details={
                        "exceeded": result.exceeded,
                        "elapsed_ms": result.elapsed_ms,
                        "limit_ms": result.limit_ms,
                    },
                )
            )
        except Exception as e:
            suite.results.append(
                TestResult(
                    test_name=test_name,
                    status=TestStatus.ERROR,
                    duration_ms=(time.time() - start) * 1000,
                    error=str(e),
                )
            )

    async def _test_budget_ttft(self, suite: TestSuite) -> None:
        test_name = "budget_enforcement_ttft"
        start = time.time()

        try:
            config = BudgetConfig(
                ttft_budget_ms=50.0,  # Very short for test
                enable_cancellation=True,
            )
            enforcer = BudgetEnforcer(config)

            request_id = await enforcer.start_request(class_key="test")

            # Simulate slow first token
            await asyncio.sleep(0.1)

            result = await enforcer.check_ttft(request_id)

            await enforcer.end_request(request_id)

            duration_ms = (time.time() - start) * 1000

            suite.results.append(
                TestResult(
                    test_name=test_name,
                    status=TestStatus.PASSED if result.exceeded else TestStatus.FAILED,
                    duration_ms=duration_ms,
                    details={
                        "exceeded": result.exceeded,
                        "elapsed_ms": result.elapsed_ms,
                    },
                )
            )
        except Exception as e:
            suite.results.append(
                TestResult(
                    test_name=test_name,
                    status=TestStatus.ERROR,
                    duration_ms=(time.time() - start) * 1000,
                    error=str(e),
                )
            )

    async def _test_audit_logging(self, suite: TestSuite) -> None:
        test_name = "audit_trail_logging"
        start = time.time()

        try:
            event_id = await self.audit.log_event(
                event_type=AuditEventType.RATE_LIMIT,
                severity=AuditSeverity.WARNING,
                user_id="test_user",
                class_key="test",
                blocked=True,
                reason="rate_limit_exceeded",
            )

            # Query back
            events = await self.audit.query_events(user_id="test_user", limit=10)

            duration_ms = (time.time() - start) * 1000

            found = any(e.event_id == event_id for e in events)

            suite.results.append(
                TestResult(
                    test_name=test_name,
                    status=TestStatus.PASSED if found else TestStatus.FAILED,
                    duration_ms=duration_ms,
                    details={
                        "event_logged": event_id,
                        "events_found": len(events),
                    },
                )
            )
        except Exception as e:
            suite.results.append(
                TestResult(
                    test_name=test_name,
                    status=TestStatus.ERROR,
                    duration_ms=(time.time() - start) * 1000,
                    error=str(e),
                )
            )

    async def _test_config_guardrails(self, suite: TestSuite) -> None:
        test_name = "config_guardrails"
        start = time.time()

        try:
            # Test valid config
            valid, errors = self.config_store.validate_config(
                "phase10_rate_limit_rps",
                50,
            )

            # Test invalid config (out of range)
            invalid, invalid_errors = self.config_store.validate_config(
                "phase10_rate_limit_rps",
                500,  # Above max of 100
            )

            duration_ms = (time.time() - start) * 1000

            suite.results.append(
                TestResult(
                    test_name=test_name,
                    status=TestStatus.PASSED
                    if (valid and not invalid)
                    else TestStatus.FAILED,
                    duration_ms=duration_ms,
                    details={
                        "valid_passed": valid,
                        "invalid_blocked": not invalid,
                        "errors": invalid_errors,
                    },
                )
            )
        except Exception as e:
            suite.results.append(
                TestResult(
                    test_name=test_name,
                    status=TestStatus.ERROR,
                    duration_ms=(time.time() - start) * 1000,
                    error=str(e),
                )
            )

    async def _test_proposal_workflow(self, suite: TestSuite) -> None:
        test_name = "config_proposal_workflow"
        start = time.time()

        try:
            # Create proposal
            proposal_id = await self.config_store.create_proposal(
                config_key="test_config",
                new_value={"test": "value"},
                change_summary="Test proposal",
                created_by="test_user",
                required_approval_level=ApprovalLevel.AUTO,
            )

            # Approve
            approved = await self.config_store.approve_proposal(
                proposal_id,
                "admin_user",
            )

            # Apply
            version_id = await self.config_store.apply_proposal(proposal_id)

            duration_ms = (time.time() - start) * 1000

            suite.results.append(
                TestResult(
                    test_name=test_name,
                    status=TestStatus.PASSED
                    if (approved and version_id)
                    else TestStatus.FAILED,
                    duration_ms=duration_ms,
                    details={
                        "proposal_id": proposal_id,
                        "approved": approved,
                        "version_id": version_id,
                    },
                )
            )
        except Exception as e:
            suite.results.append(
                TestResult(
                    test_name=test_name,
                    status=TestStatus.ERROR,
                    duration_ms=(time.time() - start) * 1000,
                    error=str(e),
                )
            )

    async def run_all_tests(self) -> TestSuite:
        """Run all validation tests."""
        suite = await self.run_gate_tests()
        return suite

    def generate_report(
        self, suite: TestSuite, baseline: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Generate test report with baseline comparison."""
        report = suite.to_dict()

        if baseline:
            report["baseline"] = baseline
            report["diff"] = {
                "passed_diff": suite.passed - baseline.get("passed", 0),
                "failed_diff": suite.failed - baseline.get("failed", 0),
                "success_rate_diff": suite.success_rate
                - baseline.get("success_rate", 0),
            }

        return report


# Singleton
_validation_harness: Optional[ValidationHarness] = None


def get_validation_harness() -> ValidationHarness:
    """Get singleton validation harness."""
    global _validation_harness
    if _validation_harness is None:
        _validation_harness = ValidationHarness()
    return _validation_harness
