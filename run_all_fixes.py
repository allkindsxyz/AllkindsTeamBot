#!/usr/bin/env python3
"""
All-in-One Fix Script for Railway Deployment

This script runs all necessary fixes to ensure both the main bot and 
communicator bot work properly when deployed on Railway.
"""

import os
import sys
import logging
import subprocess
from datetime import datetime
import shutil

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def backup_file(file_path):
    """Create a backup of the file."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{file_path}.railway_bak_{timestamp}"
    try:
        shutil.copy2(file_path, backup_path)
        logger.info(f"Created backup at {backup_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to create backup: {e}")
        return False

def run_script(script_path):
    """Run a Python script and return its success status."""
    logger.info(f"Running fix script: {script_path}")
    try:
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            check=False
        )
        
        # Log output
        for line in result.stdout.splitlines():
            logger.info(f"[{script_path}] {line}")
        
        if result.stderr:
            for line in result.stderr.splitlines():
                logger.error(f"[{script_path}] {line}")
        
        if result.returncode != 0:
            logger.error(f"Script {script_path} failed with exit code {result.returncode}")
            return False
            
        logger.info(f"Script {script_path} completed successfully")
        return True
    except Exception as e:
        logger.error(f"Error running script {script_path}: {e}")
        return False

def fix_communicator_bot_username():
    """Update the COMMUNICATOR_BOT_USERNAME in config.py."""
    config_file = "src/core/config.py"
    
    if not os.path.exists(config_file):
        logger.error(f"Config file {config_file} not found!")
        return False
    
    # Create backup
    if not backup_file(config_file):
        logger.error("Failed to create backup of config file, aborting.")
        return False
    
    try:
        import re
        # Read the file
        with open(config_file, 'r') as file:
            content = file.read()
        
        # Check if COMMUNICATOR_BOT_USERNAME field exists
        username_pattern = r"COMMUNICATOR_BOT_USERNAME:\s*str\s*=\s*Field\(default=\".*?\""
        if re.search(username_pattern, content):
            # Update existing field
            updated_content = re.sub(
                username_pattern,
                'COMMUNICATOR_BOT_USERNAME: str = Field(default="AllkindsCommunicatorBot"', 
                content
            )
        else:
            logger.warning("COMMUNICATOR_BOT_USERNAME field not found, will add it")
            # Add the field after the BOT_TOKEN field
            bot_token_pattern = r"(BOT_TOKEN:\s*str\s*=.*?\))"
            updated_content = re.sub(
                bot_token_pattern,
                r'\1\n    COMMUNICATOR_BOT_USERNAME: str = Field(default="AllkindsCommunicatorBot", alias="COMMUNICATOR_BOT_USERNAME")',
                content
            )
        
        # Write the changes back to the file
        with open(config_file, 'w') as file:
            file.write(updated_content)
        
        logger.info(f"Successfully updated {config_file} with proper communicator bot username")
        return True
    
    except Exception as e:
        logger.error(f"Error fixing config file: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False

def fix_db_connection_handling():
    """Fix database connection handling for Railway deployment."""
    db_file = "src/db/base.py"
    
    if not os.path.exists(db_file):
        logger.error(f"Database file {db_file} not found!")
        return False
    
    # Create backup
    if not backup_file(db_file):
        logger.error("Failed to create backup of database file, aborting.")
        return False
    
    try:
        import re
        # Read the file
        with open(db_file, 'r') as file:
            content = file.read()
        
        # 1. Update connect args
        connect_args_pattern = r"(connect_args = \{)([^}]*?)(\})"
        connect_args_replacement = r'\1\n        "timeout": 60, \n        "command_timeout": 60, \n        "server_settings": {\n            "application_name": "allkinds",\n            "idle_in_transaction_session_timeout": "60000"\n        },\n        "statement_cache_size": 0\n    \3'
        content = re.sub(connect_args_pattern, connect_args_replacement, content, flags=re.DOTALL)
        
        # 2. Update engine configuration
        engine_pattern = r"(engine = create_async_engine\(\s+SQLALCHEMY_DATABASE_URL,.*?)(pool_recycle=\d+,\s+pool_timeout=\d+,\s+pool_size=\d+,\s+max_overflow=\d+,)(.*?\))"
        engine_replacement = r'\1pool_recycle=120, pool_timeout=60, pool_size=5, max_overflow=10, pool_use_lifo=True,\3'
        content = re.sub(engine_pattern, engine_replacement, content, flags=re.DOTALL)
        
        # 3. Add more descriptive logging
        init_models_pattern = r"async def init_models\(engine\):"
        init_models_replacement = r'async def init_models(engine):\n    """Initialize database models with proper handling for Railway environment."""\n    logger.info(f"Initializing database models with engine {engine}...")'
        content = re.sub(init_models_pattern, init_models_replacement, content)
        
        # Write the changes back to the file
        with open(db_file, 'w') as file:
            file.write(content)
        
        logger.info(f"Successfully updated {db_file} with improved database connection handling")
        return True
    
    except Exception as e:
        logger.error(f"Error fixing database file: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False

def check_essential_environment_variables():
    """Check and create a .env.example file with required variables."""
    env_example_file = ".env.example"
    
    required_vars = {
        "BOT_TOKEN": "YOUR_TELEGRAM_BOT_TOKEN",
        "COMMUNICATOR_BOT_TOKEN": "YOUR_COMMUNICATOR_BOT_TOKEN",
        "DATABASE_URL": "postgresql://username:password@hostname:port/database",
        "COMMUNICATOR_BOT_USERNAME": "AllkindsCommunicatorBot",
        "ADMIN_IDS": "12345678,87654321",
        "OPENAI_API_KEY": "YOUR_OPENAI_API_KEY"
    }
    
    # Create or update the .env.example file
    try:
        with open(env_example_file, 'w') as f:
            f.write("# Essential environment variables for Railway deployment\n\n")
            for var, value in required_vars.items():
                f.write(f"{var}={value}\n")
        
        logger.info(f"Created {env_example_file} with required environment variables")
        
        # Check if .env exists
        if not os.path.exists(".env"):
            logger.warning(".env file not found. Using environment variables from Railway settings.")
            
        # Check for variables in current environment
        missing_vars = []
        for var in required_vars:
            if not os.environ.get(var):
                missing_vars.append(var)
        
        if missing_vars:
            logger.warning(f"Missing environment variables: {', '.join(missing_vars)}")
            logger.warning("These need to be set in Railway's environment variables settings")
        else:
            logger.info("All required environment variables are set")
            
        return True
    
    except Exception as e:
        logger.error(f"Error checking environment variables: {e}")
        return False

def fix_deep_link_generation():
    """Fix deep link generation for communicator bot."""
    # Paths to check and fix
    paths_to_check = [
        "src/bot/handlers/start.py",
        "src/bot/handlers/match.py",
    ]
    
    success = True
    
    for file_path in paths_to_check:
        if not os.path.exists(file_path):
            logger.warning(f"File {file_path} not found, skipping")
            continue
        
        # Create backup
        if not backup_file(file_path):
            logger.error(f"Failed to create backup of {file_path}, skipping")
            success = False
            continue
        
        try:
            import re
            # Read the file
            with open(file_path, 'r') as file:
                content = file.read()
            
            # Fix deep link generation in file
            deep_link_pattern = r'f"https://t\.me/([a-zA-Z0-9_]+)\?start=([a-zA-Z0-9_]+)"'
            deep_link_replacement = r'f"https://t.me/{settings.COMMUNICATOR_BOT_USERNAME}?start=\2"'
            
            # Count matches
            matches = re.findall(deep_link_pattern, content)
            if matches:
                logger.info(f"Found {len(matches)} deep links to fix in {file_path}")
                
                # Only modify if settings import exists
                if "from src.core.config import get_settings" not in content:
                    # Add import for settings
                    content = "from src.core.config import get_settings\n" + content
                    content = re.sub(r"(def [a-zA-Z0-9_]+[^:]*:)", r"    settings = get_settings()\n\1", content)
                    
                # Fix the deep links
                content = re.sub(deep_link_pattern, deep_link_replacement, content)
                
                # Write the changes back to the file
                with open(file_path, 'w') as file:
                    file.write(content)
                
                logger.info(f"Successfully updated deep links in {file_path}")
            else:
                logger.info(f"No deep links found in {file_path}, skipping")
            
        except Exception as e:
            logger.error(f"Error fixing deep links in {file_path}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            success = False
    
    return success

def create_procfile():
    """Create or update Procfile for Railway deployment."""
    procfile_path = "Procfile"
    
    try:
        procfile_content = """
