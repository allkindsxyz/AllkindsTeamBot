#!/usr/bin/env python3
import logging
import sqlite3
import os
import sys
import subprocess
from pathlib import Path
import importlib.util

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Get the absolute path to the project directory
project_dir = Path(__file__).resolve().parent
sys.path.append(str(project_dir))

# Check if we're in a PostgreSQL environment (Railway) or SQLite (local)
DATABASE_URL = os.getenv("DATABASE_URL")
IS_POSTGRES = DATABASE_URL and DATABASE_URL.startswith("postgres")

# Try to import psycopg2 for PostgreSQL
if IS_POSTGRES:
    try:
        import psycopg2
        from urllib.parse import urlparse
        logger.info("PostgreSQL mode detected. Using psycopg2 for database operations.")
    except ImportError:
        logger.error("PostgreSQL URL detected but psycopg2 package is missing! Please install it with: pip install psycopg2-binary")
        sys.exit(1)
else:
    # SQLite paths
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
        logger.error("SQLite database file not found!")
        sys.exit(1)
    
    logger.info(f"Using SQLite database at: {db_path}")

def get_db_connection():
    """Get database connection based on environment"""
    if IS_POSTGRES:
        # Parse the PostgreSQL URL
        result = urlparse(DATABASE_URL)
        username = result.username
        password = result.password
        database = result.path[1:]
        hostname = result.hostname
        port = result.port
        
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
        # Fallback to SQLite for local dev
        return sqlite3.connect(str(db_path)), "sqlite"

def check_table_exists(conn, db_type, table_name):
    """Check if a table exists in the database"""
    cursor = conn.cursor()
    
    if db_type == "postgres":
        cursor.execute(f"SELECT to_regclass('public.{table_name}')")
        result = cursor.fetchone()[0]
        return result is not None
    else:
        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
        result = cursor.fetchone()
        return result is not None

def verify_database_tables():
    """Verify all required tables exist"""
    try:
        conn, db_type = get_db_connection()
        cursor = conn.cursor()
        
        tables_to_check = [
            'users', 
            'matches', 
            'anonymous_chat_sessions', 
            'chat_messages'
        ]
        
        missing_tables = []
        
        for table in tables_to_check:
            exists = check_table_exists(conn, db_type, table)
            if not exists:
                missing_tables.append(table)
        
        conn.close()
        
        if missing_tables:
            logger.warning(f"Missing tables: {', '.join(missing_tables)}")
            return False
        
        logger.info("All required tables exist!")
        return True
        
    except Exception as e:
        logger.error(f"Error verifying tables: {e}")
        return False

def create_anonymous_chat_sessions_table():
    """Create anonymous_chat_sessions table if it doesn't exist"""
    try:
        # Get the appropriate connection
        conn, db_type = get_db_connection()
        cursor = conn.cursor()
        
        # Check if the table exists
        if check_table_exists(conn, db_type, "anonymous_chat_sessions"):
            logger.info("Table 'anonymous_chat_sessions' already exists. Skipping creation.")
            conn.close()
            return True
        
        # Check if prerequisite tables exist
        for table in ["users", "matches"]:
            if not check_table_exists(conn, db_type, table):
                logger.error(f"Table '{table}' does not exist! Please create it first.")
                conn.close()
                return False
        
        # Create the table with appropriate syntax
        if db_type == "postgres":
            # PostgreSQL syntax
            cursor.execute("""
            CREATE TABLE anonymous_chat_sessions (
                id SERIAL PRIMARY KEY,
                session_id VARCHAR(64) UNIQUE NOT NULL,
                initiator_id INTEGER NOT NULL,
                recipient_id INTEGER NOT NULL,
                match_id INTEGER NOT NULL,
                status VARCHAR(20) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ended_at TIMESTAMP NULL,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (initiator_id) REFERENCES users(id),
                FOREIGN KEY (recipient_id) REFERENCES users(id),
                FOREIGN KEY (match_id) REFERENCES matches(id)
            )
            """)
            
            # Create indices
            cursor.execute("CREATE INDEX idx_anonymous_chat_sessions_session_id ON anonymous_chat_sessions(session_id)")
            cursor.execute("CREATE INDEX idx_anonymous_chat_sessions_initiator_id ON anonymous_chat_sessions(initiator_id)")
            cursor.execute("CREATE INDEX idx_anonymous_chat_sessions_recipient_id ON anonymous_chat_sessions(recipient_id)")
            cursor.execute("CREATE INDEX idx_anonymous_chat_sessions_match_id ON anonymous_chat_sessions(match_id)")
        else:
            # SQLite syntax
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
            
            # Create indices
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
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"Database error occurred when creating anonymous_chat_sessions: {e}")
        return False

