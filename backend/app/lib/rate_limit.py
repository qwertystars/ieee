from redis.exceptions import RedisError

from app.deps import get_redis

RATE_LIMIT_PREFIX = "resqnet:rate-limit:"


def consume_rate_limit(org_id: str, subject_id: str, limit: int, window_seconds: int) -> bool:
    if limit <= 0 or window_seconds <= 0:
        return False
    client = get_redis()
    if client is None:
        return False
    key = f"{RATE_LIMIT_PREFIX}{org_id}:{subject_id}"
    try:
        with client.pipeline(transaction=True) as pipeline:
            pipeline.incr(key)
            pipeline.expire(key, window_seconds)
            count, _ = pipeline.execute()
        return int(count) <= limit
    except (OSError, RedisError, TimeoutError, TypeError, ValueError):
        return False
