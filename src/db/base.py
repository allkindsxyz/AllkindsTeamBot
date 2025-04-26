from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
import os
import urllib.parse
from loguru import logger
import re

from src.core.config import get_settings

settings = get_settings()

# Prioritize Railway's DATABASE_URL environment variable
ORIGINAL_DB_URL = os.getenv('DATABASE_URL', settings.db_url)
logger.info(f"Original database URL type: {type(ORIGINAL_DB_URL)}")

# Function to safely process database URL
def process_database_url(url):
    if not url:
        logger.warning("No database URL provided, falling back to SQLite")
        return "sqlite+aiosqlite:///./allkinds.db"
    
    logger.info(f"Processing database URL (starts with): {url[:15]}...")
    
    # Handle SQLite explicitly
    if url.startswith('sqlite'):
        logger.info("Using SQLite database")
        return url
    
    # Parse the URL to handle parameters safely
    try:
        # Handle Railway's postgres:// format
        if url.startswith('postgres://') or url.startswith('postgresql://'):
            # For asyncpg, we need to use postgresql+asyncpg://
            if 'asyncpg' not in url:
                if url.startswith('postgres://'):
                    url = url.replace('postgres://', 'postgresql+asyncpg://', 1)
                else:
                    url = url.replace('postgresql://', 'postgresql+asyncpg://', 1)
            
            # We no longer modify hostnames as they need to remain as provided by Railway
            logger.info(f"Processed database URL (starts with): {url[:15]}...")
            return url
            
        logger.warning(f"Unrecognized database URL format: {url[:10]}...")
        return url
    except Exception as e:
        logger.error(f"Error processing database URL: {e}")
        logger.info("Falling back to SQLite database")
        return "sqlite+aiosqlite:///./allkinds.db"

# Process the database URL
SQLALCHEMY_DATABASE_URL = process_database_url(ORIGINAL_DB_URL)
logger.info(f"Final database URL type: {type(SQLALCHEMY_DATABASE_URL)}")
logger.info(f"Using database driver: {SQLALCHEMY_DATABASE_URL.split('://')[0]}")

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


# Set connect_args based on database type
connect_args = {}
if 'postgresql' in SQLALCHEMY_DATABASE_URL or 'postgres' in SQLALCHEMY_DATABASE_URL:
    # PostgreSQL specific connect args for asyncpg
    connect_args = {
        "timeout": 10,  # Connection timeout in seconds
        "server_settings": {
            "application_name": "allkinds"
        }
        # Removed the 'host': '127.0.0.1' override which was causing issues
    }

# Create async engine with enhanced parameters for better connection handling
engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    echo=settings.debug,
    future=True,
    pool_pre_ping=True,               # Verify connections before using them
    pool_recycle=300,                 # Recycle connections every 5 minutes
    pool_timeout=30,                  # Connection timeout of 30 seconds
    pool_size=5,                      # Smaller pool size to avoid overwhelming the database
    max_overflow=10,                  # Allow up to 10 additional connections
    connect_args=connect_args         # Database-specific connection arguments
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

def get_engine():
    """Get the SQLAlchemy engine."""
    return engine 

def get_async_engine(database_url=None):
    """Get the SQLAlchemy async engine, optionally creating a new one with the specified URL."""
    if database_url:
        # Create a new engine with the specified URL
        from sqlalchemy.ext.asyncio import create_async_engine
        
        # Force the use of asyncpg by explicitly replacing the dialect in the URL
        if database_url.startswith('postgresql://') or database_url.startswith('postgres://'):
            # Replace 'postgresql://' or 'postgres://' with 'postgresql+asyncpg://'
            if database_url.startswith('postgresql://'):
                database_url = database_url.replace('postgresql://', 'postgresql+asyncpg://', 1)
            else:
                database_url = database_url.replace('postgres://', 'postgresql+asyncpg://', 1)
            
            logger.info(f"Enforcing asyncpg driver with URL: {database_url[:20]}...")
        
        # Create the engine with the processed URL
        return create_async_engine(
            database_url,
            echo=settings.debug,
            future=True,
            pool_pre_ping=True,
            pool_recycle=300,
            pool_timeout=30,
            pool_size=5,
            max_overflow=10
        )
    # Otherwise, return the global engine
    return engine

async def init_models(engine):
    """Initialize database models."""
    from sqlalchemy import inspect, text
    
    logger.info("Initializing database models...")
    
    try:
        async with engine.begin() as conn:
            # Test connection
            await conn.execute(text("SELECT 1"))
            logger.info("Database connection successful")
            
            # Check if tables exist
            tables = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
            
            if not tables:
                logger.info("No tables found. Creating database schema...")
                await conn.run_sync(Base.metadata.create_all)
                logger.info("Database schema created.")
            else:
                logger.info(f"Found existing tables: {tables}")
    except Exception as e:
        logger.error(f"Error initializing database models: {e}")
        # Don't raise - let the app try to continue
        
    logger.info("Database models initialization complete.") 