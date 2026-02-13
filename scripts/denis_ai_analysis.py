#!/usr/bin/env python3
"""
AI Analysis Module for DENIS.
Uses Perplexity or OpenAI API to analyze smoke failures and suggest fixes.
"""

import json
import os
import requests
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


DEFAULT_TIMEOUT = 30


# Load .env variables
def load_env():
    """Load environment variables from .env file."""
    env_path = Path(".env")
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    if key and value and os.environ.get(key) is None:
                        os.environ[key] = value


load_env()


def load_json(path: Path, default=None):
    if default is None:
        default = {}
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return default


def call_perplexity(api_key: str, query: str) -> Optional[str]:
    """Call Perplexity API for analysis."""
    url = "https://api.perplexity.ai/chat/completions"

    payload = {
        "model": "llama-3.1-sonar-small-128k",
        "messages": [
            {
                "role": "system",
                "content": "You are DENIS AI Assistant. You analyze smoke test failures and provide precise fixes. Always respond with valid JSON containing: root_cause, fix_suggestions (array), files_to_check (array), and confidence (0-1).",
            },
            {"role": "user", "content": query},
        ],
    }

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        response = requests.post(
            url, json=payload, headers=headers, timeout=DEFAULT_TIMEOUT
        )
        if response.status_code == 200:
            result = response.json()
            return result["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"Perplexity API error: {e}")

    return None


def call_openai(api_key: str, query: str) -> Optional[str]:
    """Call OpenAI API for analysis."""
    url = "https://api.openai.com/v1/chat/completions"

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "system",
                "content": "You are DENIS AI Assistant. You analyze smoke test failures and provide precise fixes. Always respond with valid JSON containing: root_cause, fix_suggestions (array), files_to_check (array), and confidence (0-1).",
            },
            {"role": "user", "content": query},
        ],
        "temperature": 0.2,
    }

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        response = requests.post(
            url, json=payload, headers=headers, timeout=DEFAULT_TIMEOUT
        )
        if response.status_code == 200:
            result = response.json()
            return result["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"OpenAI API error: {e}")

    return None


def build_analysis_prompt(
    failure: dict, smoke_output: str, controlplane_status: dict
) -> str:
    """Build the prompt for AI analysis."""

    prompt = f"""Analyze this DENIS smoke test failure and provide a fix.

FAILURE DETAILS:
- Smoke Name: {failure.get("name", "unknown")}
- Status: {failure.get("status", "unknown")}
- Reason: {failure.get("reason", "none")}
- Exit Code: {failure.get("exit_code", "N/A")}
- Duration: {failure.get("duration_ms", "N/A")}ms

"""

    if smoke_output:
        prompt += f"SMOKE OUTPUT:\n{smoke_output[:3000]}\n\n"

    if controlplane_status:
        prompt += f"CONTROL PLANE STATUS:\n{json.dumps(controlplane_status, indent=2)[:2000]}\n\n"

    prompt += """Provide a JSON response with:
{
  "root_cause": "precise description of what's wrong",
  "fix_suggestions": ["step 1", "step 2", "step 3"],
  "files_to_check": ["file1.py", "file2.py"],
  "confidence": 0.0-1.0
}

Respond ONLY with valid JSON, no markdown."""

    return prompt


def analyze_failure(
    failure: dict, smoke_output: str = "", controlplane_status: dict = None
) -> dict:
    """Analyze a failure using AI."""

    api_key = os.getenv("PERPLEXITY_API_KEY") or os.getenv("OPENAI_API_KEY")
    provider = os.getenv("AI_ANALYSIS_PROVIDER", "perplexity")

    if not api_key:
        return {
            "success": False,
            "error": "No API key found (PERPLEXITY_API_KEY or OPENAI_API_KEY)",
            "root_cause": "API key not configured",
            "fix_suggestions": ["Configure AI_ANALYSIS_PROVIDER in .env"],
            "files_to_check": [],
            "confidence": 0.0,
        }

    prompt = build_analysis_prompt(failure, smoke_output, controlplane_status or {})

    if provider == "openai":
        response = call_openai(api_key, prompt)
    else:
        response = call_perplexity(api_key, prompt)

    if not response:
        return {
            "success": False,
            "error": "API call failed",
            "root_cause": "Could not get AI response",
            "fix_suggestions": ["Check API key and try again"],
            "files_to_check": [],
            "confidence": 0.0,
        }

    # Try to parse JSON from response
    try:
        # Extract JSON from response
        import re

        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            analysis = json.loads(json_match.group())
            analysis["success"] = True
            analysis["raw_response"] = response[:500]
            return analysis
    except json.JSONDecodeError:
        pass

    return {
        "success": True,
        "raw_response": response[:500],
        "root_cause": "Could not parse AI response",
        "fix_suggestions": ["Manual analysis required"],
        "files_to_check": [],
        "confidence": 0.0,
    }


def main():
    """Test the AI analysis."""
    import argparse

    parser = argparse.ArgumentParser(description="DENIS AI Analysis")
    parser.add_argument("--failure", type=str, help="Failure JSON")
    parser.add_argument("--smoke", type=str, help="Smoke output file")
    args = parser.parse_args()

    failure = (
        json.loads(args.failure)
        if args.failure
        else {
            "name": "test_smoke",
            "status": "failed",
            "reason": "Test failure",
            "exit_code": 1,
        }
    )

    smoke_output = ""
    if args.smoke:
        try:
            smoke_output = Path(args.smoke).read_text()[:3000]
        except:
            pass

    result = analyze_failure(failure, smoke_output, {})
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
