"""
@file cache.py
@brief Redis cache manager singleton
@details
Provides a unified interface for Redis operations, connection management,
and caching decorators. Uses a global singleton pattern for the Redis client.

@author Vectra Project
@date 2025-12-13
"""

import os
import json
import logging
from typing import Optional, Any, Callable
from functools import wraps
import redis.asyncio as redis

logger = logging.getLogger(__name__)

class RedisCache:
    """
    @brief Singleton wrapper for Async Redis client
    """
    _instance: Optional['RedisCache'] = None
    client: Optional[redis.Redis] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisCache, cls).__new__(cls)
        return cls._instance

    async def connect(self):
        """
        @brief Initialize Redis connection pool
        @details
        Connects using REDIS_URL environment variable.
        """
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        try:
            self.client = redis.from_url(
                redis_url, 
                encoding="utf-8", 
                decode_responses=True
            )
            await self.client.ping()
            logger.info(f"Connected to Redis at {redis_url}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.client = None

    async def close(self):
        """
        @brief Close Redis connection
        """
        if self.client:
            await self.client.close()
            logger.info("Redis connection closed")

    async def get(self, key: str) -> Optional[Any]:
        """
        @brief Retrieve value from cache
        """
        if not self.client:
            return None
        try:
            value = await self.client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.warning(f"Redis get error for {key}: {e}")
            return None

    async def set(self, key: str, value: Any, ttl: int = 3600):
        """
        @brief Set value in cache with TTL
        """
        if not self.client:
            return
        try:
            serialized = json.dumps(value)
            await self.client.setex(key, ttl, serialized)
        except Exception as e:
            logger.warning(f"Redis set error for {key}: {e}")


# Global instance
cache = RedisCache()


def cache_response(ttl: int = 3600, key_prefix: str = ""):
    """
    @brief Decorator for caching async function results
    @details
    Generates a cache key based on function arguments.
    Note: Requires the decorated function to return JSON-serializable data.
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Construct simple cache key
            # In a real app, might need more robust key generation
            arg_str = ":".join([str(a) for a in args])
            kwarg_str = ":".join([f"{k}={v}" for k, v in kwargs.items() if k != "db"])
            
            # If explicit key provided in kwargs, use it (for manual invalidation logic maybe?)
            # Or just append.
            
            cache_key = f"{key_prefix}:{func.__name__}:{arg_str}:{kwarg_str}"
            
            # Try cache
            cached_val = await cache.get(cache_key)
            if cached_val is not None:
                logger.debug(f"Cache hit for {cache_key}")
                return cached_val
            
            # Execute function
            result = await func(*args, **kwargs)
            
            # Cache result
            await cache.set(cache_key, result, ttl)
            
            return result
        return wrapper
    return decorator
