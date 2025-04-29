#!/usr/bin/env python3
"""
Simple Railway deployment script
This script pushes changes to git and deploys to Railway
"""

import subprocess
import sys

def run_command(command):
    """Run a command and print its output."""
    print(f"Running: {command}")
    try:
        result = subprocess.run(command, shell=True, text=True, check=True, capture_output=True)
        print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Command failed with exit code {e.returncode}")
        print(f"Error: {e.stderr}")
        return False

def main():
    """Deploy to Railway."""
    print("=== Simple Railway Deployment ===")
    
    # Check Railway CLI
    print("\nChecking Railway CLI...")
    if not run_command("railway --version"):
        print("❌ Railway CLI not found. Please install it with: npm i -g @railway/cli")
        return
    
    # Check login
    print("\nChecking Railway login...")
    if not run_command("railway whoami"):
        print("❌ Not logged in to Railway. Please run: railway login")
        return
    
    # Link the project
    print("\nLinking project...")
    run_command("railway link")
    
    # Push local changes to remote repo
    print("\nPushing changes to git...")
    should_push = input("Do you want to push changes to git first? (y/n): ").lower() == 'y'
    if should_push:
        if not run_command("git push"):
            print("❌ Failed to push changes to git.")
            if input("Continue with deployment anyway? (y/n): ").lower() != 'y':
                return
    
    # Deploy to Railway
    print("\nDeploying to Railway...")
    if not run_command("railway up"):
        print("❌ Deployment failed. Please check the logs above.")
        return
    
    print("\n✅ Deployment initiated successfully!")
    print("\nNext steps:")
    print("1. Monitor deployment status: railway status")
    print("2. View logs: railway logs")
    print("3. Check the bot by sending /start")

if __name__ == "__main__":
    main() 