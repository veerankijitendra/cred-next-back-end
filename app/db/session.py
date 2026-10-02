from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=True,
    pool_size=10,  # keep 10 connections open, ready to use
    max_overflow=5,  # allow up to 5 extra temporary connections under burst load
    pool_timeout=30,  # wait up to 30s for a free connection before erroring
    pool_recycle=1800,  # recycle connections after 30 min (avoids stale/dropped conns)
    pool_pre_ping=True,  # test connection liveness before handing it out
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)


async def get_db() -> AsyncGenerator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session
