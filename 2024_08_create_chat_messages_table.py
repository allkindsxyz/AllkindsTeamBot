#!/usr/bin/env python3
import logging
import sqlite3
import os
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Get the absolute path to the project directory
project_dir = Path(__file__).resolve().parent
sys.path.append(str(project_dir))

# Database path (look for both potential locations)
db_paths = [
    project_dir / "allkinds.db",
    project_dir / "data" / "allkinds.db"
]

db_path = None
for path in db_paths:
    if path.exists():
        db_path = path
        break

if not db_path:
    logger.error("Database file not found!")
    sys.exit(1)

logger.info(f"Using database at: {db_path}")

async def run_migration():
    """Add chat_messages table to the database"""
    try:
        # Connect to the SQLite database
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Check if the table already exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chat_messages'")
        if cursor.fetchone():
            logger.info("Table 'chat_messages' already exists. Skipping creation.")
            conn.close()
            return
        
        # Check if prerequisite tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='anonymous_chat_sessions'")
        if not cursor.fetchone():
            logger.error("Table 'anonymous_chat_sessions' does not exist! Please create it first.")
            conn.close()
            return
            
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if not cursor.fetchone():
            logger.error("Table 'users' does not exist! Please create it first.")
            conn.close()
            return
        
        # Create the chat_messages table
        cursor.execute('''
        CREATE TABLE chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_session_id INTEGER NOT NULL,
            sender_id INTEGER NOT NULL,
            content_type VARCHAR(20) NOT NULL,
            text_content TEXT,
            file_id VARCHAR(255),
            is_read BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chat_session_id) REFERENCES anonymous_chat_sessions(id),
            FOREIGN KEY (sender_id) REFERENCES users(id)
        )
        ''')
        
        # Create indices for performance
        cursor.execute('''
        CREATE INDEX idx_chat_messages_chat_session_id ON chat_messages(chat_session_id)
        ''')
        
        cursor.execute('''
        CREATE INDEX idx_chat_messages_sender_id ON chat_messages(sender_id)
        ''')
        
        conn.commit()
        logger.info("Successfully created 'chat_messages' table!")
        
    except sqlite3.Error as e:
        logger.error(f"Database error occurred: {e}")
    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_migration())
    logger.info("Migration completed") 