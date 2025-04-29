#!/usr/bin/env python3
"""
Railway Deployment Optimization Script - Simple Version

This script optimizes the Railway deployment configuration by:
1. Updating the railway.toml and railway.yml files
2. Ensuring proper webhook reset functionality
3. Fixing the communicator bot
"""

import os
import sys
import logging
import re
import shutil
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Target files
RAILWAY_TOML = "railway.toml"
RAILWAY_YML = "railway.yml"
COMMUNICATOR_MAIN_PY = "src/communicator_bot/main.py"

def backup_file(file_path):
    """Create a backup of a file before modifying it."""
    if not os.path.exists(file_path):
        logger.warning(f"File not found, cannot backup: {file_path}")
        return False
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{file_path}.optimize_{timestamp}.bak"
    
    try:
        shutil.copy2(file_path, backup_path)
        logger.info(f"Created backup: {backup_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to create backup of {file_path}: {e}")
        return False

def optimize_railway_toml():
    """Optimize the Railway TOML configuration file."""
    if not os.path.exists(RAILWAY_TOML):
        logger.error(f"Railway TOML file not found: {RAILWAY_TOML}")
        return False
        
    # Backup the file first
    if not backup_file(RAILWAY_TOML):
        return False
        
    try:
        # Define optimized configuration
        optimized_config = """[build]
builder = "nixpacks"
buildCommand = "pip install -r requirements.txt && python check_dependencies.py || echo 'Dependency check failed but continuing build'"

[deploy]
startCommand = "python -m src.main"
healthcheckPath = "/health"
healthcheckTimeout = 30
restartPolicy = "on-failure"
restartPolicyMaxRetries = 10

[nixpacks]
pkgs = ["python310", "gcc", "build-essential", "curl", "python310Packages.pip"]
"""
        
        # Write updated content
        with open(RAILWAY_TOML, 'w') as file:
            file.write(optimized_config)
            
        logger.info(f"Updated {RAILWAY_TOML} with optimized configuration")
        return True
            
    except Exception as e:
        logger.error(f"Error updating {RAILWAY_TOML}: {e}")
        return False

def optimize_railway_yml():
    """Optimize the Railway YML configuration file."""
    if not os.path.exists(RAILWAY_YML):
        logger.warning(f"Railway YML file not found: {RAILWAY_YML}")
        # Create the file if it doesn't exist
        try:
            optimized_yml = """# Railway configuration
version: 2
services:
  allkinds-bot:
    dockerfilePath: ./Dockerfile
    startCommand: python3 -m src.main
    healthcheckPath: /health
    healthcheckTimeout: 30
    healthcheckInterval: 30
    envVars:
      - key: PYTHON_VERSION
        value: 3.10.0
"""
            with open(RAILWAY_YML, 'w') as file:
                file.write(optimized_yml)
                
            logger.info(f"Created {RAILWAY_YML} with optimized configuration")
            return True
        except Exception as e:
            logger.error(f"Error creating {RAILWAY_YML}: {e}")
            return False
            
    # Backup the file first
    if not backup_file(RAILWAY_YML):
        return False
        
    try:
        # Read the file
        with open(RAILWAY_YML, 'r') as file:
            content = file.read()
            
        # Update healthcheck timeout and interval
        content = re.sub(
            r"healthcheckTimeout: \d+",
            "healthcheckTimeout: 30",
            content
        )
        
        content = re.sub(
            r"healthcheckInterval: \d+",
            "healthcheckInterval: 30",
            content
        )
        
        # Write updated content
        with open(RAILWAY_YML, 'w') as file:
            file.write(content)
            
        logger.info(f"Updated {RAILWAY_YML} with optimized configuration")
        return True
            
    except Exception as e:
        logger.error(f"Error updating {RAILWAY_YML}: {e}")
        return False