def create_chat_messages_table():
    """Create chat_messages table if it doesn't exist"""
    try:
        # Get the appropriate connection
        conn, db_type = get_db_connection()
        cursor = conn.cursor()
        
        # Check if the table exists
        if check_table_exists(conn, db_type, "chat_messages"):
            logger.info("Table 'chat_messages' already exists. Skipping creation.")
            conn.close()
            return True
        
        # Check if prerequisite tables exist
        for table in ["anonymous_chat_sessions", "users"]:
            if not check_table_exists(conn, db_type, table):
                logger.error(f"Table '{table}' does not exist! Please create it first.")
                conn.close()
                return False
        
        # Create the table with appropriate syntax
        if db_type == "postgres":
            # PostgreSQL syntax
            cursor.execute("""
            CREATE TABLE chat_messages (
                id SERIAL PRIMARY KEY,
                chat_session_id INTEGER NOT NULL,
                sender_id INTEGER NOT NULL,
                content_type VARCHAR(20) NOT NULL,
                text_content TEXT,
                file_id VARCHAR(255),
                is_read BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chat_session_id) REFERENCES anonymous_chat_sessions(id),
                FOREIGN KEY (sender_id) REFERENCES users(id)
            )
            """)
            
            # Create indices
            cursor.execute("CREATE INDEX idx_chat_messages_chat_session_id ON chat_messages(chat_session_id)")
            cursor.execute("CREATE INDEX idx_chat_messages_sender_id ON chat_messages(sender_id)")
        else:
            # SQLite syntax
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
            
            # Create indices
            cursor.execute('''
            CREATE INDEX idx_chat_messages_chat_session_id ON chat_messages(chat_session_id)
            ''')
            
            cursor.execute('''
            CREATE INDEX idx_chat_messages_sender_id ON chat_messages(sender_id)
            ''')
            
        conn.commit()
        logger.info("Successfully created 'chat_messages' table!")
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"Database error occurred when creating chat_messages: {e}")
        return False

def run_migrations():
    """Run all migrations needed for the communicator bot"""
    # First verify if tables already exist
    if verify_database_tables():
        logger.info("All required tables already exist. No migrations needed.")
        return True
    
    # Otherwise run migrations
    sessions_created = create_anonymous_chat_sessions_table()
    if not sessions_created:
        logger.error("Failed to create anonymous_chat_sessions table. Aborting.")
        return False
    
    messages_created = create_chat_messages_table()
    if not messages_created:
        logger.error("Failed to create chat_messages table. Aborting.")
        return False
    
    logger.info("All migrations completed successfully!")
    return True

if __name__ == "__main__":
    # Install psycopg2 if needed and not available
    if IS_POSTGRES and importlib.util.find_spec("psycopg2") is None:
        try:
            logger.info("Installing required PostgreSQL package (psycopg2-binary)...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "psycopg2-binary"])
            # Re-import after installation
            import psycopg2
        except Exception as e:
            logger.error(f"Failed to install psycopg2-binary: {e}")
            print("❌ Failed to install required dependency")
            sys.exit(1)
    
    success = run_migrations()
    if success:
        print("✅ Database migrations completed successfully")
        sys.exit(0)
    else:
        print("❌ Database migrations failed")
        sys.exit(1) 