#!/usr/bin/env python3
import subprocess
import sys
import os
import psycopg2
import time

print("Running migration to add group_id column to matches table...")

# Only run in PostgreSQL environment
if os.getenv("DATABASE_URL") and os.getenv("DATABASE_URL").startswith("postgres"):
    # Wait for database to be ready by checking if matches table exists
    db_url = os.getenv("DATABASE_URL")
    
    def check_table_exists():
        try:
            # Connect to database
            conn = psycopg2.connect(db_url)
            cursor = conn.cursor()
            
            # Check if matches table exists
            cursor.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'matches')")
            exists = cursor.fetchone()[0]
            
            cursor.close()
            conn.close()
            
            return exists
        except Exception as e:
            print(f"Error checking if table exists: {e}")
            return False
    
    # Check with timeout and retry
    max_retries = 5
    for attempt in range(max_retries):
        if check_table_exists():
            print("Found 'matches' table, proceeding with migration...")
            break
        else:
            print(f"Matches table not found (attempt {attempt+1}/{max_retries}). Waiting before retry...")
            time.sleep(5)  # Wait 5 seconds between retries
    else:
        print("Couldn't find 'matches' table after retries. Exiting without migration.")
        sys.exit(0)
    
    # Run the migration if matches table exists
    try:
        result = subprocess.run(
            [sys.executable, "src/db/migrations/add_group_id_to_matches.py"],
            check=True,
            capture_output=True,
            text=True
        )
        print(result.stdout)
        if result.stderr:
            print(f"Warnings: {result.stderr}")
        sys.exit(0)
    except subprocess.CalledProcessError as e:
        print(f"Migration failed: {e.stderr}")
        sys.exit(1)
else:
    print("Not running in PostgreSQL environment, skipping migration")
    sys.exit(0) 