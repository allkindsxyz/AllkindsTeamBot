#!/usr/bin/env python3
"""
Railway Setup Script for AllkindsTeamBot

This script prepares all necessary files for Railway deployment,
checks for common issues, and provides troubleshooting guidance.
"""

import os
import sys
import shutil
import platform
import subprocess
import logging
from pathlib import Path
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def check_prerequisites():
    """Check if all prerequisites are met for deployment."""
    logger.info("Checking prerequisites...")
    
    # Check Python version
    python_version = platform.python_version()
    logger.info(f"Python version: {python_version}")
    if tuple(map(int, python_version.split('.'))) < (3, 8):
        logger.error("Python version must be at least 3.8")
        return False
    
    # Check if git is installed
    try:
        subprocess.run(["git", "--version"], check=True, capture_output=True)
        logger.info("Git is installed")
    except (subprocess.SubprocessError, FileNotFoundError):
        logger.warning("Git is not installed or not in PATH. Git is recommended for deployment.")
    
    # Check if required files exist
    required_files = [
        "requirements.txt",
        "src/main.py",
        "src/communicator_bot/main.py",
        "src/core/config.py",
        "src/db/base.py"
    ]
    
    missing_files = []
    for file in required_files:
        if not os.path.exists(file):
            missing_files.append(file)
    
    if missing_files:
        logger.error(f"Missing required files: {', '.join(missing_files)}")
        return False
    
    logger.info("All prerequisites check passed")
    return True

def fix_common_issues():
    """Fix common issues that might prevent successful deployment."""
    logger.info("Fixing common issues...")
    
    # Check if required directories exist, create if not
    required_dirs = [
        "logs",
        "src/communicator_bot/handlers",
    ]
    
    for dir_path in required_dirs:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)
            logger.info(f"Created directory: {dir_path}")
    
    # Ensure main.py is importable as a module
    for module_dir in ["src", "src/communicator_bot"]:
        init_file = os.path.join(module_dir, "__init__.py")
        if not os.path.exists(init_file):
            with open(init_file, "w") as f:
                f.write("# Make this directory a Python package\n")
            logger.info(f"Created {init_file}")
    
    # Fix src/core/__init__.py
    core_init = "src/core/__init__.py"
    if not os.path.exists(core_init):
        with open(core_init, "w") as f:
            f.write("# Core module initialization\n")
        logger.info(f"Created {core_init}")
    
    # Fix health check endpoints for Railway
    health_check_code = '''
from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
async def health_check():
    """Health check endpoint for Railway."""
    return {"status": "ok", "service": "allkinds"}
'''
    
    health_files = {
        "src/api/health.py": health_check_code,
        "src/communicator_bot/health.py": health_check_code.replace("allkinds", "communicator")
    }
    
    for health_file, content in health_files.items():
        os.makedirs(os.path.dirname(health_file), exist_ok=True)
        with open(health_file, "w") as f:
            f.write(content)
        logger.info(f"Created health check file: {health_file}")
    
    logger.info("Common issues fixed")
    return True

