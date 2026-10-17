from sqlalchemy.ext.asyncio import (async_sessionmaker,AsyncSession, create_async_engine)
from app.core.settings import Settings as settings
from fastapi import depends
from typing import Annotated


DATABASE_URL = settings.DATABASE_URL
DIRECT_URL = settings.DIRECT_URL


engine = create_async_engine(DATABASE_URL,echo=True, pool_pre_ping=True, future=True)
async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session 

sessiondb = Annotated[AsyncSession, depends(get_session)]