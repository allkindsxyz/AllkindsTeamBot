#!/usr/bin/env python3
import os
import sys
import argparse
import subprocess
import logging
from pathlib import Path
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Get the absolute path to the project directory
project_dir = Path(__file__).parent

def run_railway_command(command, service="Postgres", environment="production"):
    """Run a command on Railway with the specified service and environment"""
    full_command = f"railway run -s {service} --environment {environment} \"{command}\""
    logger.info(f"Running Railway command: {full_command}")
    
    try:
        result = subprocess.run(full_command, shell=True, check=True, 
                              capture_output=True, text=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        logger.error(f"Railway command failed: {e}")
        logger.error(f"stderr: {e.stderr}")
        raise e

def inspect_database():
    """Inspect the PostgreSQL database and return its structure"""
    logger.info("Inspecting database schema...")
    
    # Get all tables
    tables_cmd = "echo \"SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'\" | psql $DATABASE_URL -t"
    tables_output = run_railway_command(tables_cmd)
    tables = [t.strip() for t in tables_output.splitlines() if t.strip()]
    
    logger.info(f"Found {len(tables)} tables: {', '.join(tables)}")
    
    # Get schema for each table
    for table in tables:
        columns_cmd = f"echo \"SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_schema = 'public' AND table_name = '{table}'\" | psql $DATABASE_URL -t"
        columns_output = run_railway_command(columns_cmd)
        columns = [c.strip() for c in columns_output.splitlines() if c.strip()]
        
        logger.info(f"Table '{table}' structure:")
        for column in columns:
            logger.info(f"  - {column}")
    
    return tables

def create_database_backup():
    """Create a backup of the PostgreSQL database"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"allkinds_backup_{timestamp}.dump"
    
    logger.info(f"Creating database backup to {backup_file}...")
    
    # Using pg_dump via psql to create a backup
    backup_cmd = f"pg_dump $DATABASE_URL --format=custom --no-owner --no-acl > /tmp/backup.dump && cat /tmp/backup.dump"
    
    try:
        # We need to use subprocess directly instead of run_railway_command to capture binary output
        full_command = f"railway run -s Postgres --environment production \"{backup_cmd}\""
        logger.info(f"Running backup command")
        
        with open(backup_file, "wb") as f:
            subprocess.run(full_command, shell=True, check=True, stdout=f)
        
        file_size = Path(backup_file).stat().st_size
        logger.info(f"Backup created successfully: {backup_file} ({file_size/1024/1024:.2f} MB)")
        return backup_file
    except Exception as e:
        logger.error(f"Backup failed: {e}")
        return None

def apply_migrations():
    """Run migrations on the Railway database"""
    logger.info("Applying migrations to the database...")
    
    # List of SQL commands to run for migration
    migrations = [
        "ALTER TABLE matches ADD COLUMN IF NOT EXISTS group_id INTEGER REFERENCES groups(id)"
    ]
    
    for i, migration in enumerate(migrations, 1):
        logger.info(f"Running migration {i}/{len(migrations)}")
        migration_cmd = f"echo \"{migration};\" | psql $DATABASE_URL"
        
        try:
            output = run_railway_command(migration_cmd)
            logger.info(f"Migration {i} completed successfully")
        except Exception as e:
            logger.error(f"Migration {i} failed: {e}")
            return False
    
    logger.info("All migrations completed successfully")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Railway Database Tools')
    parser.add_argument('--backup', action='store_true', help='Create a database backup')
    parser.add_argument('--inspect', action='store_true', help='Inspect database schema')
    parser.add_argument('--migrate', action='store_true', help='Apply migrations')
    
    args = parser.parse_args()
    
    if args.backup:
        create_database_backup()
    elif args.inspect:
        inspect_database()
    elif args.migrate:
        apply_migrations()
    else:
        # If no specific action is provided, run all
        logger.info("Running full database maintenance process")
        backup_file = create_database_backup()
        if backup_file:
            logger.info(f"Backup created: {backup_file}")
        
        tables = inspect_database()
        logger.info(f"Database has {len(tables)} tables")
        
        success = apply_migrations()
        if success:
            logger.info("Migrations applied successfully")
        
        # Verify changes
        logger.info("Verifying database after migrations")
        inspect_database() 