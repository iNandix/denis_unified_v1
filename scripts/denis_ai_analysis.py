#!/usr/bin/env python3
"""
DENIS AI Analysis Module.
Analyzes smoke failures and suggests fixes using AI.
Lazy-loaded - never executes at import time.
"""

import json
import os
import re
import requests
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


# Lazy loading - only when explicitly called
_loaded = False
_env_loaded = False


def _load_env():
    """Load .env variables lazily."""
    global _env_loaded
    if _env_loaded:
        return
    _env_loaded = True

    env_path = Path(".env")
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    if key and value and os.environ.get(key) is None:
                        os.environ[key] = value


# Valid models by provider
VALID_MODELS = {
    "openai": ["gpt-4.1", "gpt-4o", "gpt-4o-mini", "gpt-4.1-mini", "gpt-4-turbo"],
    "perplexity": [
        "sonar-small",
        "sonar-medium",
        "sonar-large",
        "sonar-small-online",
        "sonar-medium-online",
    ],
}


def validate_provider_model(provider: str, model: str) -> tuple[bool, str]:
    """Validate if model exists for provider."""
    if provider not in VALID_MODELS:
        return False, f"Unknown provider: {provider}"

    if model not in VALID_MODELS[provider]:
        return (
            False,
            f"Invalid model '{model}' for {provider}. Valid: {VALID_MODELS[provider]}",
        )

    return True, "valid"


def get_api_key(provider: str) -> Optional[str]:
    """Get API key for provider."""
    _load_env()

    if provider == "openai":
        return os.getenv("OPENAI_API_KEY") or os.getenv("AI_OPENAI_KEY")
    elif provider == "perplexity":
        return os.getenv("PERPLEXITY_API_KEY") or os.getenv("AI_PERPLEXITY_KEY")

    return None


def call_openai(api_key: str, model: str, query: str) -> Optional[dict]:
    """Call OpenAI API."""
    url = "https://api.openai.com/v1/chat/completions"

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": """You are DENIS AI Assistant. Analyze smoke test failures and provide precise fixes.
Respond ONLY with valid JSON containing:
{
  "root_cause": "precise description",
  "fix_suggestions": ["step 1", "step 2"],
  "files_to_check": ["file1.py", "file2.py"],
  "confidence": 0.0-1.0
}""",
            },
            {"role": "user", "content": query},
        ],
        "temperature": 0.2,
    }

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)

        if response.status_code == 200:
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            return {"content": content, "provider": "openai", "model": model}

        elif response.status_code == 401:
            return {"error": "invalid_api_key", "detail": "401 Unauthorized"}

        elif response.status_code == 429:
            return {"error": "rate_limit", "detail": "429 Rate limit"}

        elif response.status_code == 400:
            try:
                err = response.json()
                return {
                    "error": "bad_request",
                    "detail": err.get("error", {}).get("message", "400"),
                }
            except:
                return {"error": "bad_request", "detail": response.text[:100]}

        else:
            return {
                "error": f"http_{response.status_code}",
                "detail": response.text[:200],
            }

    except Exception as e:
        return {"error": "exception", "detail": str(e)}


def call_perplexity(api_key: str, model: str, query: str) -> Optional[dict]:
    """Call Perplexity API."""
    url = "https://api.perplexity.ai/chat/completions"

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": """You are DENIS AI Assistant. Analyze smoke test failures and provide precise fixes.
Respond ONLY with valid JSON containing:
{
  "root_cause": "precise description",
  "fix_suggestions": ["step 1", "step 2"],
  "files_to_check": ["file1.py", "file2.py"],
  "confidence": 0.0-1.0
}""",
            },
            {"role": "user", "content": query},
        ],
    }

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)

        if response.status_code == 200:
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            return {"content": content, "provider": "perplexity", "model": model}

        elif response.status_code == 400:
            try:
                err = response.json()
                msg = err.get("error", {}).get("message", "")
                if "invalid_model" in msg.lower():
                    return {"error": "invalid_model", "detail": msg}
                return {"error": "bad_request", "detail": msg}
            except:
                return {"error": "bad_request", "detail": response.text[:100]}

        elif response.status_code == 401:
            return {"error": "invalid_api_key", "detail": "401 Unauthorized"}

        elif response.status_code == 429:
            return {"error": "rate_limit", "detail": "429 Rate limit"}

        else:
            return {
                "error": f"http_{response.status_code}",
                "detail": response.text[:200],
            }

    except Exception as e:
        return {"error": "exception", "detail": str(e)}


def call_ai(query: str, provider: str = None, model: str = None) -> dict:
    """
    Main entry point for AI analysis.
    Handles fallback between providers automatically.
    """
    _load_env()

    # Get config
    if provider is None:
        provider = os.getenv("AI_ANALYSIS_PROVIDER", "openai")

    if model is None:
        model = os.getenv("AI_OPENAI_MODEL", "gpt-4o-mini")
        if provider == "perplexity":
            model = os.getenv("AI_PERPLEXITY_MODEL", "sonar-small")

    # Try primary provider first
    result = _try_provider(provider, model, query)

    if result.get("error") in ["invalid_model", "rate_limit", "http_429"]:
        # Try fallback provider
        fallback = "perplexity" if provider == "openai" else "openai"
        fallback_model = (
            os.getenv("AI_OPENAI_MODEL", "gpt-4o-mini")
            if fallback == "openai"
            else os.getenv("AI_PERPLEXITY_MODEL", "sonar-small")
        )

        result = _try_provider(fallback, fallback_model, query)

        if not result.get("error"):
            result["fallback_from"] = provider

    return result


def _try_provider(provider: str, model: str, query: str) -> dict:
    """Try a specific provider."""
    api_key = get_api_key(provider)

    if not api_key:
        return {"error": "no_api_key", "provider": provider}

    # Validate model
    valid, msg = validate_provider_model(provider, model)
    if not valid:
        return {"error": "invalid_model", "detail": msg, "provider": provider}

    if provider == "openai":
        return call_openai(api_key, model, query)
    elif provider == "perplexity":
        return call_perplexity(api_key, model, query)

    return {"error": "unknown_provider", "provider": provider}


def parse_ai_response(response: dict) -> dict:
    """Parse AI response into structured format."""
    if response.get("error"):
        return {
            "success": False,
            "error": response["error"],
            "detail": response.get("detail", ""),
            "root_cause": "AI analysis unavailable",
            "fix_suggestions": ["Check API keys and configuration"],
            "files_to_check": [],
            "confidence": 0.0,
            "provider": response.get("provider", "unknown"),
        }

    content = response.get("content", "")

    # Try to extract JSON
    try:
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
            return {
                "success": True,
                "root_cause": parsed.get("root_cause", "unknown"),
                "fix_suggestions": parsed.get("fix_suggestions", []),
                "files_to_check": parsed.get("files_to_check", []),
                "confidence": parsed.get("confidence", 0.5),
                "provider": response.get("provider", "unknown"),
                "model": response.get("model", "unknown"),
                "raw": content[:500],
            }
    except json.JSONDecodeError:
        pass

    # Fallback if no JSON found
    return {
        "success": True,
        "root_cause": "Could not parse AI response",
        "fix_suggestions": ["Manual analysis required"],
        "files_to_check": [],
        "confidence": 0.0,
        "provider": response.get("provider", "unknown"),
        "raw": content[:500],
    }


def build_prompt(
    failure: dict, smoke_data: dict = None, controlplane: dict = None
) -> str:
    """Build analysis prompt from failure context."""

    prompt = f"""Analyze this DENIS smoke test failure:

