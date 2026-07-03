from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncAttrs
from .config import get_settings

setting = get_settings()

engine = create_async_engine(url=setting.database_url, echo = True)

AsyncLocalSession = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,   # keep ORM objects usable after commit (needed to return them from async endpoints)
)

class Base(AsyncAttrs, DeclarativeBase):
    pass

async def get_db():
    async with AsyncLocalSession() as session:
        yield session
