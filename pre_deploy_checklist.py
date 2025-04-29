#!/usr/bin/env python3
"""
Pre-deployment checklist for Allkinds Team Bot.

This script guides you through a series of checks before deploying
to ensure that your code is ready for production.
"""

import os
import sys
import time
import subprocess
from datetime import datetime
from typing import List, Dict, Any, Callable

# ANSI color codes for console output
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
BLUE = '\033[94m'
ENDC = '\033[0m'
BOLD = '\033[1m'

def print_header(title: str) -> None:
    """Print a formatted header."""
    print(f"\n{BLUE}{BOLD}{'=' * 80}{ENDC}")
    print(f"{BLUE}{BOLD}{title.center(80)}{ENDC}")
    print(f"{BLUE}{BOLD}{'=' * 80}{ENDC}\n")

def print_step(step: str, number: int, total: int) -> None:
    """Print a formatted step."""
    print(f"\n{YELLOW}{BOLD}[{number}/{total}] {step}{ENDC}")

def print_success(message: str) -> None:
    """Print a success message."""
    print(f"{GREEN}✓ {message}{ENDC}")

def print_warning(message: str) -> None:
    """Print a warning message."""
    print(f"{YELLOW}⚠ {message}{ENDC}")

def print_error(message: str) -> None:
    """Print an error message."""
    print(f"{RED}✗ {message}{ENDC}")

def run_command(command: str) -> tuple:
    """Run a shell command and return (success, output)."""
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            check=False,
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        return (result.returncode == 0, result.stdout + result.stderr)
    except Exception as e:
        return (False, str(e))

def confirm(prompt: str) -> bool:
    """Ask for confirmation."""
    response = input(f"{YELLOW}{prompt} (y/n): {ENDC}").lower()
    return response.startswith('y')

def check_code_integrity() -> bool:
    """Run code integrity checks."""
    print_step("Running code integrity verification", 1, 7)
    
    if os.path.exists("./verify_integrity.py"):
        success, output = run_command("python3 ./verify_integrity.py")
        print(output)
        
        if success:
            print_success("Code integrity check completed")
            return True
        else:
            print_error("Code integrity check failed")
            return confirm("Do you want to continue despite the code integrity issues?")
    else:
        print_warning("verify_integrity.py not found, skipping check")
        return True

def check_git_status() -> bool:
    """Check git status for uncommitted changes."""
    print_step("Checking Git status", 2, 7)
    
    success, output = run_command("git status --porcelain")
    
    if not success:
        print_error("Failed to get Git status")
        return confirm("Do you want to continue without checking Git status?")
    
    if output.strip():
        print_warning("You have uncommitted changes:")
        print(output)
        return confirm("Do you want to continue with uncommitted changes?")
    else:
        print_success("No uncommitted changes found")
        return True

def run_tests() -> bool:
    """Run tests to ensure everything is working."""
    print_step("Running tests", 3, 7)
    
    if os.path.exists("./tests"):
        print("Running pytest...")
        success, output = run_command("python -m pytest -v")
        print(output)
        
        if success:
            print_success("All tests passed")
            return True
        else:
            print_error("Some tests failed")
            return confirm("Do you want to continue despite the test failures?")
    else:
        print_warning("No tests directory found, skipping tests")
        return True

def check_environment() -> bool:
    """Check environment variables."""
    print_step("Checking environment variables", 4, 7)
    
    required_vars = [
        "TELEGRAM_BOT_TOKEN",
        "COMMUNICATOR_BOT_TOKEN",
        "DATABASE_URL",
        "WEBHOOK_DOMAIN",
        "COMMUNICATOR_BOT_USERNAME"
    ]
    
    success = True
    for var in required_vars:
        if not os.environ.get(var):
            if os.path.exists(".env"):
                # Check if it's in the .env file
                with open(".env", "r") as f:
                    env_content = f.read()
                    if f"{var}=" in env_content:
                        print_success(f"Environment variable {var} found in .env file")
                        continue
            
            print_warning(f"Environment variable {var} not set")
            success = False
    
    if success:
        print_success("All required environment variables are set")
        return True
    else:
        return confirm("Do you want to continue with missing environment variables?")