def fix_communicator_bot():
    """Fix the reset_webhook function in communicator bot's main.py file."""
    if not os.path.exists(COMMUNICATOR_MAIN_PY):
        logger.error(f"Communicator bot file not found: {COMMUNICATOR_MAIN_PY}")
        return False
        
    # Backup the file first
    if not backup_file(COMMUNICATOR_MAIN_PY):
        return False
        
    try:
        # Read the file
        with open(COMMUNICATOR_MAIN_PY, 'r') as file:
            content = file.read()
            
        # Check for duplicate try/except blocks in reset_webhook
        if content.count("Trying reset webhook with direct HTTP request as fallback...") > 1:
            logger.info("Found duplicated code in reset_webhook function. Fixing...")
            
            # Define the fixed reset_webhook function
            fixed_reset_webhook = """async def reset_webhook():
    """Reset the Telegram webhook to ensure no conflicts."""
    if not COMMUNICATOR_BOT_TOKEN:
        logger.error("Cannot reset webhook: No token available")
        return False
    
    # Try with direct HTTP request as fallback
    try:
        import requests
        logger.info("Trying reset webhook with direct HTTP request as fallback...")
        response = requests.get(
            f"https://api.telegram.org/bot{COMMUNICATOR_BOT_TOKEN}/deleteWebhook?drop_pending_updates=true"
        )
        result = response.json()
        if result.get("ok"):
            logger.info("Webhook deleted successfully with direct HTTP request")
            return True
        else:
            logger.error(f"Failed to delete webhook with direct request: {result}")
    except Exception as e:
        logger.error(f"Error with direct webhook reset: {e}")
        
    # Try with aiohttp client
    try:
        logger.info("Resetting Telegram webhook using aiohttp...")
        # Create a default SSL context that doesn't verify
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        # Create a session with relaxed SSL configuration
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        async with aiohttp.ClientSession(connector=connector) as session:
            # First, check current webhook status
            async with session.get(
                f"https://api.telegram.org/bot{COMMUNICATOR_BOT_TOKEN}/getWebhookInfo"
            ) as response:
                webhook_info = await response.json()
                logger.info(f"Current webhook status: {webhook_info}")
            
            # Force delete the webhook with drop_pending_updates
            async with session.get(
                f"https://api.telegram.org/bot{COMMUNICATOR_BOT_TOKEN}/deleteWebhook?drop_pending_updates=true"
            ) as response:
                result = await response.json()
                if result.get("ok"):
                    logger.info("Webhook deleted successfully")
                    return True
                else:
                    logger.error(f"Failed to delete webhook: {result}")
                    
            # Verify webhook was deleted
            await asyncio.sleep(1)  # Give Telegram a moment to process
            async with session.get(
                f"https://api.telegram.org/bot{COMMUNICATOR_BOT_TOKEN}/getWebhookInfo"
            ) as response:
                webhook_info = await response.json()
                if webhook_info.get("ok") and not webhook_info.get("result", {}).get("url"):
                    logger.info("Verified webhook is now empty")
                    return True
    except Exception as e:
        logger.error(f"Error resetting webhook: {e}")
    
    return False"""
            
            # Define the pattern to match the whole reset_webhook function
            reset_webhook_pattern = r"async def reset_webhook\(\):.*?(?=async def|def|\n\n\n|$)"
            
            # Replace the reset_webhook function
            updated_content = re.sub(
                reset_webhook_pattern,
                fixed_reset_webhook,
                content,
                flags=re.DOTALL
            )
            
            # Check if replacement was successful
            if updated_content != content:
                # Write updated content back to file
                with open(COMMUNICATOR_MAIN_PY, 'w') as file:
                    file.write(updated_content)
                    
                logger.info(f"Updated reset_webhook function in {COMMUNICATOR_MAIN_PY}")
                return True
            else:
                logger.warning(f"No changes made to reset_webhook function in {COMMUNICATOR_MAIN_PY}")
                return False
        else:
            logger.info(f"No duplicate code found in reset_webhook function in {COMMUNICATOR_MAIN_PY}")
            return True
                
    except Exception as e:
        logger.error(f"Error updating {COMMUNICATOR_MAIN_PY}: {e}")
        return False

def main():
    """Run all optimizations for Railway deployment."""
    logger.info("Starting Railway deployment optimization")
    
    results = {
        "railway_toml": optimize_railway_toml(),
        "railway_yml": optimize_railway_yml(),
        "communicator_bot": fix_communicator_bot()
    }
    
    # Summarize results
    logger.info("\n--- Optimization Results ---")
    all_success = True
    for step, success in results.items():
        status = "✅ Success" if success else "❌ Failed"
        logger.info(f"{step.replace('_', ' ').title()}: {status}")
        if not success:
            all_success = False
            
    if all_success:
        logger.info("\n✅ All optimizations completed successfully!")
        logger.info("\nTo apply these changes:")
        logger.info("1. Commit the changes to your repository")
        logger.info("2. Push to Railway or merge to your deployment branch")
        logger.info("3. Verify the deployment in the Railway dashboard")
    else:
        logger.warning("\n⚠️ Some optimizations failed. Please check the logs for details.")
        
    return 0 if all_success else 1

if __name__ == "__main__":
    sys.exit(main()) 