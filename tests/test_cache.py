"""
Test Redis Cache Module
"""
import pytest
from unittest.mock import AsyncMock, patch
from app.core.cache import RedisCache, cache_response

@pytest.fixture
def mock_redis():
    with patch("redis.asyncio.from_url") as mock:
        yield mock

@pytest.mark.asyncio
async def test_redis_connection(mock_redis):
    cache = RedisCache()
    
    # Mock client
    mock_client = AsyncMock()
    mock_redis.return_value = mock_client
    
    await cache.connect()
    
    mock_redis.assert_called_once()
    mock_client.ping.assert_awaited_once()
    assert cache.client == mock_client
    
    await cache.close()
    mock_client.close.assert_awaited_once()

@pytest.mark.asyncio
async def test_redis_get_set(mock_redis):
    # Reset singleton
    RedisCache._instance = None
    cache = RedisCache()
    cache.client = AsyncMock()
    
    # Test Set
    await cache.set("test_key", {"foo": "bar"}, ttl=60)
    cache.client.setex.assert_awaited_once()
    
    # Test Get
    cache.client.get.return_value = '{"foo": "bar"}'
    result = await cache.get("test_key")
    assert result == {"foo": "bar"}
    
    # Test Miss
    cache.client.get.return_value = None
    result = await cache.get("missing")
    assert result is None
