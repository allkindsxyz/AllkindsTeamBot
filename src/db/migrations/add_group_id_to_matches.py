#!/usr/bin/env python3
import logging
import os
import sys
from urllib.parse import urlparse
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get the absolute path to the project directory
project_dir = Path(__file__).parent.parent.parent.parent
sys.path.append(str(project_dir))

# Check if we're in a PostgreSQL environment (Railway) or SQLite (local)
DATABASE_URL = os.getenv("DATABASE_URL")
IS_POSTGRES = DATABASE_URL and DATABASE_URL.startswith("postgres")

def get_db_connection():
    """Get database connection based on environment"""
    if IS_POSTGRES:
        # Connect using the full DATABASE_URL for better compatibility with Railway CLI
        import psycopg2
        try:
            # First try connecting with the DATABASE_URL directly
            logger.info("Connecting to PostgreSQL with DATABASE_URL")
            conn = psycopg2.connect(DATABASE_URL)
            return conn, "postgres"
        except Exception as e:
            logger.warning(f"Failed to connect with DATABASE_URL: {e}")
            # Fall back to parsed components
            result = urlparse(DATABASE_URL)
            username = result.username
            password = result.password
            database = result.path[1:]
            hostname = result.hostname
            port = result.port
            
            logger.info(f"Trying connection with parsed parameters - host: {hostname}, port: {port}, database: {database}")
            # Connect to PostgreSQL
            conn = psycopg2.connect(
                database=database,
                user=username,
                password=password,
                host=hostname,
                port=port
            )
            return conn, "postgres"
    else:
        # For SQLite, group_id already exists in the schema, so no need to run this
        import sqlite3
        db_path = project_dir / "allkinds.db"
        return sqlite3.connect(str(db_path)), "sqlite"

def add_group_id_to_matches():
    """Add the group_id column to the matches table if it doesn't exist."""
    logger.info("Starting migration: Adding group_id column to matches table")
    
    try:
        # Connect to the database
        conn, db_type = get_db_connection()
        cursor = conn.cursor()
        
        if db_type == "postgres":
            # Check if the column exists in PostgreSQL
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='matches' AND column_name='group_id'
            """)
            column_exists = cursor.fetchone()
            
            if column_exists:
                logger.info("group_id column already exists in matches table")
                conn.close()
                return True
            
            # Add the column
            logger.info("Adding group_id column to matches table")
            try:
                cursor.execute("""
                    ALTER TABLE matches 
                    ADD COLUMN group_id INTEGER REFERENCES groups(id)
                """)
                conn.commit()
                logger.info("group_id column added successfully to matches table")
            except Exception as e:
                logger.error(f"Error adding group_id column: {e}")
                conn.rollback()
                return False
        else:
            # SQLite - column should already exist
            logger.info("Using SQLite, matches table should already have group_id column")
            pass
            
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"Error in migration: {e}")
        return False

if __name__ == "__main__":
    # Only run for PostgreSQL
    if IS_POSTGRES:
        success = add_group_id_to_matches()
        if success:
            print("✅ Migration completed successfully: group_id column added to matches table")
            sys.exit(0)
        else:
            print("❌ Migration failed")
            sys.exit(1)
    else:
        print("ℹ️ SQLite already has group_id column in matches table, no migration needed")
        sys.exit(0) 