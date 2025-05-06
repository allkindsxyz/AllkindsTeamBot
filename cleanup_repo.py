#!/usr/bin/env python3
"""
Cleanup Repository Script

This script removes temporary files, backups, and unnecessary files from the repository
to keep the codebase clean after fixing the 'load_answered_questions' issue.
"""

import os
import re
import shutil
import logging
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("cleanup_report.log")
    ]
)
logger = logging.getLogger(__name__)

# Files and patterns to remove
TEMP_EXTENSIONS = [
    ".bak", ".bak_*", ".old", ".tmp", ".backup", 
    ".clean", ".clean2", ".fixed", ".new"
]

# Fix scripts that are no longer needed (now that we have the stable version)
TEMP_FIX_SCRIPTS = [
    "fix_debug.py", 
    "fix_indentation.py", 
    "fix_awaits.py", 
    "register_callback.py",
    "fix_decorator.py",
    "direct_patch.py", 
    "cleanup_start_file.py",
    "diagnose_telegram_conflict.py",
    "direct_patch.py",
    "fix_try_except.sh",
    "force_kill_all_bots.sh",
    "fixed_function.txt"
]

# Keep the main unified fix as documentation
KEEP_SCRIPTS = [
    "unified_fix.py",
    "direct_fix.py"
]

# Scripts directory to organize remaining scripts
SCRIPTS_DIR = "scripts/fixes"

def find_temp_files():
    """Find all temporary files in the repository"""
    temp_files = []
    
    # Walk through all directories
    for root, dirs, files in os.walk("."):
        # Skip .git directory
        if ".git" in root:
            continue
            
        # Skip node_modules if it exists
        if "node_modules" in root:
            continue
            
        # Check each file
        for file in files:
            file_path = os.path.join(root, file)
            
            # Check if it's a temporary file by extension
            for ext in TEMP_EXTENSIONS:
                if ext.endswith("*"):
                    # Handle wildcard extensions
                    pattern = ext.replace("*", ".*")
                    if re.search(pattern, file):
                        temp_files.append(file_path)
                        break
                elif file.endswith(ext):
                    temp_files.append(file_path)
                    break
            
            # Check for temporary scripts
            if file in TEMP_FIX_SCRIPTS and file_path not in temp_files:
                temp_files.append(file_path)
    
    return temp_files

def organize_scripts():
    """Organize remaining useful scripts into scripts directory"""
    logger.info("Organizing scripts into the scripts directory...")
    
    # Create scripts directory if it doesn't exist
    os.makedirs(SCRIPTS_DIR, exist_ok=True)
    
    # Move important scripts to the scripts directory
    organized = 0
    for script in KEEP_SCRIPTS:
        if os.path.exists(script) and not script.startswith("scripts/"):
            target_path = os.path.join(SCRIPTS_DIR, script)
            
            # Create directories if needed
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            
            # Copy the file to scripts directory
            logger.info(f"Moving {script} to {target_path}")
            shutil.copy2(script, target_path)
            organized += 1
    
    return organized

def remove_temp_files(temp_files, dry_run=False):
    """Remove temporary files"""
    removed = 0
    
    for file_path in temp_files:
        if os.path.exists(file_path):
            if dry_run:
                logger.info(f"Would remove: {file_path}")
            else:
                try:
                    os.remove(file_path)
                    logger.info(f"Removed: {file_path}")
                    removed += 1
                except Exception as e:
                    logger.error(f"Failed to remove {file_path}: {e}")
    
    return removed

def main(dry_run=False):
    """Execute the cleanup"""
    logger.info("Starting repository cleanup...")
    
    # Find temporary files
    temp_files = find_temp_files()
    logger.info(f"Found {len(temp_files)} temporary files")
    
    # Print files to be removed
    for file in temp_files:
        logger.info(f"Will remove: {file}")
    
    # Prompt for confirmation if not in dry run mode
    if not dry_run:
        confirm = input(f"Remove {len(temp_files)} temporary files? (y/n): ")
        if confirm.lower() != 'y':
            logger.info("Operation cancelled")
            return False
    
    # Remove temporary files
    removed = remove_temp_files(temp_files, dry_run)
    logger.info(f"Removed {removed} temporary files")
    
    # Organize scripts
    organized = organize_scripts()
    logger.info(f"Organized {organized} scripts")
    
    return True

if __name__ == "__main__":
    # Check for dry run flag
    if len(sys.argv) > 1 and sys.argv[1] == "--dry-run":
        main(dry_run=True)
    else:
        main() 