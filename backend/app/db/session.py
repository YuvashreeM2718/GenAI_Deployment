"""
Async engine + session factory for the backend's read-only queries
(quotation lookups). Separate from LangGraph's own checkpointer connection.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(settings.sqlalchemy_database_url, future=True)
AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
