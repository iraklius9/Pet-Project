import logging
import redis

from .settings import REDIS_URL

logger = logging.getLogger("app")

_cache = None


def get_cache():
    global _cache
    if _cache is None:
        pool = redis.ConnectionPool.from_url(REDIS_URL, decode_responses=True)
        _cache = redis.Redis(connection_pool=pool)
        try:
            _cache.ping()
            logger.info(f"Connected to Redis at {REDIS_URL}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            _cache = None
            raise
    return _cache
