from loguru import logger
from sqlalchemy.ext.asyncio import create_async_engine

from src.db.base import Base, SQLALCHEMY_DATABASE_URL
from src.db.models import * # Import all models to register metadata


async def init_db():
    """Initialize the database and create tables."""
    logger.info("Initializing database...")
    engine = create_async_engine(SQLALCHEMY_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        # Drop all tables (for development, remove in production)
        # await conn.run_sync(Base.metadata.drop_all)
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    logger.info("Database initialized.")

# TODO: Integrate Alembic for proper migrations 