import logging
from typing import Optional

import redis.asyncio as redis

from .settings import REDIS_URL

logger = logging.getLogger("app")

_cache: Optional[redis.Redis] = None


async def get_cache():
    global _cache
    if _cache is None:
        _cache = redis.from_url(REDIS_URL, decode_responses=True)
        try:
            await _cache.ping()
            logger.info(f"Connected to Redis at {REDIS_URL}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            _cache = None
            raise
    return _cache
