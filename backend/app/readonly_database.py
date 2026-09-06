"""Consistent, read-only snapshots for records export and recovery verification."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine


class ReadOnlyDatabaseError(ValueError):
    """Operator guidance that does not disclose connection credentials."""


@asynccontextmanager
async def read_only_connection(database_url: str) -> AsyncIterator[AsyncConnection]:
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite":
        if not url.database or url.database == ":memory:" or url.query.get("uri"):
            raise ReadOnlyDatabaseError("Use a file-backed SQLite database URL without URI options")
        try:
            database = Path(url.database).resolve(strict=True)
        except FileNotFoundError as exc:
            raise ReadOnlyDatabaseError("The configured SQLite database does not exist") from exc
        url = url.set(database=database.as_uri(), query={**url.query, "mode": "ro", "uri": "true"})
    elif url.get_backend_name() != "postgresql":
        raise ReadOnlyDatabaseError("Read-only snapshots support PostgreSQL and SQLite")
    engine = create_async_engine(url, echo=False)
    try:
        async with engine.connect() as connection:
            if url.get_backend_name() == "postgresql":
                await connection.execution_options(isolation_level="REPEATABLE READ")
                await connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            else:
                await connection.exec_driver_sql("PRAGMA query_only=ON")
                # sqlite3's legacy transaction mode does not begin on SELECT alone.
                await connection.exec_driver_sql("BEGIN")
            yield connection
    finally:
        await engine.dispose()
