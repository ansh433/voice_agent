"""Async PostgreSQL connection-pool lifecycle and transaction helpers."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from types import TracebackType
from typing import Literal

import asyncpg
from asyncpg.pool import PoolConnectionProxy

type IsolationLevel = Literal[
    "read_committed",
    "read_uncommitted",
    "repeatable_read",
    "serializable",
]


class DatabaseNotStartedError(RuntimeError):
    """Raised when a database operation is attempted before pool startup."""


class Database:
    """Own an asyncpg pool with bounded acquisition, queries, and transactions."""

    def __init__(
        self,
        dsn: str,
        *,
        min_pool_size: int = 1,
        max_pool_size: int = 10,
        acquire_timeout_seconds: float = 2.0,
        query_timeout_seconds: float = 2.0,
        transaction_timeout_seconds: float = 5.0,
    ) -> None:
        if min_pool_size < 0:
            raise ValueError("min_pool_size cannot be negative")
        if max_pool_size < 1 or max_pool_size < min_pool_size:
            raise ValueError("max_pool_size must be positive and at least min_pool_size")
        if (
            min(
                acquire_timeout_seconds,
                query_timeout_seconds,
                transaction_timeout_seconds,
            )
            <= 0
        ):
            raise ValueError("database timeouts must be positive")

        self._dsn = dsn
        self._min_pool_size = min_pool_size
        self._max_pool_size = max_pool_size
        self._acquire_timeout_seconds = acquire_timeout_seconds
        self._query_timeout_seconds = query_timeout_seconds
        self._transaction_timeout_seconds = transaction_timeout_seconds
        self._pool: asyncpg.Pool | None = None

    @property
    def pool(self) -> asyncpg.Pool:
        """Return the started pool or fail with an actionable lifecycle error."""
        if self._pool is None:
            raise DatabaseNotStartedError("database pool has not been started")
        return self._pool

    @property
    def query_timeout_seconds(self) -> float:
        return self._query_timeout_seconds

    async def start(self) -> None:
        """Create the pool once; repeated startup calls are harmless."""
        if self._pool is not None:
            return

        self._pool = await asyncpg.create_pool(
            dsn=self._dsn,
            min_size=self._min_pool_size,
            max_size=self._max_pool_size,
            command_timeout=self._query_timeout_seconds,
            init=_initialize_connection,
        )

    async def close(self) -> None:
        """Close the pool once; repeated shutdown calls are harmless."""
        pool = self._pool
        self._pool = None
        if pool is not None:
            await pool.close()

    async def __aenter__(self) -> Database:
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()

    @asynccontextmanager
    async def connection(
        self,
    ) -> AsyncGenerator[PoolConnectionProxy[asyncpg.Record]]:
        """Borrow one connection from the pool within the acquisition deadline."""
        async with self.pool.acquire(timeout=self._acquire_timeout_seconds) as connection:
            yield connection

    @asynccontextmanager
    async def transaction(
        self,
        *,
        isolation: IsolationLevel = "read_committed",
    ) -> AsyncGenerator[PoolConnectionProxy[asyncpg.Record]]:
        """Run work on one connection in a transaction with a total deadline."""
        async with asyncio.timeout(self._transaction_timeout_seconds):
            async with self.connection() as connection:
                async with connection.transaction(isolation=isolation):
                    await connection.execute(
                        "SELECT set_config('statement_timeout', $1, true)",
                        f"{int(self._query_timeout_seconds * 1_000)}ms",
                    )
                    yield connection


async def _initialize_connection(connection: asyncpg.Connection) -> None:
    await connection.execute("SET TIME ZONE 'UTC'")
