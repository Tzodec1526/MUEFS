from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# SQLite doesn't support pool_size/max_overflow/pool_pre_ping
engine_kwargs: dict = {"echo": settings.debug}
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
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
