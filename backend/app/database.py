from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings
from app.services import document_service, storage_intent

# SQLite doesn't support pool_size/max_overflow/pool_pre_ping
engine_kwargs: dict = {"echo": settings.database_echo}
if "sqlite" not in settings.database_url:
    engine_kwargs["pool_size"] = 20
    engine_kwargs["max_overflow"] = 10
    engine_kwargs["pool_pre_ping"] = True  # Detect stale connections
    engine_kwargs["pool_recycle"] = 300  # Recycle connections every 5 min
    engine_kwargs["connect_args"] = {"command_timeout": 30}  # 30s query timeout

engine = create_async_engine(settings.database_url, **engine_kwargs)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Use function scope so commit failures can prevent a successful HTTP response."""
    async with async_session() as session:
        try:
            yield session
        except BaseException:
            await storage_intent.rollback_with_upload_cleanup(session)
            raise
        try:
            await session.commit()
        except BaseException:
            await storage_intent.rollback_with_upload_cleanup(
                session, verify_with=async_session,
            )
            raise
        queued = storage_intent.queued_deletion(session.sync_session)
    if queued and document_service.uses_local_storage():
        # Deployments that keep documents on local disk (the demos) run no storage
        # worker: delete removed drafts' files once their removal has committed.
        from app import storage_cleanup  # it imports this module

        await storage_cleanup.drain(async_session)