def create_deployment_note() -> bool:
    """Create a deployment note with details about this deployment."""
    print_step("Creating deployment note", 5, 7)
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Get git info
    _, git_branch = run_command("git rev-parse --abbrev-ref HEAD")
    _, git_commit = run_command("git rev-parse HEAD")
    _, git_message = run_command("git log -1 --pretty=%B")
    
    deployment_note = f"""
DEPLOYMENT NOTE
==============
Date: {timestamp}
Branch: {git_branch.strip()}
Commit: {git_commit.strip()}
Commit Message: {git_message.strip()}

Environment:
- WEBHOOK_DOMAIN: {os.environ.get('WEBHOOK_DOMAIN', 'Not set')}
- DATABASE_URL: {'Set' if os.environ.get('DATABASE_URL') else 'Not set'}

Changes in this deployment:
[Fill in the major changes here]

Pre-deployment checks completed by: {os.environ.get('USER', 'Unknown')}
"""
    
    with open("LAST_DEPLOYMENT.md", "w") as f:
        f.write(deployment_note)
    
    print_success("Deployment note created at LAST_DEPLOYMENT.md")
    print_warning("Please update the 'Changes in this deployment' section before continuing")
    
    editor = os.environ.get('EDITOR', 'nano')
    success, _ = run_command(f"{editor} LAST_DEPLOYMENT.md")
    
    return success

def backup_database() -> bool:
    """Backup the database before deployment."""
    print_step("Creating database backup", 6, 7)
    
    if "DATABASE_URL" not in os.environ and not os.path.exists(".env"):
        print_warning("DATABASE_URL not set and no .env file found, skipping backup")
        return True
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"allkinds_backup_{timestamp}.dump"
    
    if os.path.exists("./backup_railway_db.sh"):
        print("Using backup_railway_db.sh script...")
        success, output = run_command(f"./backup_railway_db.sh {backup_filename}")
    else:
        print("Using pg_dump directly...")
        # Fall back to pg_dump
        success, output = run_command(f"pg_dump $DATABASE_URL > {backup_filename}")
    
    print(output)
    
    if success:
        print_success(f"Database backup created at {backup_filename}")
        return True
    else:
        print_error("Database backup failed")
        return confirm("Do you want to continue without a database backup?")

def confirm_deployment() -> bool:
    """Final confirmation before deployment."""
    print_step("Deployment confirmation", 7, 7)
    
    print(f"{BOLD}You are about to deploy to production.{ENDC}")
    print("This will affect LIVE users of the Allkinds Team Bot.")
    
    if not confirm("Are you SURE you want to deploy now?"):
        return False
    
    if not confirm("Did you review all the warnings and errors above?"):
        return False
    
    return True

def main() -> None:
    """Run the pre-deployment checklist."""
    print_header("ALLKINDS TEAM BOT PRE-DEPLOYMENT CHECKLIST")
    
    print(f"{BOLD}This script will guide you through pre-deployment checks to ensure your code is ready for production.{ENDC}")
    
    # Load environment variables from .env file
    if os.path.exists(".env"):
        try:
            from dotenv import load_dotenv
            load_dotenv()
            print_success(".env file loaded")
        except ImportError:
            print_warning("python-dotenv not installed, skipping .env loading")
    
    # Define the checklist steps
    steps = [
        check_code_integrity,
        check_git_status,
        run_tests,
        check_environment,
        create_deployment_note,
        backup_database,
        confirm_deployment
    ]
    
    # Run the steps
    for step in steps:
        if not step():
            print_error("Pre-deployment checklist failed. Deployment aborted.")
            sys.exit(1)
    
    print_header("PRE-DEPLOYMENT CHECKLIST COMPLETE")
    print_success("All checks passed. You're ready to deploy!")
    print("\nTo deploy, run the following command:")
    print(f"{BOLD}railway up{ENDC}")
    
    print("\nAfter deployment, don't forget to:")
    print("1. Check the webhook configuration")
    print("2. Test the bot functionality")
    print("3. Monitor the logs for any errors")

if __name__ == "__main__":
    main() 