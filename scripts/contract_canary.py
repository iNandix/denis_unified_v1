#!/usr/bin/env python3
"""Runtime canary for OpenAI contract validation against deployed service."""

import asyncio
import json
import os
import sys
import time
from typing import Dict, Any, Optional
import httpx
from enum import Enum
from typing import List, Dict, Any, Optional


class FailureLevel(Enum):
    """Severity levels for canary failures."""
    HARD_FAIL = "hard_fail"  # Triggers rollback
    WARN = "warn"           # Alerts but allows deployment
    INFO = "info"          # Logged but not actioned


class CanaryFailure:
    """Structured failure with severity level."""
    def __init__(self, test_name: str, error: str, level: FailureLevel, details: Optional[Dict] = None):
        self.test_name = test_name
        self.error = error
        self.level = level
        self.details = details or {}
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test": self.test_name,
            "error": self.error,
            "level": self.level.value,
            "details": self.details,
            "timestamp": self.timestamp
        }


class ContractCanary:
    """Validates OpenAI contracts against deployed service."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=30.0)
        self.failures: List[CanaryFailure] = []

    def record_failure(self, test_name: str, error: str, level: FailureLevel = FailureLevel.HARD_FAIL, details: Optional[Dict] = None):
        """Record a failure with severity level."""
        self.failures.append(CanaryFailure(test_name, error, level, details))

    def has_hard_failures(self) -> bool:
        """Check if any hard failures occurred."""
        return any(f.level == FailureLevel.HARD_FAIL for f in self.failures)

    def has_warnings(self) -> bool:
        """Check if any warnings occurred."""
        return any(f.level in [FailureLevel.WARN, FailureLevel.INFO] for f in self.failures)

    async def test_openai_contract_shape(self) -> bool:
        """Test OpenAI response shape and invariants."""
        try:
            response = await self.client.post(
                f"{self.base_url}/v1/chat/completions",
                json={
                    "model": "denis-cognitive",
                    "messages": [{"role": "user", "content": "Canary test: Hello world"}],
                    "max_tokens": 100
                },
                headers={"Content-Type": "application/json"}
            )

            if response.status_code != 200:
                self.record_failure("openai_contract_shape", f"HTTP {response.status_code}", {
                    "response_text": response.text[:500]
                })
                return False

            data = response.json()

            # Validate top-level structure
            required_fields = ["id", "object", "created", "model", "choices", "usage"]
            for field in required_fields:
                if field not in data:
                    self.record_failure("openai_contract_shape", f"Missing field: {field}")
                    return False

            # Validate object type
            if data.get("object") != "chat.completion":
                self.record_failure("openai_contract_shape", f"Wrong object type: {data.get('object')}")
                return False

            # Validate choices structure
            choices = data.get("choices", [])
            if not choices or not isinstance(choices, list):
                self.record_failure("openai_contract_shape", "Invalid choices structure")
                return False

            choice = choices[0]
            if not isinstance(choice, dict):
                self.record_failure("openai_contract_shape", "Choice is not a dict")
                return False

            # Validate message structure
            message = choice.get("message", {})
            if not isinstance(message, dict):
                self.record_failure("openai_contract_shape", "Message is not a dict")
                return False

            required_msg_fields = ["role", "content"]
            for field in required_msg_fields:
                if field not in message:
                    self.record_failure("openai_contract_shape", f"Missing message field: {field}")
                    return False

            if message.get("role") != "assistant":
                self.record_failure("openai_contract_shape", f"Wrong role: {message.get('role')}")
                return False

            # Validate usage structure
            usage = data.get("usage", {})
            if not isinstance(usage, dict):
                self.record_failure("openai_contract_shape", "Usage is not a dict")
                return False

            required_usage_fields = ["prompt_tokens", "completion_tokens", "total_tokens"]
            for field in required_usage_fields:
                if field not in usage or not isinstance(usage[field], int) or usage[field] < 0:
                    self.record_failure("openai_contract_shape", f"Invalid usage field: {field}")
                    return False

            # Validate token arithmetic
            expected_total = usage["prompt_tokens"] + usage["completion_tokens"]
            if usage["total_tokens"] != expected_total:
                self.record_failure("openai_contract_shape", f"Token arithmetic error: {usage}")
                return False

            return True

        except Exception as e:
            self.record_failure("openai_contract_shape", f"Exception: {str(e)}", FailureLevel.HARD_FAIL)
            return False

    async def test_strict_verify_semantics(self) -> bool:
        """Test strict verify safety semantics."""
        try:
            # This test requires internal access to KernelResponse
            # For external canary, we'd need a debug endpoint or extension field
            response = await self.client.post(
                f"{self.base_url}/v1/chat/completions",
                json={
                    "model": "denis-cognitive",
                    "messages": [{"role": "user", "content": "Test safety mode"}],
                    "max_tokens": 100
                },
                headers={
                    "Content-Type": "application/json",
                    "X-Denis-Safety-Mode": "strict"  # If supported
                }
            )

            if response.status_code != 200:
                self.record_failure("strict_verify_semantics", f"HTTP {response.status_code}", FailureLevel.HARD_FAIL)
                return False

            data = response.json()

            # Check for extensions field with safety info (if implemented)
            extensions = data.get("extensions", {})
            if not isinstance(extensions, dict):
                self.record_failure("strict_verify_semantics", "Extensions field missing or invalid", FailureLevel.WARN)
                return False

            # Validate safety flags if present
            safety_flags = extensions.get("attribution_flags", [])
            if "SAFETY_MODE_STRICT_APPLIED" not in safety_flags:
                self.record_failure("strict_verify_semantics", "Missing SAFETY_MODE_STRICT_APPLIED flag", FailureLevel.HARD_FAIL)
                return False

            return True

        except Exception as e:
            self.record_failure("strict_verify_semantics", f"Exception: {str(e)}", FailureLevel.WARN)
            return False

    async def test_evidence_availability_slo(self) -> bool:
        """Test evidence availability SLO (only for tool-required prompts)."""
        try:
            # Test with tool-required prompt that should generate evidence
            tool_response = await self.client.post(
                f"{self.base_url}/v1/chat/completions",
                json={
                    "model": "denis-cognitive",
                    "messages": [{"role": "user", "content": "Please use a tool to help me"}],
                    "tools": [{"type": "function", "function": {"name": "test_tool", "parameters": {}}}],
                    "max_tokens": 100
                }
            )

            if tool_response.status_code != 200:
                self.record_failure("evidence_availability_slo", f"Tool request failed: HTTP {tool_response.status_code}", FailureLevel.WARN)
                return False

            tool_data = tool_response.json()
            extensions = tool_data.get("extensions", {})

            # Check if evidence was generated for tool request
            evidence_refs = extensions.get("evidence_refs", [])
            if len(evidence_refs) == 0:
                self.record_failure("evidence_availability_slo", "No evidence generated for tool-required prompt", FailureLevel.WARN)
                return False

            return True

        except Exception as e:
            self.record_failure("evidence_availability_slo", f"Exception: {str(e)}", FailureLevel.INFO)
            return False

    async def test_budget_drift_slo(self) -> bool:
        """Test budget drift SLO (warn on ratio, hard fail on absolute)."""
        try:
            # Run a few requests to establish baseline
            budget_tests = []
            for i in range(3):
                response = await self.client.post(
                    f"{self.base_url}/v1/chat/completions",
                    json={
                        "model": "denis-cognitive",
                        "messages": [{"role": "user", "content": f"Budget test {i}: This is a test message"}],
                        "max_tokens": 50
                    }
                )

                if response.status_code != 200:
                    self.record_failure("budget_drift_slo", f"Request {i} failed: HTTP {response.status_code}", FailureLevel.WARN)
                    continue

                data = response.json()
                extensions = data.get("extensions", {})

                # Extract budget info if available
                budget_info = extensions.get("budget", {})
                actual = budget_info.get("actual_total", 0)
                planned = budget_info.get("planned_total", 1)  # Avoid division by zero

                budget_tests.append({
                    "actual": actual,
                    "planned": planned,
                    "delta": actual - planned,
                    "ratio": actual / planned if planned > 0 else float('inf')
                })

            if not budget_tests:
                self.record_failure("budget_drift_slo", "No successful budget tests", FailureLevel.INFO)
                return False

            # Check absolute drift (hard fail)
            max_absolute_drift = max(abs(test["delta"]) for test in budget_tests)
            if max_absolute_drift > 1000:  # Configurable threshold
                self.record_failure("budget_drift_slo", f"Excessive absolute budget drift: {max_absolute_drift}", FailureLevel.HARD_FAIL)
                return False

            # Check ratio drift (warn only)
            max_ratio_drift = max(test["ratio"] for test in budget_tests)
            if max_ratio_drift > 2.0:  # 200% of planned
                self.record_failure("budget_drift_slo", f"High budget ratio drift: {max_ratio_drift:.2f}", FailureLevel.WARN)

            return True

        except Exception as e:
            self.record_failure("budget_drift_slo", f"Exception: {str(e)}", FailureLevel.INFO)
            return False

    async def test_latency_slo(self, max_p95_ms: int = 5000) -> bool:
        """Test latency SLO compliance."""
        latencies = []

        # Run multiple requests to establish p95
        for i in range(5):
            start_time = time.perf_counter()
            try:
                response = await self.client.post(
                    f"{self.base_url}/v1/chat/completions",
                    json={
                        "model": "denis-cognitive",
                        "messages": [{"role": "user", "content": f"Canary latency test {i}"}],
                        "max_tokens": 50
                    }
                )
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                latencies.append(latency_ms)

                if response.status_code != 200:
                    self.record_failure("latency_slo", f"Request {i} failed: HTTP {response.status_code}")
                    return False

            except Exception as e:
                self.record_failure("latency_slo", f"Request {i} exception: {str(e)}")
                return False

        # Calculate p95 (simple approximation)
        latencies.sort()
        p95_index = int(len(latencies) * 0.95)
        p95_latency = latencies[min(p95_index, len(latencies) - 1)]

        if p95_latency > max_p95_ms:
            self.record_failure("latency_slo", f"P95 latency {p95_latency}ms exceeds {max_p95_ms}ms SLO", {
                "latencies": latencies,
                "p95": p95_latency
            })
            return False

        return True

    async def run_canary(self) -> bool:
        """Run all canary tests."""
        print(f"🩺 Running contract canary against {self.base_url}")

        tests = [
            ("OpenAI Contract Shape", self.test_openai_contract_shape, FailureLevel.HARD_FAIL),
            ("Strict Verify Semantics", self.test_strict_verify_semantics, FailureLevel.HARD_FAIL),
            ("Evidence Availability SLO", self.test_evidence_availability_slo, FailureLevel.WARN),
            ("Budget Drift SLO", self.test_budget_drift_slo, FailureLevel.WARN),
            ("Latency SLO (5s p95)", lambda: self.test_latency_slo(5000), FailureLevel.HARD_FAIL),
        ]

        all_passed = True
        for test_name, test_func, expected_level in tests:
            print(f"  Testing: {test_name}...", end=" ")
            try:
                passed = await test_func()
                if passed:
                    print("✅ PASS")
                else:
                    print(f"❌ {expected_level.value.upper()}")
                    if expected_level == FailureLevel.HARD_FAIL:
                        all_passed = False
                    # Warnings don't fail the overall test
            except Exception as e:
                print(f"❌ ERROR: {str(e)}")
                self.record_failure(test_name, f"Test execution error: {str(e)}", FailureLevel.HARD_FAIL)
                all_passed = False

        return all_passed

    def get_report(self) -> Dict[str, Any]:
        """Get canary execution report."""
        hard_failures = [f for f in self.failures if f.level == FailureLevel.HARD_FAIL]
        warnings = [f for f in self.failures if f.level in [FailureLevel.WARN, FailureLevel.INFO]]
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service_url": self.base_url,
            "tests_run": 5,  # Updated count
            "hard_failures": [f.to_dict() for f in hard_failures],
            "warnings": [f.to_dict() for f in warnings],
            "overall_status": "FAIL" if hard_failures else "PASS",
            "has_warnings": len(warnings) > 0
        }


async def main():
    """Run canary from command line."""
    base_url = os.getenv("CANARY_TARGET_URL", "http://localhost:8000")

    async with ContractCanary(base_url) as canary:
        success = await canary.run_canary()
        report = canary.get_report()

        # Print report
        print(f"\n📊 Canary Report: {report['overall_status']}")
        print(f"Service: {report['service_url']}")
        print(f"Timestamp: {report['timestamp']}")

        if report['failures']:
            print("\n❌ Failures:")
            for failure in report['failures']:
                print(f"  • {failure['test']}: {failure['error']}")
                if failure.get('details'):
                    print(f"    Details: {json.dumps(failure['details'], indent=4)}")

        # Exit with appropriate code
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