def create_railway_specific_files():
    """Create Railway-specific files for deployment."""
    logger.info("Creating Railway-specific files...")
    
    # Create a simple startup script 
    startup_script = """#!/bin/bash
# Railway startup script

# Log the startup
echo "Starting AllkindsTeamBot services..."

# Give the system a moment to stabilize
sleep 3

# Start the main bot
python -m src.main &
MAIN_PID=$!
echo "Main bot started with PID $MAIN_PID"

# Start the communicator bot
python -m src.communicator_bot.main &
COMM_PID=$!
echo "Communicator bot started with PID $COMM_PID"

# Monitor the processes
monitor() {
  echo "Monitoring processes..."
  while true; do
    if ! kill -0 $MAIN_PID 2>/dev/null; then
      echo "Main bot process died, restarting..."
      python -m src.main &
      MAIN_PID=$!
    fi
    
    if ! kill -0 $COMM_PID 2>/dev/null; then
      echo "Communicator bot process died, restarting..."
      python -m src.communicator_bot.main &
      COMM_PID=$!
    fi
    
    sleep 10
  done
}

# Start the monitor in the background
monitor &
MONITOR_PID=$!

# Wait for all processes
wait
"""
    
    with open("railway_start.sh", "w") as f:
        f.write(startup_script)
    
    # Make it executable
    os.chmod("railway_start.sh", 0o755)
    logger.info("Created railway_start.sh")
    
    # Create a simple .gitignore if it doesn't exist
    if not os.path.exists(".gitignore"):
        gitignore_content = """
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
*.egg-info/
.installed.cfg
*.egg

# Environment variables
.env
.env.*
!.env.example

# Logs
logs/
*.log

# Database
*.db
*.sqlite
*.sqlite3

# Generated files
railway-*
*.railway_bak_*
*.comm_fix_bak_*
"""
        with open(".gitignore", "w") as f:
            f.write(gitignore_content)
        logger.info("Created .gitignore")
    
    # Create a basic troubleshooting guide
    troubleshooting_guide = """
# Railway Deployment Troubleshooting Guide

## Common Issues and Solutions

### 1. Database Connection Issues

If you see database connection errors in the logs:

- Check that DATABASE_URL is set correctly in Railway's environment variables
- Ensure PostgreSQL addon is properly attached to your project
- Try the following in Railway's shell:
  ```
  python -c "import asyncio, asyncpg; asyncio.run(asyncpg.connect(os.environ['DATABASE_URL']))"
  ```

### 2. Bot Token Verification Failed

If you see "Bot verification failed" in the logs:

- Verify BOT_TOKEN and COMMUNICATOR_BOT_TOKEN are set correctly
- Check that the bots are active in BotFather
- Try accessing the Telegram API directly in Railway's shell:
  ```
  curl -X POST https://api.telegram.org/bot$BOT_TOKEN/getMe
  ```

### 3. Webhook Conflict

If you see "Conflict: terminated by other getUpdates request" or webhook errors:

- The bot might be running in multiple instances or have a webhook set
- Run this in Railway's shell to clear webhooks:
  ```
  curl -X POST https://api.telegram.org/bot$BOT_TOKEN/deleteWebhook?drop_pending_updates=true
  ```

### 4. Port Binding Issues

If you see "Address already in use" errors:

- Change the PORT environment variable in Railway to a different value
- Ensure you're not binding to the same port multiple times

### 5. Memory or CPU Usage Issues

If the app keeps crashing or restarting:

- Check Railway usage metrics
- Consider optimizing your code or adjusting pool sizes in database configuration
- Add memory limits to Railway configuration

## Accessing Logs

To view detailed logs in Railway:

1. Go to your project in the Railway dashboard
2. Click on the "Deployments" tab
3. Select the current deployment
4. Click on "Logs" to see real-time logs

## Support

If you continue to experience issues, please:

1. Export the logs from Railway
2. Create an issue on the project repository with the logs attached
3. Include details of your deployment environment
"""
    
    with open("RAILWAY_TROUBLESHOOTING.md", "w") as f:
        f.write(troubleshooting_guide)
    logger.info("Created RAILWAY_TROUBLESHOOTING.md")
    
    logger.info("Railway-specific files created")
    return True

def check_env_variables():
    """Check and create necessary environment variable templates."""
    logger.info("Checking environment variables...")
    
    # Create .env.example if it doesn't exist
    env_example = ".env.example"
    env_example_content = """# Environment Variables for AllkindsTeamBot
# Required
BOT_TOKEN=your_main_bot_token_from_botfather
COMMUNICATOR_BOT_TOKEN=your_communicator_bot_token_from_botfather
DATABASE_URL=postgresql://username:password@hostname:port/database

# Optional with defaults
COMMUNICATOR_BOT_USERNAME=AllkindsCommunicatorBot
ADMIN_IDS=12345678,87654321
OPENAI_API_KEY=your_openai_api_key

# Railway specific (set automatically)
PORT=8080
"""
    
    with open(env_example, "w") as f:
        f.write(env_example_content)
    logger.info(f"Created {env_example}")
    
    # Create a simple script to export variables for debugging
    debug_script = """#!/bin/bash
# Script to check environment variables for Railway deployment

echo "Checking environment variables for Railway deployment..."

# Check for required variables
required_vars=("BOT_TOKEN" "COMMUNICATOR_BOT_TOKEN" "DATABASE_URL")
missing=()

for var in "${required_vars[@]}"; do
  if [ -z "${!var}" ]; then
    missing+=("$var")
    echo "❌ Missing required variable: $var"
  else
    echo "✅ $var is set (starts with: ${!var:0:3}...)"
  fi
done

# Check optional variables
optional_vars=("COMMUNICATOR_BOT_USERNAME" "ADMIN_IDS" "OPENAI_API_KEY")

for var in "${optional_vars[@]}"; do
  if [ -z "${!var}" ]; then
    echo "⚠️ Optional variable not set: $var"
  else
    echo "✅ $var is set"
  fi
done

if [ ${#missing[@]} -gt 0 ]; then
  echo ""
  echo "Error: ${#missing[@]} required variables are missing!"
  echo "Please set them in Railway's environment variables settings."
  exit 1
else
  echo ""
  echo "All required variables are set!"
fi
"""
    
    with open("check_env.sh", "w") as f:
        f.write(debug_script)
    os.chmod("check_env.sh", 0o755)
    logger.info("Created check_env.sh")
    
    return True

