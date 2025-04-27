#!/usr/bin/env python3
import sys
import os
import re
from sqlalchemy import create_engine, text

def drop_production_data():
    """
    Drop data from the production PostgreSQL database on Railway.
    This script will truncate all relevant tables while preserving the schema.
    """
    # Get database URL from environment
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL environment variable is not set.")
        print("Make sure you're running this script with the Railway environment variables.")
        return False
    
    # Make sure it's a PostgreSQL URL
    if not db_url.startswith("postgres"):
        print(f"ERROR: DATABASE_URL must be a PostgreSQL URL, got: {db_url[:10]}...")
        return False
    
    # Convert to standard PostgreSQL URL without async prefix if needed
    if db_url.startswith("postgresql+asyncpg"):
        db_url = db_url.replace("postgresql+asyncpg", "postgresql")
    
    # Confirm with a warning
    print("⚠️ WARNING ⚠️")
    print("This script will delete ALL DATA from the following tables in the production database:")
    print("  - group_members")
    print("  - groups")
    print("  - questions")
    print("  - answers")
    print("  - matches")
    print("User data will be preserved.")
    
    # Ask for confirmation
    if "FORCE_CONFIRM" not in os.environ:
        confirmation = input("Type 'DELETE ALL DATA' to confirm: ")
        if confirmation != "DELETE ALL DATA":
            print("Operation cancelled.")
            return False
    
    try:
        # Create engine and connection
        print(f"Connecting to database...")
        # Ensure we have psycopg2 installed
        try:
            import psycopg2
            print("Using psycopg2 driver")
        except ImportError:
            print("WARNING: psycopg2 not found, trying to install...")
            import subprocess
            subprocess.check_call([sys.executable, "-m", "pip", "install", "psycopg2-binary"])
            import psycopg2
            print("psycopg2-binary installed successfully")
            
        engine = create_engine(db_url)
        
        with engine.connect() as connection:
            # Start transaction
            print("Starting transaction...")
            trans = connection.begin()
            
            # List of tables to truncate in order (respecting foreign keys)
            tables = [
                "answers",
                "questions",
                "matches",
                "group_members",
                "groups"
            ]
            
            print("Truncating tables...")
            for table in tables:
                try:
                    # Use TRUNCATE with CASCADE to handle foreign keys
                    connection.execute(text(f"TRUNCATE TABLE {table} CASCADE;"))
                    print(f"✓ Truncated table: {table}")
                except Exception as e:
                    print(f"Error truncating {table}: {e}")
                    trans.rollback()
                    print("Transaction rolled back.")
                    return False
            
            # Commit the transaction
            print("Committing changes...")
            trans.commit()
            
            print("✅ All data has been successfully deleted while preserving the schema.")
            print("The application can now start with a fresh database.")
            return True
            
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    result = drop_production_data()
    sys.exit(0 if result else 1) 