# Procfile for Railway deployment
# This runs both the main bot and the communicator bot
web: python3 -m src.main & python3 -m src.communicator_bot.main & wait
"""
        with open(procfile_path, 'w') as f:
            f.write(procfile_content.strip())
        
        logger.info(f"Created {procfile_path} for running both bots")
        return True
    
    except Exception as e:
        logger.error(f"Error creating Procfile: {e}")
        return False

def add_railway_yml():
    """Create railway.yml for Railway deployment."""
    railway_yml_path = "railway.yml"
    
    try:
        railway_content = """
# Railway configuration
version: 2
services:
  allkinds-bot:
    dockerfilePath: ./Dockerfile
    startCommand: python3 -m src.main
    healthcheckPath: /health
    healthcheckTimeout: 10
    healthcheckInterval: 30
    envVars:
      - key: PYTHON_VERSION
        value: 3.10.0
  
  communicator-bot:
    dockerfilePath: ./Dockerfile
    startCommand: python3 -m src.communicator_bot.main
    healthcheckPath: /health
    healthcheckTimeout: 10
    healthcheckInterval: 30
    envVars:
      - key: PYTHON_VERSION
        value: 3.10.0
"""
        with open(railway_yml_path, 'w') as f:
            f.write(railway_content.strip())
        
        logger.info(f"Created {railway_yml_path} for Railway deployment")
        return True
    
    except Exception as e:
        logger.error(f"Error creating railway.yml: {e}")
        return False

def create_deployment_guide():
    """Create a deployment guide for Railway."""
    guide_path = "RAILWAY_DEPLOYMENT.md"
    
    try:
        guide_content = """
