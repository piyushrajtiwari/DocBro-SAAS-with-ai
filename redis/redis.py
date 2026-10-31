import logging
from typing import Any

import redis.asyncio as redis
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.settings import settings

logger = logging.getLogger(__name__)


class RedisClient:
    """
    Asynchronous Redis client with connection pooling.

    Features:
    - Async Redis operations
    - Connection pooling
    - Connection and socket timeouts
    - Health checks
    - Retry support
    - Structured logging
    - Graceful shutdown
    """

    def __init__(self) -> None:
        self.client: Redis = redis.Redis(
            host=settings.HOST,
            port=settings.PORT,
            db=settings.DB,
            password=settings.PASSWORD or None,

            # Decode Redis responses into Python strings.
            decode_responses=True,

            # Connection pool configuration.
            max_connections=50,

            # Avoid waiting indefinitely for connections.
            socket_connect_timeout=5,
            socket_timeout=5,

            # Periodically verify idle connections.
            health_check_interval=30,

            # Retry selected connection failures.
            retry_on_timeout=True,

            # Do not silently retry indefinitely.
            retry=redis.retry.Retry(
                redis.retry.ExponentialBackoff(
                    base=0.1,
                    cap=1.0,
                ),
                3,
            ),
        )

    async def connect(self) -> Redis:
        """Verify that Redis is reachable and return the client."""
        try:
            await self.client.ping()
            logger.info("Redis connection successful")
            return self.client

        except RedisError:
            logger.exception("Redis connection failed")
            raise

    async def set_key(
        self,
        key: str,
        value: Any,
        expiry_seconds: int | None = None,
    ) -> bool:
        """Store a value, optionally with a TTL."""
        if expiry_seconds is not None and expiry_seconds <= 0:
            raise ValueError("expiry_seconds must be greater than zero")

        try:
            result = await self.client.set(
                name=key,
                value=value,
                ex=expiry_seconds,
            )
            return result is True

        except RedisError:
            logger.exception("Failed to set Redis key: %s", key)
            raise

    async def get_key(self, key: str) -> str | None:
        """Retrieve a value from Redis."""
        try:
            return await self.client.get(key)

        except RedisError:
            logger.exception("Failed to get Redis key: %s", key)
            raise

    async def delete_key(self, key: str) -> int:
        """Delete a key and return the number of keys removed."""
        try:
            return await self.client.delete(key)

        except RedisError:
            logger.exception("Failed to delete Redis key: %s", key)
            raise

    async def exists(self, key: str) -> bool:
        """Check whether a key exists."""
        try:
            return bool(await self.client.exists(key))

        except RedisError:
            logger.exception("Failed to check Redis key: %s", key)
            raise

    async def health_check(self) -> bool:
        """Check Redis availability without exposing connection details."""
        try:
            return bool(await self.client.ping())

        except RedisError:
            logger.warning("Redis health check failed", exc_info=True)
            return False

    async def close(self) -> None:
        """Close Redis connections gracefully."""
        await self.client.aclose()
        logger.info("Redis connections closed")


# Shared client instance for the application.
redis_client = RedisClient()
