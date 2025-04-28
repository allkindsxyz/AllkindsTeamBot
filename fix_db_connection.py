#!/usr/bin/env python3
"""
Script to fix database connection issues in Railway deployment
This script addresses:
1. Connection timeouts by adding retry logic
2. Proper error handling for database connections
3. Setting appropriate timeouts
"""

import os
import re
import shutil
import sys
from datetime import datetime

# Files that need updating
DB_BASE_PATH = "src/db/base.py"
COMMUNICATOR_MIDDLEWARES_PATH = "src/communicator_bot/middlewares.py"

def create_backup(file_path):
    """Create a backup of the file before modifying it"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{file_path}.db_fix_bak_{timestamp}"
    try:
        shutil.copy2(file_path, backup_path)
        print(f"Created backup at {backup_path}")
        return True
    except Exception as e:
        print(f"Error creating backup of {file_path}: {e}")
        return False

def fix_db_base():
    """Fix the database connection logic in src/db/base.py"""
    if not os.path.exists(DB_BASE_PATH):
        print(f"Error: {DB_BASE_PATH} not found!")
        return False
    
    # Create backup
    if not create_backup(DB_BASE_PATH):
        print("Failed to create backup, aborting to be safe.")
        return False
    
    # Read the file
    with open(DB_BASE_PATH, 'r') as file:
        content = file.read()
    
    # Add retry logic to get_async_engine function
    get_engine_pattern = r"def get_async_engine\([^)]*\):\s+[^\"]*\"\"\"[^\"]*\"\"\"\s+(.*?)(\s+return engine)"
    
    get_engine_replacement = r"""def get_async_engine(*args, **kwargs):
    \"\"\"Get SQLAlchemy async engine with retry logic.\"\"\"
    import time
    from sqlalchemy.exc import SQLAlchemyError
    
    # Get database URL from environment with proper error handling
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL environment variable is not set")
        database_url = os.environ.get("POSTGRES_URL")
        if database_url:
            logger.info("Using POSTGRES_URL as fallback")
        else:
            logger.critical("No database URL found in environment variables!")
            if IS_RAILWAY:
                # In production, fail fast
                raise ValueError("DATABASE_URL environment variable is required")
            else:
                # In development, use SQLite as a fallback
                logger.warning("Using SQLite as fallback for development")
                database_url = "sqlite+aiosqlite:///./test.db"
    
    # Force asyncpg driver for PostgreSQL
    if database_url.startswith('postgresql:'):
        database_url = database_url.replace('postgresql:', 'postgresql+asyncpg:')
        logger.info(f"Enforcing asyncpg driver with URL: {database_url[:25]}...")
    
    # Set connection parameters with sensible timeouts
    connect_args = {
        'timeout': 10,  # Connection timeout in seconds
        'command_timeout': 10,  # Command execution timeout
    }
    
    # Use a separate pool for statements, with retries
    engine_args = {
        'pool_size': 5,  # Start with a smaller pool
        'max_overflow': 10,
        'pool_timeout': 30,
        'pool_recycle': 1800,  # Recycle connections after 30 minutes
        'pool_pre_ping': True,  # Check connection viability before using
        'connect_args': connect_args
    }
    
    # Create engine with retry logic
    max_retries = 3
    retry_delay = 2  # seconds
    
    for attempt in range(max_retries):
        try:
            engine = create_async_engine(
                database_url,
                **engine_args
            )
            logger.info(f"Successfully created database engine on attempt {attempt + 1}")
            return engine
        except SQLAlchemyError as e:
            if attempt < max_retries - 1:
                logger.warning(f"Database connection failed (attempt {attempt + 1}/{max_retries}): {e}")
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                logger.error(f"Failed to establish database connection after {max_retries} attempts: {e}")
                raise"""
    
    # Update init_models function to include better error handling and retry logic
    init_models_pattern = r"async def init_models\(engine\):\s+[^\"]*\"\"\"[^\"]*\"\"\"\s+(.*?)(\s+return metadata)"
    
    init_models_replacement = r"""async def init_models(engine):
    \"\"\"Initialize database models with proper error handling and retry logic.\"\"\"
    import time
    import asyncio
    from sqlalchemy.exc import SQLAlchemyError
    
    logger.info("Initializing database models...")
    metadata = Base.metadata
    
    max_retries = 3
    retry_delay = 2  # seconds
    
    for attempt in range(max_retries):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(metadata.create_all)
            
            logger.info("Database models initialized successfully")
            
            # Initialize default data if needed
            is_fresh_db = await is_empty_database(engine)
            if is_fresh_db:
                logger.info("Fresh database detected, initializing default data...")
                await init_default_data(engine)
                logger.info("Default data initialized successfully")
            
            # Verify connection by running a simple query
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                logger.info("Database connection verified")
            
            return metadata
            
        except asyncio.exceptions.CancelledError as e:
            logger.error(f"Connection cancelled (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                logger.error(f"Database initialization failed after {max_retries} attempts due to: {e}")
                if IS_RAILWAY:
                    logger.error("Database initialization failed in production environment!")
                    raise  # Re-raise in production
                else:
                    logger.warning("Continuing without proper database initialization in development environment")
                    return metadata
                    
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy error (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                logger.error(f"Database initialization failed after {max_retries} attempts due to SQLAlchemy error: {e}")
                if IS_RAILWAY:
                    logger.error("Database initialization failed in production environment!")
                    raise  # Re-raise in production
                else:
                    logger.warning("Continuing without proper database initialization in development environment")
                    return metadata
                    
        except Exception as e:
            logger.error(f"Unexpected error (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                logger.error(f"Database initialization failed after {max_retries} attempts due to: {e}")
                if IS_RAILWAY:
                    logger.error("Database initialization failed in production environment!")
                    raise  # Re-raise in production
                else:
                    logger.warning("Continuing without proper database initialization in development environment")
                    return metadata"""
    
    # Apply the updates
    content = re.sub(get_engine_pattern, get_engine_replacement, content, flags=re.DOTALL)
    content = re.sub(init_models_pattern, init_models_replacement, content, flags=re.DOTALL)
    
    # Write the updated content
    with open(DB_BASE_PATH, 'w') as file:
        file.write(content)
    
    print(f"Updated {DB_BASE_PATH} with improved database connection logic")
    return True

def fix_communicator_middlewares():
    """Fix database middleware in the communicator bot"""
    if not os.path.exists(COMMUNICATOR_MIDDLEWARES_PATH):
        print(f"Error: {COMMUNICATOR_MIDDLEWARES_PATH} not found!")
        return False
    
    # Create backup
    if not create_backup(COMMUNICATOR_MIDDLEWARES_PATH):
        print("Failed to create backup, aborting to be safe.")
        return False
    
    # Read the file
    with open(COMMUNICATOR_MIDDLEWARES_PATH, 'r') as file:
        content = file.read()
    
    # Update the DatabaseMiddleware class to include better error handling
    db_middleware_pattern = r"class DatabaseMiddleware\(BaseMiddleware\):(.*?)def __call__\((.*?)\):(.*?)(return await handler\(event, data\))"
    
    db_middleware_replacement = r"""class DatabaseMiddleware(BaseMiddleware):
    \"\"\"Middleware for handling database connections with proper error handling and timeouts.\"\"\"
    
    def __init__(self):
        self.session_pool = {}
        self.retry_attempts = 3
        self.session_timeout = 30  # seconds
        logger.info("Database middleware initialized with retry logic")
        super().__init__()
    
    async def __call__\2:
        import time
        import asyncio
        from sqlalchemy.exc import SQLAlchemyError
        
        # Create a new session for this request with retry logic
        session = None
        engine = None
        
        # Store original exception if we need to re-raise later
        original_exc = None
        
        for attempt in range(self.retry_attempts):
            try:
                # Get or create engine with proper error handling
                try:
                    engine = get_async_engine()
                except Exception as e:
                    logger.error(f"Failed to create database engine: {e}")
                    raise
                
                # Create session with timeout
                async_session = sessionmaker(
                    engine, expire_on_commit=False, class_=AsyncSession
                )
                
                # Create session with timeout protection
                try:
                    session_task = asyncio.create_task(async_session())
                    session = await asyncio.wait_for(session_task, timeout=self.session_timeout)
                    
                    # Add session to the data dict
                    data["session"] = session
                    
                    # Process handler
                    result = await handler(event, data)
                    
                    # Close session
                    await session.close()
                    return result
                    
                except asyncio.TimeoutError:
                    logger.error(f"Session creation timed out after {self.session_timeout}s (attempt {attempt+1}/{self.retry_attempts})")
                    if session:
                        await session.close()
                    raise
                    
            except asyncio.exceptions.CancelledError as e:
                logger.warning(f"Database connection cancelled (attempt {attempt+1}/{self.retry_attempts}): {e}")
                original_exc = e
                if attempt < self.retry_attempts - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                    
            except SQLAlchemyError as e:
                logger.error(f"Database error (attempt {attempt+1}/{self.retry_attempts}): {e}")
                original_exc = e
                if attempt < self.retry_attempts - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                    
            except Exception as e:
                logger.error(f"Unexpected error in database middleware (attempt {attempt+1}/{self.retry_attempts}): {e}")
                original_exc = e
                if attempt < self.retry_attempts - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                    
        # All retries failed
        logger.critical(f"All database connection attempts failed after {self.retry_attempts} retries")
        
        # In production, we should handle this gracefully for the user
        try:
            if isinstance(event, types.Message) and event.text == "/start":
                # Special handling for /start command to avoid bad user experience
                await event.answer(
                    "I'm currently experiencing technical difficulties connecting to the database. "
                    "Please try again in a few minutes."
                )
            return None  # Return None to indicate middleware handled the response
        except Exception as e:
            logger.error(f"Failed to send error message to user: {e}")
            
        # Re-raise the original exception
        if original_exc:
            raise original_exc
        raise RuntimeError("Failed to establish database connection")"""
    
    # Apply the updates
    content = re.sub(db_middleware_pattern, db_middleware_replacement, content, flags=re.DOTALL)
    
    # Write the updated content
    with open(COMMUNICATOR_MIDDLEWARES_PATH, 'w') as file:
        file.write(content)
    
    print(f"Updated {COMMUNICATOR_MIDDLEWARES_PATH} with improved database middleware")
    return True

if __name__ == "__main__":
    print("Starting database connection fixes...")
    success = True
    
    # Fix db/base.py
    if not fix_db_base():
        success = False
        print("Failed to fix database base module")
    
    # Fix communicator middlewares
    if not fix_communicator_middlewares():
        success = False
        print("Failed to fix communicator middlewares")
    
    if success:
        print("Database connection fixes completed successfully!")
        print("Please commit and deploy these changes to fix the database connection issues.")
    else:
        print("Some fixes failed. Please check the errors above.") 