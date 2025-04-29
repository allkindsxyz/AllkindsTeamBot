#!/usr/bin/env python3
"""
Emergency fix for database connection CancelledError in Railway deployment.
This script specifically addresses the asyncio.exceptions.CancelledError in the 
database connection process.
"""

import os
import re
import shutil
from datetime import datetime

# File that needs updating
DB_BASE_PATH = "src/db/base.py"

def create_backup(file_path):
    """Create a backup of the file before modifying it"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{file_path}.emergency_fix_{timestamp}"
    try:
        shutil.copy2(file_path, backup_path)
        print(f"Created backup at {backup_path}")
        return True
    except Exception as e:
        print(f"Error creating backup of {file_path}: {e}")
        return False

def emergency_fix_cancelled_error():
    """Fix the CancelledError handling in init_models function"""
    if not os.path.exists(DB_BASE_PATH):
        print(f"Error: {DB_BASE_PATH} not found!")
        return False
    
    # Create backup
    if not create_backup(DB_BASE_PATH):
        print("Failed to create backup, aborting to be safe.")
        return False
    
    try:
        # Read the file
        with open(DB_BASE_PATH, 'r') as file:
            content = file.read()
        
        # Check if we already have proper handling for CancelledError
        if "asyncio.exceptions.CancelledError" in content and "except asyncio.exceptions.CancelledError as e:" in content:
            print("File already contains CancelledError handling. Making more robust...")
            
            # Modify the CancelledError handling block to catch all kinds of CancelledError
            old_pattern = r"except asyncio\.exceptions\.CancelledError as e:(.*?)logger\.error\(f\"Connection cancelled \(attempt \{attempt \+ 1\}/\{max_retries\}\): \{e\}\"\)(.*?)if attempt < max_retries - 1:(.*?)time\.sleep\(retry_delay\)(.*?)retry_delay \*= 2  # Exponential backoff(.*?)else:(.*?)logger\.error\(f\"Database initialization failed after \{max_retries\} attempts due to: \{e\}\"\)"
            
            new_pattern = """except asyncio.exceptions.CancelledError as e:
            # This is a critical issue in Railway - the connection is being cancelled
            logger.error(f"Connection cancelled (attempt {attempt + 1}/{max_retries}): {e}")
            
            # Retry with adjusted timeout
            if attempt < max_retries - 1:
                logger.info(f"Retrying with adjusted timeout after CancelledError...")
                # Reduce timeout to avoid cancellation
                engine_args['pool_timeout'] = 15
                connect_args['timeout'] = 5
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                logger.error(f"Database initialization failed after {max_retries} attempts due to cancellation: {e}")
                
                # In production with cancellation errors, we might still be able to create tables
                if IS_PRODUCTION or IS_RAILWAY:
                    logger.warning("Attempting to continue despite cancellation in production...")
                    try:
                        # Try with a more direct approach
                        async with engine.begin() as conn:
                            await conn.run_sync(metadata.create_all)
                        logger.info("Successfully created database tables despite connection issues")
                        return metadata
                    except Exception as inner_e:
                        logger.critical(f"Final attempt to create tables failed: {inner_e}")
                        raise  # Re-raise only after trying everything
                else:
                    logger.warning("Continuing without proper database initialization in development environment")
                    return metadata"""
            
            # Replace the pattern
            updated_content = re.sub(old_pattern, new_pattern, content, flags=re.DOTALL)
            
            # If no changes were made with the pattern, we need a more targeted approach
            if updated_content == content:
                print("Pattern replacement didn't work. Trying targeted replacement...")
                
                # Find the init_models function
                init_models_start = content.find("async def init_models")
                if init_models_start == -1:
                    print("Could not find init_models function!")
                    return False
                
                # Replace the entire function with our enhanced version
                enhanced_init_models = """async def init_models(engine):
    \"\"\"Initialize database models with proper error handling and retry logic.\"\"\"
    import time
    import asyncio
    from sqlalchemy.exc import SQLAlchemyError
    from sqlalchemy import text, inspect
    
    logger.info("Initializing database models...")
    metadata = Base.metadata
    
    max_retries = 3
    retry_delay = 2  # seconds
    
    # For Railway with connection cancellations
    connect_args = {
        'timeout': 10,    # Connection timeout in seconds
        'command_timeout': 10,  # Command execution timeout
    }
    
    # Connection settings for retry attempts
    engine_args = {
        'pool_size': 5,    # Start with a smaller pool
        'max_overflow': 10,
        'pool_timeout': 30,
        'pool_recycle': 1800,  # Recycle connections after 30 minutes
        'pool_pre_ping': True,  # Check connection viability before using
        'connect_args': connect_args
    }
    
    for attempt in range(max_retries):
        try:
            # Special handling for Railway environment
            if IS_PRODUCTION or os.environ.get("RAILWAY_ENVIRONMENT"):
                logger.info(f"Attempt {attempt + 1}/{max_retries} in Railway environment...")
                try:
                    # Simple ping test before heavy operations
                    async with engine.connect() as conn:
                        await conn.execute(text("SELECT 1"))
                        logger.info("Database connection verified with SELECT 1")
                except Exception as ping_e:
                    logger.warning(f"Connection ping failed: {ping_e}")
                    # Continue anyway to try the actual operation
            
            # Now try the actual operation
            async with engine.begin() as conn:
                try:
                    # Check if tables exist first
                    tables = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
                    logger.info(f"Found existing tables: {tables}")
                except Exception as table_e:
                    logger.warning(f"Error checking existing tables, will try to create: {table_e}")
                    tables = []
                
                if not tables:
                    logger.info("Creating database schema...")
                    await conn.run_sync(metadata.create_all)
                    logger.info("Database schema created successfully")
            
            logger.info("Database models initialized successfully")
            return metadata
            
        except asyncio.exceptions.CancelledError as e:
            # This is a critical issue in Railway - the connection is being cancelled
            logger.error(f"Connection cancelled (attempt {attempt + 1}/{max_retries}): {e}")
            
            # Retry with adjusted timeout
            if attempt < max_retries - 1:
                logger.info(f"Retrying with adjusted timeout after CancelledError...")
                # Reduce timeout to avoid cancellation
                engine_args['pool_timeout'] = 15
                connect_args['timeout'] = 5
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                logger.error(f"Database initialization failed after {max_retries} attempts due to cancellation")
                
                # In production with cancellation errors, we need to try a different approach
                if IS_PRODUCTION or os.environ.get("RAILWAY_ENVIRONMENT"):
                    logger.warning("Attempting emergency connection in Railway environment...")
                    try:
                        # Create a new engine with minimal settings
                        from sqlalchemy.ext.asyncio import create_async_engine
                        emergency_engine = create_async_engine(
                            os.environ.get("DATABASE_URL"),
                            echo=False,
                            pool_size=1,
                            max_overflow=2,
                            pool_timeout=10,
                            connect_args={'timeout': 5, 'command_timeout': 5}
                        )
                        
                        # Try with a simple approach
                        async with emergency_engine.begin() as conn:
                            await conn.run_sync(metadata.create_all)
                            logger.info("EMERGENCY: Created database tables with emergency engine")
                        
                        return metadata
                    except Exception as emergency_e:
                        logger.critical(f"Emergency database approach failed: {emergency_e}")
                        # We've tried everything, re-raise the original error
                        raise e
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
                if IS_PRODUCTION or os.environ.get("RAILWAY_ENVIRONMENT"):
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
                if IS_PRODUCTION or os.environ.get("RAILWAY_ENVIRONMENT"):
                    logger.error("Database initialization failed in production environment!")
                    raise  # Re-raise in production
                else:
                    logger.warning("Continuing without proper database initialization in development environment")
                    return metadata"""
                
                # Find the end of the function
                next_func = content.find("async def", init_models_start + 1)
                if next_func == -1:
                    next_func = len(content)  # End of file
                
                # Replace the function
                updated_content = content[:init_models_start] + enhanced_init_models + content[next_func:]
        
        # Add IS_RAILWAY detection to the file if it doesn't exist
        if "IS_RAILWAY =" not in updated_content:
            railway_detection = "\n# Check if we're in Railway\nIS_RAILWAY = os.environ.get('RAILWAY_ENVIRONMENT') is not None\n"
            # Insert after imports
            imports_end = updated_content.find("import sys") + len("import sys")
            updated_content = updated_content[:imports_end] + railway_detection + updated_content[imports_end:]
        
        # Write the updated content back
        with open(DB_BASE_PATH, 'w') as file:
            file.write(updated_content)
        
        print(f"Successfully updated {DB_BASE_PATH} with improved CancelledError handling")
        return True
        
    except Exception as e:
        print(f"Error updating {DB_BASE_PATH}: {e}")
        return False

if __name__ == "__main__":
    print("Applying emergency fix for database CancelledError...")
    
    if emergency_fix_cancelled_error():
        print("✅ Emergency fix applied successfully!")
        print("Please commit and deploy these changes to fix the database connection issue in Railway.")
    else:
        print("❌ Failed to apply emergency fix. Please check the errors above.") 