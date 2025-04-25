import sqlite3
import os
import sys
from loguru import logger

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Database file path
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "allkinds.db")

def run_migration():
    """Adds category column to the questions table."""
    logger.info(f"Using database at: {DB_PATH}")
    
    try:
        # Connect to the database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check if the column already exists
        cursor.execute("PRAGMA table_info(questions)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        if "category" not in column_names:
            logger.info("Adding 'category' column to questions table")
            cursor.execute("ALTER TABLE questions ADD COLUMN category VARCHAR(50) DEFAULT 'other'")
            conn.commit()
            logger.info("Migration completed successfully")
        else:
            logger.info("Column 'category' already exists in questions table")
            
        conn.close()
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise

if __name__ == "__main__":
    run_migration() 