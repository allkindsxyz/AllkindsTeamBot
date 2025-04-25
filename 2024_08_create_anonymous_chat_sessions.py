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
    """Add anonymous_chat_sessions table to the database"""
    try:
        # Connect to the SQLite database
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Check if the table already exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='anonymous_chat_sessions'")
        if cursor.fetchone():
            logger.info("Table 'anonymous_chat_sessions' already exists. Skipping creation.")
            conn.close()
            return
        
        # Check if prerequisite tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if not cursor.fetchone():
            logger.error("Table 'users' does not exist! Please create it first.")
            conn.close()
            return
            
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='matches'")
        if not cursor.fetchone():
            logger.error("Table 'matches' does not exist! Please create it first.")
            conn.close()
            return
        
        # Create the anonymous_chat_sessions table
        cursor.execute('''
        CREATE TABLE anonymous_chat_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id VARCHAR(64) UNIQUE NOT NULL,
            initiator_id INTEGER NOT NULL,
            recipient_id INTEGER NOT NULL,
            match_id INTEGER NOT NULL,
            status VARCHAR(20) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ended_at TIMESTAMP,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (initiator_id) REFERENCES users(id),
            FOREIGN KEY (recipient_id) REFERENCES users(id),
            FOREIGN KEY (match_id) REFERENCES matches(id)
        )
        ''')
        
        # Create indices for performance
        cursor.execute('''
        CREATE INDEX idx_anonymous_chat_sessions_session_id ON anonymous_chat_sessions(session_id)
        ''')
        
        cursor.execute('''
        CREATE INDEX idx_anonymous_chat_sessions_initiator_id ON anonymous_chat_sessions(initiator_id)
        ''')
        
        cursor.execute('''
        CREATE INDEX idx_anonymous_chat_sessions_recipient_id ON anonymous_chat_sessions(recipient_id)
        ''')
        
        cursor.execute('''
        CREATE INDEX idx_anonymous_chat_sessions_match_id ON anonymous_chat_sessions(match_id)
        ''')
        
        conn.commit()
        logger.info("Successfully created 'anonymous_chat_sessions' table!")
        
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