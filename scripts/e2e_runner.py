#!/usr/bin/env python3
"""
E2E Runner for Denis scenarios.
Loads YAML scenarios, executes requests against API, checks asserts, outputs JSON report.
"""

import json
import sys
from pathlib import Path

import requests
import yaml


def run_scenario(scenario):
    req = scenario["request"]
    url = f"http://127.0.0.1:8000{req['path']}"
    method = req["method"]
    body = req.get("body")

    resp = requests.request(method, url, json=body, timeout=10)

    results = []
    for assert_ in scenario["asserts"]:
        if "status_code" in assert_:
            pass_ = resp.status_code == assert_["status_code"]
            results.append({
                "assert": assert_,
                "pass": pass_,
                "expected": assert_["status_code"],
                "actual": resp.status_code
            })
        elif "headers.x-runtime-mode" in assert_:
            expected = assert_["headers.x-runtime-mode"]
            actual = resp.headers.get("x-runtime-mode")
            if expected == "not_present":
                pass_ = "x-runtime-mode" not in resp.headers
            else:
                pass_ = actual == expected
            results.append({
                "assert": assert_,
                "pass": pass_,
                "expected": expected,
                "actual": actual
            })
        elif "body.reason" in assert_:
            expected = assert_["body.reason"]
            body_json = resp.json()
            actual = body_json.get("reason")
            pass_ = actual == expected
            results.append({
                "assert": assert_,
                "pass": pass_,
                "expected": expected,
                "actual": actual
            })
        elif "body.diagnostics.degraded" in assert_:
            expected = assert_["body.diagnostics.degraded"]
            body_json = resp.json()
            actual = body_json.get("diagnostics", {}).get("degraded")
            pass_ = actual == expected
            results.append({
                "assert": assert_,
                "pass": pass_,
                "expected": expected,
                "actual": actual
            })
        elif "body.diagnostics.reason" in assert_:
            expected = assert_["body.diagnostics.reason"]
            body_json = resp.json()
            actual = body_json.get("diagnostics", {}).get("reason")
            pass_ = actual == expected
            results.append({
                "assert": assert_,
                "pass": pass_,
                "expected": expected,
                "actual": actual
            })
        # Add more asserts as needed

    return {
        "name": scenario["name"],
        "asserts": results,
        "pass": all(r["pass"] for r in results)
    }


def main():
    if len(sys.argv) != 2:
        print("Usage: python e2e_runner.py <scenarios.yaml>")
        sys.exit(1)

    scenarios_file = Path(sys.argv[1])
    if not scenarios_file.exists():
        print(f"Scenarios file not found: {scenarios_file}")
        sys.exit(1)

    with open(scenarios_file) as f:
        data = yaml.safe_load(f)

    scenarios = data.get("scenarios", [])
    results = []
    for scenario in scenarios:
        try:
            result = run_scenario(scenario)
            results.append(result)
        except Exception as e:
            results.append({
                "name": scenario["name"],
                "error": str(e),
                "pass": False
            })

    report = {
        "scenarios": results,
        "overall_pass": all(r.get("pass", False) for r in results),
        "total": len(results),
        "passed": sum(1 for r in results if r.get("pass", False))
    }

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
