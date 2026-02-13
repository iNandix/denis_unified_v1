"""
Tests for Rate Limiting Module.
"""
import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from denis_unified_v1.rate_limiting import RateLimiter


@pytest.fixture
async def mock_redis():
    """Mock Redis client."""
    mock_client = AsyncMock()
    mock_client.ping.return_value = None
    mock_client.script_load.return_value = "sha1_script"
    mock_client.evalsha.return_value = 1  # Allowed
    return mock_client


@pytest.mark.asyncio
async def test_rate_limiter_redis_allowed(mock_redis):
    """Test rate limiter with Redis, allowed."""
    limiter = RateLimiter(limit=10, window=60)
    limiter.redis_client = mock_redis
    limiter.lua_script = "sha1_script"

    allowed = await limiter.is_allowed("client1")
    assert allowed is True
    mock_redis.evalsha.assert_called_once_with("sha1_script", keys=["rate_limit:client1"], args=[10, 60])


@pytest.mark.asyncio
async def test_rate_limiter_redis_blocked(mock_redis):
    """Test rate limiter with Redis, blocked."""
    mock_redis.evalsha.return_value = 0  # Blocked
    limiter = RateLimiter(limit=10, window=60)
    limiter.redis_client = mock_redis
    limiter.lua_script = "sha1_script"

    allowed = await limiter.is_allowed("client1")
    assert allowed is False


@pytest.mark.asyncio
async def test_rate_limiter_fallback_allowed():
    """Test fallback in-memory, allowed."""
    limiter = RateLimiter(limit=2, window=60)
    # No redis_client, use fallback

    assert await limiter.is_allowed("client1") is True
    assert await limiter.is_allowed("client1") is True
    assert await limiter.is_allowed("client1") is False  # Exceed limit


@pytest.mark.asyncio
async def test_rate_limiter_fallback_ttl():
    """Test fallback TTL expiration."""
    limiter = RateLimiter(limit=1, window=1)  # 1 second window

    assert await limiter.is_allowed("client1") is True
    assert await limiter.is_allowed("client1") is False  # Blocked

    await asyncio.sleep(1.1)  # Wait for TTL

    assert await limiter.is_allowed("client1") is True  # Allowed again


@pytest.mark.asyncio
async def test_initialize_success(mock_redis):
    """Test initialize with Redis success."""
    with patch('denis_unified_v1.rate_limiting.redis.from_url', return_value=mock_redis):
        limiter = RateLimiter()
        await limiter.initialize()
        assert limiter.redis_client is mock_redis
        assert limiter.lua_script == "sha1_script"


@pytest.mark.asyncio
async def test_initialize_failure():
    """Test initialize with Redis failure."""
    with patch('denis_unified_v1.rate_limiting.redis.from_url', side_effect=Exception("Connection failed")):
        limiter = RateLimiter()
        await limiter.initialize()
        assert limiter.redis_client is None


@pytest.mark.asyncio
async def test_close():
    """Test close Redis client."""
    limiter = RateLimiter()
    limiter.redis_client = AsyncMock()
    await limiter.close()
    limiter.redis_client.close.assert_called_once()