FAILURE:
- Name: {failure.get("name", "unknown")}
- Status: {failure.get("status", "unknown")}
- Reason: {failure.get("reason", "none")}
- Exit Code: {failure.get("exit_code", "N/A")}
- Duration: {failure.get("duration_ms", "N/A")}ms

"""

    if smoke_data:
        prompt += f"SMOKE ARTIFACT:\n{json.dumps(smoke_data, indent=2)[:2000]}\n\n"

    if controlplane:
        prompt += (
            f"CONTROL PLANE STATUS:\n{json.dumps(controlplane, indent=2)[:1000]}\n\n"
        )

    prompt += """Provide a JSON response with:
{
  "root_cause": "precise description of what's wrong",
  "fix_suggestions": ["step 1", "step 2"],
  "files_to_check": ["file1.py"],
  "confidence": 0.0-1.0
}"""

    return prompt


def analyze_failure(
    failure: dict, smoke_data: dict = None, controlplane: dict = None
) -> dict:
    """
    Main function to analyze a smoke failure.
    Returns structured analysis with root cause and fix suggestions.
    """
    prompt = build_prompt(failure, smoke_data, controlplane)

    # Call AI
    response = call_ai(prompt)

    # Parse response
    return parse_ai_response(response)


# Test function
def main():
    import argparse

    parser = argparse.ArgumentParser(description="DENIS AI Analysis")
    parser.add_argument("--failure", type=str, help="Failure JSON")
    parser.add_argument("--smoke", type=str, help="Smoke artifact file")
    parser.add_argument(
        "--provider", type=str, default=None, help="Provider (openai/perplexity)"
    )
    parser.add_argument("--model", type=str, default=None, help="Model name")
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

    smoke_data = {}
    if args.smoke:
        try:
            with open(args.smoke) as f:
                smoke_data = json.load(f)
        except:
            pass

    result = analyze_failure(failure, smoke_data, {})
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
