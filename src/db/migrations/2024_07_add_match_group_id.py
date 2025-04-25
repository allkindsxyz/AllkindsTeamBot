import asyncio
import logging
import os
from pathlib import Path
from datetime import datetime

import aiosqlite

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database file path - get the absolute path to the project root
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DB_PATH = os.path.join(PROJECT_ROOT, "allkinds.db")


async def add_match_group_id():
    """Add the group_id column to the matches table."""
    logger.info(f"Starting migration: Adding group_id to matches table using DB at {DB_PATH}")
    
    try:
        # Connect to the database
        async with aiosqlite.connect(DB_PATH) as db:
            # Get the cursor
            cursor = await db.cursor()
            
            # Check if the table exists
            await cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='matches'")
            table_exists = await cursor.fetchone()
            
            if not table_exists:
                logger.error("The matches table does not exist in the database")
                return
            
            # Check if the column already exists
            await cursor.execute("PRAGMA table_info(matches)")
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]
            
            if "group_id" in column_names:
                logger.info("group_id column already exists in matches table")
                return
            
            # Add the group_id column with a default value of 1 (assuming group 1 exists)
            logger.info("Adding group_id column to matches table")
            await cursor.execute("ALTER TABLE matches ADD COLUMN group_id INTEGER DEFAULT 1 REFERENCES groups(id)")
            
            # Commit the changes
            await db.commit()
            logger.info("group_id column added successfully to matches table")
            
    except Exception as e:
        logger.error(f"Error adding group_id column to matches table: {e}")
        raise


if __name__ == "__main__":
    # Run the migration
    asyncio.run(add_match_group_id()) 