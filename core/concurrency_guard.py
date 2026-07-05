import threading
import time
from dataclasses import dataclass

from core.config import (
    ACTIVE_SESSION_TTL_SECONDS,
    ASR_CONNECTION_TTL_SECONDS,
    MAX_ACTIVE_ASR_CONNECTIONS,
    MAX_ACTIVE_INTERVIEWS,
)
from core.redis_utils import get_redis_client, redis_key


@dataclass
class AdmissionResult:
    allowed: bool
    active_count: int
    limit: int
    source: str
    message: str = ""


_local_lock = threading.RLock()
_local_active: dict[str, dict[str, float]] = {
    "sessions": {},
    "asr": {},
}

_ADMISSION_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local member = ARGV[2]
local ttl = tonumber(ARGV[3])
local limit = tonumber(ARGV[4])
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - ttl)
local exists = redis.call('ZSCORE', key, member)
local count = redis.call('ZCARD', key)
if exists or count < limit then
    redis.call('ZADD', key, now, member)
    redis.call('EXPIRE', key, ttl)
    if not exists then
        count = count + 1
    end
    return {1, count, limit}
end
return {0, count, limit}
"""


def _active_key(name: str) -> str:
    return redis_key("active", name)


def _prune_local(name: str, ttl_seconds: int) -> None:
    now = time.time()
    bucket = _local_active.setdefault(name, {})
    stale_members = [member for member, seen_at in bucket.items() if seen_at < now - ttl_seconds]
    for member in stale_members:
        bucket.pop(member, None)


def _try_register_local(name: str, member: str, limit: int, ttl_seconds: int) -> AdmissionResult:
    with _local_lock:
        _prune_local(name, ttl_seconds)
        bucket = _local_active.setdefault(name, {})
        already_active = member in bucket
        active_count = len(bucket)
        if not already_active and active_count >= limit:
            return AdmissionResult(False, active_count, limit, "local", "capacity limit reached")
        bucket[member] = time.time()
        return AdmissionResult(True, len(bucket), limit, "local")


def _try_register(name: str, member: str, limit: int, ttl_seconds: int) -> AdmissionResult:
    client = get_redis_client()
    if client is None:
        return _try_register_local(name, member, limit, ttl_seconds)

    try:
        allowed, active_count, limit_value = client.eval(
            _ADMISSION_LUA,
            1,
            _active_key(name),
            time.time(),
            member,
            ttl_seconds,
            limit,
        )
        return AdmissionResult(
            bool(int(allowed)),
            int(active_count),
            int(limit_value),
            "redis",
            "" if int(allowed) else "capacity limit reached",
        )
    except Exception:
        return _try_register_local(name, member, limit, ttl_seconds)


def _release(name: str, member: str) -> None:
    client = get_redis_client()
    if client is not None:
        try:
            client.zrem(_active_key(name), member)
        except Exception:
            pass
    with _local_lock:
        _local_active.setdefault(name, {}).pop(member, None)


def _active_count(name: str, ttl_seconds: int) -> int:
    client = get_redis_client()
    if client is not None:
        try:
            now = time.time()
            key = _active_key(name)
            client.zremrangebyscore(key, "-inf", now - ttl_seconds)
            return int(client.zcard(key))
        except Exception:
            pass
    with _local_lock:
        _prune_local(name, ttl_seconds)
        return len(_local_active.setdefault(name, {}))


def try_register_active_session(session_id: str) -> AdmissionResult:
    return _try_register("sessions", session_id, MAX_ACTIVE_INTERVIEWS, ACTIVE_SESSION_TTL_SECONDS)


def release_active_session(session_id: str) -> None:
    if session_id:
        _release("sessions", session_id)


def try_register_active_asr(connection_id: str) -> AdmissionResult:
    return _try_register("asr", connection_id, MAX_ACTIVE_ASR_CONNECTIONS, ASR_CONNECTION_TTL_SECONDS)


def release_active_asr(connection_id: str) -> None:
    if connection_id:
        _release("asr", connection_id)


def get_capacity_snapshot() -> dict:
    return {
        "active_interviews": _active_count("sessions", ACTIVE_SESSION_TTL_SECONDS),
        "max_active_interviews": MAX_ACTIVE_INTERVIEWS,
        "active_asr_connections": _active_count("asr", ASR_CONNECTION_TTL_SECONDS),
        "max_active_asr_connections": MAX_ACTIVE_ASR_CONNECTIONS,
    }
