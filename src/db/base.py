from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
import os

from src.core.config import get_settings

settings = get_settings()

# Prioritize Railway's DATABASE_URL environment variable
SQLALCHEMY_DATABASE_URL = os.getenv('DATABASE_URL', settings.db_url)

# PostgreSQL driver correction (Railway uses postgres://, SQLAlchemy needs postgresql://)
if SQLALCHEMY_DATABASE_URL.startswith('postgres://'):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace('postgres://', 'postgresql://', 1)

# Naming convention for constraints
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=convention)


class Base(DeclarativeBase):
    """Base class for all models."""
    metadata = metadata


# Create async engine
engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    echo=settings.debug,
    future=True,
)

# Create async session factory
async_session_factory = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_session() -> AsyncSession:
    """Get a database session."""
    async with async_session_factory() as session:
        yield session 