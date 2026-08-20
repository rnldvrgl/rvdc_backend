from typing import Optional
from django.core.cache import cache


def make_dashboard_cache_key(start_dt: str, end_dt: str, stall_id: Optional[int]) -> str:
    stall_part = str(stall_id) if stall_id is not None else "all"
    return f"dashboard:{start_dt}:{end_dt}:{stall_part}"


def invalidate_dashboard_cache(prefix: str = "dashboard:") -> None:
    """Invalidate dashboard cache keys.

    Attempts to delete matching keys efficiently when using django-redis.
    Falls back to `cache.clear()` if pattern delete isn't available.
    """
    try:
        # django-redis exposes a `delete_pattern` helper on the cache object
        delete_pattern = getattr(cache, "delete_pattern", None)
        if callable(delete_pattern):
            # delete keys like 'dashboard:*'
            delete_pattern(f"{prefix}*")
            return

        # Fallback: try to access raw client (may be Redis client)
        client = getattr(cache, "client", None)
        if client:
            try:
                redis_client = client.get_client()
            except Exception:
                redis_client = None
            if redis_client:
                # Use SCAN to avoid blocking Redis
                cursor = 0
                pattern = f"{prefix}*"
                keys = []
                while True:
                    cursor, found = redis_client.scan(cursor=cursor, match=pattern, count=1000)
                    if found:
                        keys.extend(found)
                    if cursor == 0:
                        break
                if keys:
                    redis_client.delete(*keys)
                    return
    except Exception:
        # best-effort: fall through to clear
        pass

    # last-resort: clear whole cache
    try:
        cache.clear()
    except Exception:
        pass
