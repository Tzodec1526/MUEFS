from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from sqlalchemy import DateTime, Dialect, TypeDecorator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings
from app.services import document_service, storage_intent

engine_kwargs: dict = {"echo": settings.database_echo}
if "sqlite" not in settings.database_url:
    engine_kwargs["pool_size"] = 20
    engine_kwargs["max_overflow"] = 10
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_recycle"] = 300
    engine_kwargs["connect_args"] = {"command_timeout": 30}

engine = create_async_engine(settings.database_url, **engine_kwargs)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator[datetime]):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with session_scope(
        async_session, drain=document_service.uses_local_storage(),
    ) as session:
        yield session


@asynccontextmanager
async def session_scope(
    sessions: async_sessionmaker[AsyncSession], *, drain: bool,
) -> AsyncIterator[AsyncSession]:
    async with sessions() as session:
        try:
            yield session
        except BaseException:
            await storage_intent.rollback_with_upload_cleanup(session)
            raise
        try:
            await session.commit()
        except BaseException:
            await storage_intent.rollback_with_upload_cleanup(session, verify_with=sessions)
            raise
        queued = storage_intent.queued_deletion(session.sync_session)
    if queued and drain:
        from app import storage_cleanup

        await storage_cleanup.drain(sessions)
