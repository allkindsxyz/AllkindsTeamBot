#!/usr/bin/env python3
import asyncio
import sys
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

async def drop_production_data():
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
        # Create engine and session
        print(f"Connecting to database...")
        engine = create_async_engine(db_url)
        async_session = sessionmaker(
            engine, expire_on_commit=False, class_=AsyncSession
        )
        
        async with async_session() as session:
            # Start transaction
            print("Starting transaction...")
            
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
                    await session.execute(text(f"TRUNCATE TABLE {table} CASCADE;"))
                    print(f"✓ Truncated table: {table}")
                except Exception as e:
                    print(f"Error truncating {table}: {e}")
                    return False
            
            # Commit the transaction
            print("Committing changes...")
            await session.commit()
            
            print("✅ All data has been successfully deleted while preserving the schema.")
            print("The application can now start with a fresh database.")
            
            # Close connections
            await engine.dispose()
            return True
            
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    result = asyncio.run(drop_production_data())
    sys.exit(0 if result else 1) 