# Railway Deployment Guide for AllkindsTeamBot

This guide provides step-by-step instructions for deploying the AllkindsTeamBot (including both the main bot and communicator bot) on Railway.

## Prerequisites

1. A Railway account
2. Git repository connected to Railway
3. Telegram bot tokens for both bots

## Environment Variables

Set the following environment variables in the Railway project settings:

- `BOT_TOKEN` - Your main Telegram bot token
- `COMMUNICATOR_BOT_TOKEN` - Your communicator bot token
- `COMMUNICATOR_BOT_USERNAME` - Username of your communicator bot (without @)
- `DATABASE_URL` - PostgreSQL connection string (automatically set by Railway if using their PostgreSQL plugin)
- `ADMIN_IDS` - Comma-separated list of admin Telegram IDs
- `OPENAI_API_KEY` - Your OpenAI API key

## Deployment Steps

1. Create a new Railway project
2. Add a PostgreSQL database using Railway's plugin
3. Connect your GitHub repository to the project
4. Set all the required environment variables
5. Deploy the application

## Troubleshooting

If you encounter any issues:

1. Check the application logs in Railway's dashboard
2. Verify all environment variables are set correctly
3. Restart the deployment if necessary
4. Make sure both bots are properly registered and active on Telegram

## Health Checks

Both bots expose a `/health` endpoint that Railway uses to monitor their status. If the health check fails, Railway will automatically restart the service.

## Database Maintenance

Railway's PostgreSQL database may require occasional maintenance:

1. Backups are handled automatically by Railway
2. Consider setting up periodic data exports for additional safety
3. Monitor database usage through Railway's dashboard
"""
        with open(guide_path, 'w') as f:
            f.write(guide_content.strip())
        
        logger.info(f"Created {guide_path} with deployment instructions")
        return True
    
    except Exception as e:
        logger.error(f"Error creating deployment guide: {e}")
        return False

def main():
    """Main function to run all fixes."""
    logger.info("Starting AllkindsTeamBot Railway deployment fixes...")
    
    # Track which fixes succeed
    fix_results = {
        "Bot Username": fix_communicator_bot_username(),
        "DB Connection": fix_db_connection_handling(),
        "Environment Variables": check_essential_environment_variables(),
        "Deep Link Generation": fix_deep_link_generation(),
        "Procfile": create_procfile(),
        "Railway Config": add_railway_yml(),
        "Deployment Guide": create_deployment_guide()
    }
    
    # Try running deploy_fix.py if it exists
    if os.path.exists("deploy_fix.py"):
        fix_results["Deploy Script"] = run_script("deploy_fix.py")
    
    # Print summary
    print("\n" + "=" * 50)
    print("RAILWAY DEPLOYMENT FIX SUMMARY")
    print("=" * 50)
    for fix_name, result in fix_results.items():
        print(f"{fix_name}: {'✅ COMPLETED' if result else '❌ FAILED'}")
    print("=" * 50)
    
    # Count failures
    failures = sum(1 for result in fix_results.values() if not result)
    
    if failures == 0:
        print("\n✅ All fixes have been applied successfully.")
        print("📋 Please refer to RAILWAY_DEPLOYMENT.md for deployment instructions.")
        return True
    else:
        print(f"\n⚠️ {failures} fixes could not be applied.")
        print("📋 Please check the logs for details and address the issues manually.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 