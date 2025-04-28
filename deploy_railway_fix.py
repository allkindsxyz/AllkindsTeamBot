#!/usr/bin/env python3
"""
Script to deploy fixes to Railway
This script will:
1. Check if Railway CLI is installed and logged in
2. Set the environment variables for the communicator bot on Railway
3. Deploy the changes to Railway
"""

import os
import sys
import subprocess
import time
import json

# Define the correct bot username and token
CORRECT_BOT_USERNAME = "AllkindsChat"
CORRECT_BOT_TOKEN = "8018043989:AAGXTjJ5EZ1JjAhZLwd700W_FmRmyDD-AzQ"

def run_command(command, check=True):
    """Run a shell command and return the output."""
    print(f"Running: {command}")
    result = subprocess.run(command, shell=True, text=True, capture_output=True)
    if check and result.returncode != 0:
        print(f"Command failed with exit code {result.returncode}")
        print(f"Error: {result.stderr}")
        sys.exit(1)
    return result.stdout.strip()

def check_railway_cli():
    """Check if Railway CLI is installed and logged in."""
    print("Checking if Railway CLI is installed...")
    try:
        output = run_command("railway --version", check=False)
        if "command not found" in output:
            print("Railway CLI not found. Please install it first:")
            print("npm i -g @railway/cli")
            sys.exit(1)
        print(f"Railway CLI found: {output}")
    except Exception as e:
        print(f"Error checking Railway CLI: {e}")
        print("Please install Railway CLI: npm i -g @railway/cli")
        sys.exit(1)
    
    print("Checking if logged in to Railway...")
    try:
        output = run_command("railway whoami", check=False)
        if "not logged in" in output.lower():
            print("Not logged in to Railway. Please run 'railway login' first.")
            sys.exit(1)
        print(f"Logged in as: {output}")
    except Exception as e:
        print(f"Error checking Railway login: {e}")
        sys.exit(1)

def set_railway_variables():
    """Set the environment variables on Railway."""
    print("\nSetting environment variables on Railway...")
    try:
        # Set the communicator bot username
        run_command(f'railway variables set COMMUNICATOR_BOT_USERNAME="{CORRECT_BOT_USERNAME}"')
        print(f"✅ Set COMMUNICATOR_BOT_USERNAME to {CORRECT_BOT_USERNAME}")
        
        # Set the communicator bot token
        run_command(f'railway variables set COMMUNICATOR_BOT_TOKEN="{CORRECT_BOT_TOKEN}"')
        print("✅ Set COMMUNICATOR_BOT_TOKEN to the correct production token")
    except Exception as e:
        print(f"Error setting environment variables: {e}")
        sys.exit(1)

def deploy_to_railway():
    """Deploy the changes to Railway."""
    print("\nDeploying changes to Railway...")
    try:
        # Link to the existing project if not already linked
        run_command("railway link", check=False)
        
        # Deploy the changes
        run_command("railway up")
        print("✅ Deployment initiated")
        
        # Wait a moment for deployment to start
        print("Waiting for deployment to start...")
        time.sleep(10)
        
        # Monitor the deployment status
        print("Checking deployment status...")
        status_output = run_command("railway status --json")
        try:
            status_data = json.loads(status_output)
            deployment_id = status_data["deployments"][0]["id"]
            deployment_status = status_data["deployments"][0]["status"]
            print(f"Deployment ID: {deployment_id}")
            print(f"Initial status: {deployment_status}")
            
            # Poll for deployment status
            while deployment_status in ["BUILDING", "DEPLOYING"]:
                print(f"Deployment in progress: {deployment_status}")
                time.sleep(15)  # Wait before checking again
                status_output = run_command("railway status --json")
                status_data = json.loads(status_output)
                
                # Find the deployment with matching ID
                for deployment in status_data["deployments"]:
                    if deployment["id"] == deployment_id:
                        deployment_status = deployment["status"]
                        break
            
            print(f"Final deployment status: {deployment_status}")
            
            if deployment_status == "SUCCESS":
                print("✅ Deployment successful!")
            else:
                print(f"⚠️ Deployment ended with status: {deployment_status}")
                print("Check logs for more details: railway logs")
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Error parsing deployment status: {e}")
            print("Please check deployment status manually with: railway status")
    except Exception as e:
        print(f"Error deploying to Railway: {e}")
        sys.exit(1)

def main():
    print("=== Railway Deployment Script ===")
    
    # Check if Railway CLI is installed and logged in
    check_railway_cli()
    
    # Ask for confirmation before proceeding
    print("\nThis script will:")
    print(f"1. Set COMMUNICATOR_BOT_USERNAME to {CORRECT_BOT_USERNAME}")
    print("2. Set COMMUNICATOR_BOT_TOKEN to the correct production token")
    print("3. Deploy the changes to Railway")
    
    confirm = input("\nDo you want to proceed? (y/n): ").lower()
    if confirm != 'y':
        print("Aborted.")
        sys.exit(0)
    
    # Set environment variables
    set_railway_variables()
    
    # Deploy to Railway
    deploy_to_railway()
    
    print("\n=== Deployment Complete ===")
    print("Monitor the logs to ensure everything is working: railway logs")
    print("Check the webhook status: railway run python check_webhook.py")

if __name__ == "__main__":
    main() 