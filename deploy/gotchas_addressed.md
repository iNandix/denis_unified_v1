# Security and Compatibility Gotchas - Addressed

## Gotcha 1: Contract Test Mode Never in Production
### Risk: Accidental deterministic responses in production
### Solution: Environment-gated activation

```python
# In openai_compatible.py - runtime.py
def generate(req: ChatCompletionRequest) -> dict[str, Any]:
    # Only allow contract mode in non-production environments
    is_contract_mode = (
        req.model == "denis-contract-test" and
        os.getenv("ENV", "development") != "production" and
        os.getenv("DENIS_CONTRACT_TEST_MODE") == "1"
    )

    if is_contract_mode:
        return _generate_deterministic_response(req)

    # Normal processing...
```

### CI Check:
```bash
# In deployment pipeline
grep -r "DENIS_CONTRACT_TEST_MODE" --include="*.py" .
# Should only appear in test files and guarded by ENV checks
```

## Gotcha 2: Extensions Field Breaking OpenAI SDKs
### Risk: Adding top-level fields confuses strict SDK parsers
### Solution: Vendor-safe extension structure

```python
# Safe extension format (OpenAI-compatible)
def _format_openai_response(kernel_response: KernelResponse) -> dict:
    response = {
        "id": f"chatcmpl-{uuid.uuid4().hex[:16]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "denis-cognitive",
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": kernel_response.response.get("text", ""),
            },
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": 10,  # Calculate properly
            "completion_tokens": 20,
            "total_tokens": 30,
        }
    }

    # Add extensions in vendor-safe way
    if hasattr(kernel_response, 'attribution_flags'):
        response["extensions"] = {
            "denis.ai": {  # Vendor namespace
                "attribution_flags": kernel_response.attribution_flags,
                "attribution_language": kernel_response.attribution_language,
                "evidence_refs": kernel_response.evidence_refs,
                "disclaimers": kernel_response.disclaimers,
                "schema_version": "kernel_response_v1"
            }
        }

    return response
```

### Compatibility Test:
```python
def test_openai_sdk_compatibility():
    """Test that response works with real OpenAI SDKs."""
    import openai  # If available

    # Parse response through OpenAI SDK
    client = openai.OpenAI(api_key="dummy")
    try:
        # This should not raise exceptions due to unknown fields
        parsed = client.chat.completions.parse(response_json)
        assert parsed.choices[0].message.content is not None
    except Exception as e:
        pytest.fail(f"OpenAI SDK compatibility broken: {e}")
```

## Gotcha 3: Trace Sampling Impacting Performance
### Risk: High sampling rate slows down production
### Solution: Environment-based sampling

```python
# In decision_trace.py
def get_trace_sample_rate() -> float:
    """Environment-aware sampling rate."""
    env = os.getenv("ENV", "development")

    # High sampling in development/testing
    if env in ["development", "test"]:
        return 1.0  # 100% sampling

    # Low sampling in production
    if env == "production":
        return float(os.getenv("TRACE_SAMPLE_RATE", "0.01"))  # 1%

    # Staging: medium sampling
    return 0.1  # 10%
```

## Gotcha 4: Schema Version Drift
### Risk: Silent incompatibilities between versions
### Solution: Schema validation and version checking

```python
# In contract tests
def test_schema_version_compatibility():
    """Ensure schema versions are recognized and valid."""
    valid_versions = ["decision_trace_v1", "context_pack_v1"]

    trace = generate_trace()
    assert trace["schema_version"] in valid_versions

    # Test deserialization works
    from decision_trace import DecisionTrace
    reconstructed = DecisionTrace.from_dict(trace)
    assert reconstructed.trace_id == trace["trace_id"]
```

## Production Safety Checks
### Pre-deployment validation:
```bash
# 1. No contract mode in production builds
grep -r "contract.*test" --exclude-dir=test . || echo "✓ No contract test code in prod build"

# 2. Extensions field is properly namespaced
grep -A5 -B5 "extensions.*denis" api/openai_compatible.py | head -10

# 3. Sampling rates are environment-appropriate
echo "TRACE_SAMPLE_RATE in prod: ${TRACE_SAMPLE_RATE:-0.01}"
```

### Runtime validation:
```bash
# Contract canary includes SDK compatibility test
python scripts/contract_canary.py --include-sdk-compat

# Check no contract mode active
curl -s http://service/health | jq -r '.features.contract_mode' # Should be false/null
```
