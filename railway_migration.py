#!/usr/bin/env python3
import os
import sys
import subprocess
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Get the absolute path to the project directory
project_dir = Path(__file__).parent
sys.path.append(str(project_dir))

def run_railway_command(args, capture_output=True):
    """Run a Railway CLI command with the specified arguments"""
    cmd = ["railway"] + args
    logger.info(f"Running Railway command: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=capture_output, text=True)
        return result.stdout if capture_output else None
    except subprocess.CalledProcessError as e:
        logger.error(f"Railway command failed: {e}")
        if capture_output and e.stderr:
            logger.error(f"stderr: {e.stderr}")
        return None

def run_migration():
    """Apply the migration to add group_id column to matches table"""
    logger.info("Running direct migration to add group_id column to matches table")
    
    # First check if the Postgres service is accessible by trying a simple railway link command
    logger.info("Checking Railway project and services...")
    link_result = run_railway_command(["link"])
    if not link_result:
        logger.error("Failed to link Railway project. Make sure you're logged in with 'railway login'")
        return False
    
    # Let's try to run our migration directly
    logger.info("Applying migration: Add group_id column to matches table...")
    
    # Run the migration file
    migration_file = project_dir / "src" / "db" / "migrations" / "add_group_id_to_matches.py"
    if migration_file.exists():
        logger.info(f"Running migration file: {migration_file}")
        try:
            # Execute the migration via railway run
            result = run_railway_command(["run", "-s", "Postgres", "python", str(migration_file)], capture_output=False)
            
            logger.info("Migration completed successfully")
            return True
        except Exception as e:
            logger.error(f"Error running migration: {e}")
            return False
    else:
        logger.error(f"Migration file not found: {migration_file}")
        return False

if __name__ == "__main__":
    logger.info("Starting Railway migration process")
    success = run_migration()
    if success:
        logger.info("✅ Railway migration completed successfully")
        sys.exit(0)
    else:
        logger.error("❌ Railway migration failed")
        sys.exit(1) 