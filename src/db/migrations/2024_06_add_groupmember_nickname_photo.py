import asyncio
import sqlite3
import sys
import logging
from pathlib import Path

# Add the root directory to the path
sys.path.append('.')

from src.db.base import SQLALCHEMY_DATABASE_URL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Extract the SQLite database path from the URL
DB_PATH = SQLALCHEMY_DATABASE_URL.replace("sqlite+aiosqlite:///", "")

async def migrate():
    """Add nickname and photo_file_id columns to the group_members table."""
    logger.info(f"Starting migration: Add nickname and photo_file_id columns to group_members table")
    logger.info(f"Database path: {DB_PATH}")
    
    try:
        # Connect to the database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check if the columns already exist
        cursor.execute("PRAGMA table_info(group_members)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        # Add nickname column if it doesn't exist
        if "nickname" not in column_names:
            logger.info("Adding 'nickname' column to group_members table")
            cursor.execute("ALTER TABLE group_members ADD COLUMN nickname VARCHAR(32)")
        else:
            logger.info("Column 'nickname' already exists in group_members table")
        
        # Add photo_file_id column if it doesn't exist
        if "photo_file_id" not in column_names:
            logger.info("Adding 'photo_file_id' column to group_members table")
            cursor.execute("ALTER TABLE group_members ADD COLUMN photo_file_id VARCHAR(255)")
        else:
            logger.info("Column 'photo_file_id' already exists in group_members table")
        
        # Commit the changes
        conn.commit()
        logger.info("Migration completed successfully")
        
        # Close the connection
        conn.close()
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(migrate()) 