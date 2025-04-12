from loguru import logger
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import inspect

from src.db.base import Base, SQLALCHEMY_DATABASE_URL
from src.db.models import * # Import all models to register metadata


async def init_db():
    """Initialize the database and create tables if they don't exist."""
    logger.info("Initializing database...")
    engine = create_async_engine(SQLALCHEMY_DATABASE_URL, echo=True)
    
    async with engine.begin() as conn:
        # Check if tables exist using run_sync
        tables = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
        
        if not tables:
            logger.info("No tables found. Creating database schema...")
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database schema created.")
        else:
            logger.info(f"Found existing tables: {tables}")
    
    await engine.dispose()
    logger.info("Database initialization complete.")

# TODO: Integrate Alembic for proper migrations 