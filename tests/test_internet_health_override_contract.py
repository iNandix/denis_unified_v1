"""Test InternetHealth override contract."""

import os
import pytest

from denis_unified_v1.kernel.internet_health import get_internet_health


def test_internet_health_override_contract():
    """Test DENIS_INTERNET_STATUS override is contractual and takes priority."""
    health = get_internet_health()
    health.invalidate()

    # Test OK override
    os.environ["DENIS_INTERNET_STATUS"] = "OK"
    try:
        assert health.check() == "OK"
    finally:
        del os.environ["DENIS_INTERNET_STATUS"]

    # Test DOWN override
    os.environ["DENIS_INTERNET_STATUS"] = "DOWN"
    try:
        assert health.check() == "DOWN"
    finally:
        del os.environ["DENIS_INTERNET_STATUS"]

    # Test UNKNOWN override
    os.environ["DENIS_INTERNET_STATUS"] = "UNKNOWN"
    try:
        assert health.check() == "UNKNOWN"
    finally:
        del os.environ["DENIS_INTERNET_STATUS"]

    # Clean up and ensure no override
    health.invalidate()
    # Actual check may vary, but no override
    status = health.check()
    assert status in ("OK", "DOWN")
