#!/usr/bin/env python3
"""
Script to generate manual commands for deploying fixes to Railway
This script simply outputs the commands you should run instead of executing them
"""

import os

FILES_TO_COMMIT = [
    "src/db/base.py",
    "src/db/init_db.py",
    "src/communicator_bot/middlewares.py",
    "src/db/init_communicator_db.py",
    "src/db/utils/session_management.py"
]

def check_files_exist():
    """Check if all files to commit exist."""
    missing_files = []
    for file in FILES_TO_COMMIT:
        if not os.path.exists(file):
            missing_files.append(file)
    
    return missing_files

def main():
    """Generate commands for manual deployment."""
    print("=== Manual Railway Deployment Guide ===")
    
    # Check files
    missing_files = check_files_exist()
    if missing_files:
        print("\n⚠️ Warning: The following files don't exist:")
        for file in missing_files:
            print(f"  - {file}")
        print("Please check the file paths.")
    
    # Git commands
    print("\n=== Step 1: Commit Changes ===")
    print("Run the following commands:")
    
    # Add specific files
    print("\n# Add the modified files")
    for file in FILES_TO_COMMIT:
        if file not in missing_files:
            print(f"git add {file}")
    
    # Commit
    print("\n# Commit the changes")
    print('git commit -m "Fix database connection settings and server_settings format for Railway"')
    
    # Push
    print("\n=== Step 2: Push to Repository ===")
    print("git push")
    
    # Deploy
    print("\n=== Step 3: Deploy to Railway ===")
    print("# Link to your Railway project if needed")
    print("railway link")
    print("\n# Deploy")
    print("railway up")
    
    # Verify
    print("\n=== Step 4: Verify Deployment ===")
    print("# Check status")
    print("railway status")
    print("\n# Monitor logs")
    print("railway logs")
    
    print("\n=== Troubleshooting ===")
    print("If you encounter any issues:")
    print("1. Verify the server_settings format in all database files")
    print("2. Check Railway logs for errors")
    print("3. Restart the bots in Railway dashboard if needed")
    
    print("\nRemember that your deployment will only take effect after pushing to the repository and running 'railway up'.")

if __name__ == "__main__":
    main() 