def test_setup():
    """Test the setup to make sure it works before deployment."""
    logger.info("Testing setup...")
    
    # Check if pytest is installed
    try:
        subprocess.run(["pytest", "--version"], check=True, capture_output=True)
        has_pytest = True
    except (subprocess.SubprocessError, FileNotFoundError):
        has_pytest = False
        logger.warning("Pytest not installed, skipping tests")
    
    if has_pytest:
        # Create a basic test file
        test_dir = "tests"
        os.makedirs(test_dir, exist_ok=True)
        
        with open(os.path.join(test_dir, "__init__.py"), "w") as f:
            f.write("# Test package\n")
        
        test_file = os.path.join(test_dir, "test_railway_setup.py")
        test_content = '''
import os
import sys
import importlib.util
import pytest

def test_imports():
    """Test that key modules can be imported."""
    try:
        # Add project root to path to make imports work
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
        
        # Try to import key modules
        from src.core import config
        assert hasattr(config, "get_settings"), "Missing get_settings function"
        
        # Check DB module
        from src.db import base
        assert hasattr(base, "get_session"), "Missing get_session function"
        
        # Check main modules exist
        assert os.path.exists("src/main.py"), "Missing src/main.py"
        assert os.path.exists("src/communicator_bot/main.py"), "Missing communicator bot main.py"
        
    except ImportError as e:
        pytest.fail(f"Import error: {e}")

def test_railway_files():
    """Test that Railway-specific files exist."""
    required_files = [
        "Procfile",
        "Dockerfile",
        "railway.yml",
        "requirements.txt",
        ".env.example",
        "railway_start.sh"
    ]
    
    for file in required_files:
        assert os.path.exists(file), f"Missing {file}"
        
    # Check that the railway_start.sh is executable
    assert os.access("railway_start.sh", os.X_OK), "railway_start.sh is not executable"
'''
        with open(test_file, "w") as f:
            f.write(test_content)
        logger.info(f"Created {test_file}")
        
        # Run the tests
        logger.info("Running tests...")
        result = subprocess.run(["pytest", "-xvs", test_file], capture_output=True, text=True)
        logger.info(f"Test output:\n{result.stdout}")
        if result.returncode != 0:
            logger.error(f"Tests failed:\n{result.stderr}")
            return False
        
        logger.info("Tests passed!")
    
    logger.info("Setup testing completed")
    return True

def main():
    """Main function to prepare for Railway deployment."""
    logger.info("Starting Railway setup...")
    
    # Run all setup steps and track results
    results = {
        "Prerequisites": check_prerequisites(),
        "Common Issues": fix_common_issues(),
        "Railway Files": create_railway_specific_files(),
        "Environment Variables": check_env_variables()
    }
    
    # Only run tests if all other steps passed
    if all(results.values()):
        results["Tests"] = test_setup()
    
    # Print summary
    print("\n" + "=" * 50)
    print("RAILWAY SETUP SUMMARY")
    print("=" * 50)
    for step_name, result in results.items():
        print(f"{step_name}: {'✅ PASSED' if result else '❌ FAILED'}")
    print("=" * 50)
    
    # Count failures
    failures = sum(1 for result in results.values() if not result)
    
    if failures == 0:
        print("\n✅ Railway setup completed successfully!")
        print("📋 Please refer to RAILWAY_DEPLOYMENT.md for deployment instructions.")
        print("🔧 If you encounter issues, check RAILWAY_TROUBLESHOOTING.md.")
        return True
    else:
        print(f"\n⚠️ Railway setup completed with {failures} issues.")
        print("📋 Please check the logs and fix the issues before deploying.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 