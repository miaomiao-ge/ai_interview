import json
import time
from typing import Any, Optional

from core.config import REDIS_KEY_PREFIX, REDIS_REQUIRED, REDIS_URL

_client = None
_unavailable_until = 0.0


def get_redis_client():
    """Return a Redis client when Redis is reachable; otherwise return None."""
    global _client, _unavailable_until

    if _client is not None:
        return _client

    now = time.time()
    if now < _unavailable_until:
        if REDIS_REQUIRED:
            raise RuntimeError("Redis is required but is currently marked unavailable")
        return None

    try:
        import redis

        client = redis.Redis.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=0.3,
            socket_timeout=0.5,
        )
        client.ping()
        _client = client
        return _client
    except Exception as exc:
        _unavailable_until = now + 5
        _client = None
        if REDIS_REQUIRED:
            raise RuntimeError(f"Redis is required but unavailable: {exc}") from exc
        return None


def redis_available() -> bool:
    return get_redis_client() is not None


def ensure_redis_available() -> None:
    if get_redis_client() is None:
        raise RuntimeError("Redis is unavailable")


def redis_key(*parts: Any) -> str:
    clean_parts = [str(part).strip(":") for part in parts if str(part)]
    return ":".join([REDIS_KEY_PREFIX, *clean_parts])


def json_get(key: str) -> Optional[dict]:
    client = get_redis_client()
    if client is None:
        return None
    raw_value = client.get(key)
    if not raw_value:
        return None
    try:
        value = json.loads(raw_value)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        return None


def json_set(key: str, value: dict, ttl_seconds: int) -> bool:
    client = get_redis_client()
    if client is None:
        return False
    client.setex(key, ttl_seconds, json.dumps(value, ensure_ascii=False))
    return True


def delete_key(key: str) -> bool:
    client = get_redis_client()
    if client is None:
        return False
    client.delete(key)
    return True


def fixed_window_rate_limited(key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
    """Return (is_limited, current_count). Missing Redis means no global limit."""
    client = get_redis_client()
    if client is None:
        return False, 0

    count = client.incr(key)
    if count == 1:
        client.expire(key, window_seconds)
    return count > limit, int(count)


def fixed_window_current_count(key: str) -> int:
    """Return the current counter value without incrementing it."""
    client = get_redis_client()
    if client is None:
        return 0
    try:
        value = client.get(key)
        return int(value or 0)
    except Exception:
        return 0


def fixed_window_increment(key: str, window_seconds: int) -> int:
    """Increment a fixed-window counter and return the new count."""
    client = get_redis_client()
    if client is None:
        return 0
    count = client.incr(key)
    if count == 1:
        client.expire(key, window_seconds)
    return int(count)
