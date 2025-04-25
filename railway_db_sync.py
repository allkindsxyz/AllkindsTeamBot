#!/usr/bin/env python3
import logging
import os
import sys
from urllib.parse import urlparse
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Get the absolute path to the project directory
project_dir = Path(__file__).parent
sys.path.append(str(project_dir))

# Check if we're in a PostgreSQL environment (Railway)
DATABASE_URL = os.getenv("DATABASE_URL")
IS_POSTGRES = DATABASE_URL and DATABASE_URL.startswith("postgres")

if not IS_POSTGRES:
    logger.error("This script is intended for use with PostgreSQL on Railway")
    sys.exit(1)

def get_db_connection():
    """Get database connection to PostgreSQL"""
    import psycopg2
    try:
        # First try connecting with the DATABASE_URL directly
        logger.info("Connecting to PostgreSQL with DATABASE_URL")
        conn = psycopg2.connect(DATABASE_URL)
        return conn
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
        return conn

def check_table_exists(cursor, table_name):
    """Check if a table exists in the database"""
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = %s
        )
    """, (table_name,))
    return cursor.fetchone()[0]

def check_column_exists(cursor, table_name, column_name):
    """Check if a column exists in a table"""
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns 
            WHERE table_schema = 'public' 
            AND table_name = %s 
            AND column_name = %s
        )
    """, (table_name, column_name))
    return cursor.fetchone()[0]

def get_all_tables(cursor):
    """Get all tables in the database"""
    cursor.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
    """)
    return [row[0] for row in cursor.fetchall()]

def get_table_columns(cursor, table_name):
    """Get all columns in a table with their types"""
    cursor.execute("""
        SELECT column_name, data_type, character_maximum_length, is_nullable
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = %s
    """, (table_name,))
    return {row[0]: {"type": row[1], "max_length": row[2], "nullable": row[3]} for row in cursor.fetchall()}

def inspect_database():
    """Inspect the PostgreSQL database and log its structure"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get all tables
        tables = get_all_tables(cursor)
        logger.info(f"Found {len(tables)} tables: {', '.join(tables)}")
        
        # For each table, get its columns
        for table in tables:
            columns = get_table_columns(cursor, table)
            logger.info(f"Table '{table}' has {len(columns)} columns:")
            for col_name, col_info in columns.items():
                logger.info(f"  - {col_name}: {col_info['type']}" + 
                           (f"({col_info['max_length']})" if col_info['max_length'] else "") + 
                           (", NULL" if col_info['nullable'] == 'YES' else ", NOT NULL"))
        
        conn.close()
        return tables
        
    except Exception as e:
        logger.error(f"Error inspecting database: {e}")
        sys.exit(1)

def run_all_migrations():
    """Run all the migration scripts in the correct order"""
    from src.db.migrations import add_group_id_to_matches
    
    # Run the migrations one by one, in correct order
    success = add_group_id_to_matches.add_group_id_to_matches()
    
    if success:
        logger.info("All migrations completed successfully")
    else:
        logger.error("Failed to apply migrations")
        sys.exit(1)

if __name__ == "__main__":
    logger.info("Starting database inspection and migration")
    
    # First, inspect the current structure
    tables = inspect_database()
    
    # Then apply migrations as needed
    logger.info("Applying migrations to update schema")
    run_all_migrations()
    
    # Verify changes after migrations
    logger.info("Verifying database after migrations")
    inspect_database()
    
    logger.info("Migration process completed successfully") 