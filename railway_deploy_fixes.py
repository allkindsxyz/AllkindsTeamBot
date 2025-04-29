#!/usr/bin/env python3
"""
Script to deploy all fixes to Railway
This script will:
1. Commit all the changes
2. Push to the repository
3. Deploy to Railway
"""

import os
import sys
import subprocess
import time

FILES_TO_COMMIT = [
    "src/db/base.py",
    "src/db/init_db.py",
    "src/communicator_bot/middlewares.py",
    "src/db/init_communicator_db.py",
    "src/db/utils/session_management.py"
]

def run_command(command, check=True):
    """Run a shell command and return the output."""
    print(f"Running: {command}")
    result = subprocess.run(command, shell=True, text=True, capture_output=True)
    if check and result.returncode != 0:
        print(f"Command failed with exit code {result.returncode}")
        print(f"Error: {result.stderr}")
        sys.exit(1)
    print(result.stdout)
    return result.stdout.strip()

def deploy_to_railway():
    """Deploy all fixes to Railway."""
    print("=== Railway Deployment Script ===")
    
    # 1. Check for uncommitted changes
    print("\nChecking git status...")
    git_status = run_command("git status -s", check=False)
    
    if not git_status:
        print("No changes to commit.")
        choice = input("Do you want to force deployment to Railway anyway? (y/n): ")
        if choice.lower() != 'y':
            print("Aborted.")
            return
    else:
        print("Found the following changes:")
        print(git_status)
        
        # 2. Confirm changes to commit
        choice = input("Do you want to commit these changes? (y/n): ")
        if choice.lower() != 'y':
            print("Aborted.")
            return
        
        # 3. Add files
        print("\nAdding files to git...")
        for file in FILES_TO_COMMIT:
            if os.path.exists(file):
                run_command(f"git add {file}")
        
        # 4. Commit
        print("\nCommitting changes...")
        commit_message = "Fix database connection settings and server_settings format for Railway"
        run_command(f'git commit -m "{commit_message}"')
    
    # 5. Push to repository
    print("\nPushing to repository...")
    push_choice = input("Do you want to push the changes to the repository? (y/n): ")
    if push_choice.lower() == 'y':
        run_command("git push")
    
    # 6. Deploy to Railway
    print("\nDeploying to Railway...")
    deploy_choice = input("Do you want to deploy to Railway now? (y/n): ")
    if deploy_choice.lower() == 'y':
        # Check if Railway CLI is installed
        try:
            railway_version = run_command("railway version", check=False)
            if "command not found" in railway_version:
                print("Railway CLI not found. Please install it first:")
                print("npm i -g @railway/cli")
                return
        except Exception:
            print("Railway CLI not found. Please install it first:")
            print("npm i -g @railway/cli")
            return
        
        # Check if logged in
        try:
            railway_whoami = run_command("railway whoami", check=False)
            if "not logged in" in railway_whoami.lower():
                print("Not logged in to Railway. Please run 'railway login' first.")
                return
        except Exception:
            print("Error checking Railway login. Please run 'railway login' first.")
            return
        
        # Link project if needed
        run_command("railway link", check=False)
        
        # Deploy
        print("\nDeploying to Railway... This may take a few minutes.")
        run_command("railway up")
        
        print("\n✅ Deployment initiated!")
        print("You can check the status with: railway status")
        print("And view logs with: railway logs")
    
    print("\n=== Deployment Process Complete ===")
    print("Summary of actions:")
    if git_status and choice.lower() == 'y':
        print("✓ Changes committed")
    if push_choice.lower() == 'y':
        print("✓ Changes pushed to repository")
    if deploy_choice.lower() == 'y':
        print("✓ Deployment to Railway initiated")
    print("\nRemember to monitor the deployment and check that both bots are working correctly.")

if __name__ == "__main__":
    deploy_to_railway() 