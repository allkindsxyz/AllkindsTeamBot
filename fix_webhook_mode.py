#!/usr/bin/env python3
"""
Webhook Mode Fix Script

This script properly configures both bots to use webhook mode by:
1. Setting up correct webhook URLs
2. Ensuring proper webhook registration with Telegram
3. Updating configuration files as needed
"""

import os
import sys
import logging
import asyncio
import aiohttp
import ssl
import requests
import re
import shutil
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Try to load dotenv if available
try:
    from dotenv import load_dotenv
    load_dotenv()
    logger.info("Loaded environment variables from .env file")
except ImportError:
    logger.warning("python-dotenv not installed, continuing without loading .env file")

# Config files to modify
CONFIG_FILE = "src/core/config.py"
MAIN_FILE = "src/main.py"
MAIN_BOT_FILE = "src/bot/main.py"
COMMUNICATOR_BOT_FILE = "src/communicator_bot/main.py"

# Get tokens from environment
MAIN_BOT_TOKEN = os.environ.get("BOT_TOKEN")
COMMUNICATOR_BOT_TOKEN = os.environ.get("COMMUNICATOR_BOT_TOKEN")

def backup_file(file_path):
    """Create a backup of a file before modifying it."""
    if not os.path.exists(file_path):
        logger.warning(f"File not found, cannot backup: {file_path}")
        return False
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{file_path}.webhook_fix_{timestamp}.bak"
    
    try:
        shutil.copy2(file_path, backup_path)
        logger.info(f"Created backup: {backup_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to create backup of {file_path}: {e}")
        return False

def update_env_file():
    """Create or update .env file with USE_WEBHOOK=true."""
    env_file = ".env"
    env_content = {}
    
    # Read existing .env file if it exists
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    env_content[key.strip()] = value.strip()
    
    # Update USE_WEBHOOK setting
    env_content["USE_WEBHOOK"] = "true"
    
    # Set webhook host if available
    railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN")
    if railway_domain:
        env_content["WEBHOOK_HOST"] = f"https://{railway_domain}"
    
    # Make sure tokens are present and correctly quoted if they contain special characters
    tokens = ["BOT_TOKEN", "COMMUNICATOR_BOT_TOKEN"]
    for token_key in tokens:
        token_value = os.environ.get(token_key, env_content.get(token_key, ""))
        if token_value:
            # If token has special characters, quote it
            if any(c in token_value for c in " ,;:|\"'"):
                if not (token_value.startswith('"') and token_value.endswith('"')):
                    token_value = f'"{token_value}"'
            env_content[token_key] = token_value
    
    # Write updated content back to .env file
    with open(env_file, "w") as f:
        f.write(f"# Updated by fix_webhook_mode.py at {datetime.now().isoformat()}\n")
        for key, value in env_content.items():
            f.write(f"{key}={value}\n")
    
    logger.info(f"Updated {env_file} with USE_WEBHOOK=true and verified tokens")
    return True

def fix_config_file():
    """Update config.py to properly use webhook mode."""
    if not os.path.exists(CONFIG_FILE):
        logger.error(f"Config file not found: {CONFIG_FILE}")
        return False
        
    # Backup the file first
    if not backup_file(CONFIG_FILE):
        return False
        
    try:
        # Read the file
        with open(CONFIG_FILE, 'r') as file:
            content = file.read()
            
        # Find and update the USE_WEBHOOK field
        use_webhook_pattern = r"(USE_WEBHOOK\s*:\s*bool\s*=\s*Field\().*?(\))"
        
        # Update to always use webhook mode on Railway
        updated_content = re.sub(
            use_webhook_pattern,
            r'\1default=bool(os.environ.get("RAILWAY_ENVIRONMENT")), alias="USE_WEBHOOK"\2',
            content,
            flags=re.DOTALL
        )
        
        # Write updated content back to file
        with open(CONFIG_FILE, 'w') as file:
            file.write(updated_content)
            
        logger.info(f"Updated {CONFIG_FILE} to use webhook mode on Railway")
        return True
    except Exception as e:
        logger.error(f"Error updating {CONFIG_FILE}: {e}")
        return False

def fix_main_file():
    """Update main.py to properly set up webhook URLs."""
    if not os.path.exists(MAIN_FILE):
        logger.error(f"Main file not found: {MAIN_FILE}")
        return False
        
    # Backup the file first
    if not backup_file(MAIN_FILE):
        return False
        
    try:
        # Read the file
        with open(MAIN_FILE, 'r') as file:
            content = file.read()
            
        # Ensure the get_webhook_url function uses https:// prefix
        webhook_url_pattern = r"(def get_webhook_url\(\):.*?webhook_host = f\")(https://)?({railway_url}\")(.*?return webhook_host)"
        
        # Make sure we're always using https:// prefix
        updated_content = re.sub(
            webhook_url_pattern,
            r'\1https://\3\4',
            content,
            flags=re.DOTALL
        )
        
        # Make sure the environment variables are properly set for both bots
        env_section_pattern = r"(# Set environment variables for children processes.*?)(os\.environ\[\"WEBHOOK_HOST\"\] = webhook_url.*?)(.*?)"
        
        # Update environment variables section
        webhook_env_update = r"""    # Set environment variables for both bots
    os.environ["USE_WEBHOOK"] = "true"
    os.environ["WEBHOOK_HOST"] = webhook_url
    os.environ["WEBHOOK_PATH"] = "/webhook"
    
    # Main bot uses /webhook path
    os.environ["BOT_WEBHOOK_PATH"] = "/webhook"
    # Communicator bot uses /comm_webhook path for separation
    os.environ["COMMUNICATOR_WEBHOOK_PATH"] = "/comm_webhook"
"""
        updated_content = re.sub(
            env_section_pattern,
            r'\1' + webhook_env_update + r'\3',
            updated_content,
            flags=re.DOTALL
        )
        
        # Write updated content back to file
        with open(MAIN_FILE, 'w') as file:
            file.write(updated_content)
            
        logger.info(f"Updated {MAIN_FILE} to properly set up webhook URLs")
        return True
    except Exception as e:
        logger.error(f"Error updating {MAIN_FILE}: {e}")
        return False

def fix_main_bot_file():
    """Update main bot file for proper webhook handling."""
    if not os.path.exists(MAIN_BOT_FILE):
        logger.error(f"Main bot file not found: {MAIN_BOT_FILE}")
        return False
        
    # Backup the file first
    if not backup_file(MAIN_BOT_FILE):
        return False
        
    try:
        # Read the file
        with open(MAIN_BOT_FILE, 'r') as file:
            content = file.read()
            
        # Ensure the webhook path is consistent
        webhook_url_pattern = r"(webhook_path\s*=\s*\")([^\"]+)(\"\s+.*?webapp_host\s*=\s*\"0\.0\.0\.0\")"
        
        # Make sure we're using the correct webhook path from environment
        updated_content = re.sub(
            webhook_url_pattern,
            r'\1/webhook\3',
            content,
            flags=re.DOTALL
        )
        
        # Enhance webhook reset to ensure it's working properly
        reset_webhook_pattern = r"(async def reset_webhook\(bot\):.*?return False)(.*?)(async def run_webhook_bot\(\):)"
        
        enhanced_reset = r"""
    # Try with direct HTTP request as fallback
    try:
        logger.info("Trying reset webhook with direct HTTP request as fallback...")
        url = f"https://api.telegram.org/bot{bot.token}/deleteWebhook?drop_pending_updates=true"
        response = requests.get(url, timeout=10)
        result = response.json()
        if result.get("ok"):
            logger.info("Webhook deleted successfully with direct HTTP request")
            return True
        else:
            logger.error(f"Failed to delete webhook: {result}")
            return False
    except Exception as e:
        logger.error(f"Error with direct webhook reset: {e}")
        return False\2\3"""
        
        updated_content = re.sub(
            reset_webhook_pattern,
            r'\1' + enhanced_reset,
            updated_content,
            flags=re.DOTALL
        )
        
        # Enhance the webhook setup in run_webhook_bot function
        run_webhook_pattern = r"(async def run_webhook_bot\(\):.*?# Initialize the bot with an AiohttpSession for better control)(.*?)(async with)(.*?)(await bot\.set_webhook)"
        
        enhanced_webhook_setup = r"""\2
    # Get webhook details from environment or settings
    webhook_host = os.environ.get("WEBHOOK_HOST", webhook_host)
    webhook_path = os.environ.get("BOT_WEBHOOK_PATH", webhook_path)
    
    # Construct full webhook URL
    webhook_url = f"{webhook_host}{webhook_path}"
    logger.info(f"Setting up webhook with URL: {webhook_url}")
    
    # First, make sure any existing webhook is removed
    await reset_webhook(bot)
    
\3\4\5"""
        
        updated_content = re.sub(
            run_webhook_pattern,
            r'\1' + enhanced_webhook_setup,
            updated_content,
            flags=re.DOTALL
        )
        
        # Write updated content back to file
        with open(MAIN_BOT_FILE, 'w') as file:
            file.write(updated_content)
            
        logger.info(f"Updated {MAIN_BOT_FILE} with enhanced webhook handling")
        return True
    except Exception as e:
        logger.error(f"Error updating {MAIN_BOT_FILE}: {e}")
        return False

def fix_communicator_bot_file():
    """Update communicator bot file for proper webhook setup."""
    if not os.path.exists(COMMUNICATOR_BOT_FILE):
        logger.error(f"Communicator bot file not found: {COMMUNICATOR_BOT_FILE}")
        return False
        
    # Backup the file first
    if not backup_file(COMMUNICATOR_BOT_FILE):
        return False
        
    try:
        # Read the file
        with open(COMMUNICATOR_BOT_FILE, 'r') as file:
            content = file.read()
            
        # Enhance the webhook setup to use distinct webhook path
        setup_webhook_pattern = r"(async def setup_webhook_server\(\):.*?)(webhook_host = os\.environ\.get\(\"WEBHOOK_HOST\"\).*?webhook_url = f\"{webhook_host}\/webhook\")(.*?)(await bot\.set_webhook\(webhook_url\))"
        
        enhanced_webhook_setup = r"""\1# Get webhook details from environment
        webhook_host = os.environ.get("WEBHOOK_HOST")
        webhook_path = os.environ.get("COMMUNICATOR_WEBHOOK_PATH", "/comm_webhook")
        
        # Construct full webhook URL
        if webhook_host:
            # Make sure webhook host has https:// prefix
            if not webhook_host.startswith("http"):
                webhook_host = f"https://{webhook_host}"
                
            webhook_url = f"{webhook_host}{webhook_path}"
            logger.info(f"Setting webhook URL: {webhook_url}")\3\4"""
        
        updated_content = re.sub(
            setup_webhook_pattern,
            enhanced_webhook_setup,
            content,
            flags=re.DOTALL
        )
        
        # Enhance the webhook reset function
        reset_pattern = r"(async def reset_webhook\(\):.*?return False)(.*?)(async def setup_webhook_server\(\):)"
        
        enhanced_reset = r"""
    # Try with direct HTTP request as fallback
    try:
        logger.info("Trying reset webhook with direct HTTP request as fallback...")
        import requests
        response = requests.get(
            f"https://api.telegram.org/bot{COMMUNICATOR_BOT_TOKEN}/deleteWebhook?drop_pending_updates=true",
            verify=False,
            timeout=10
        )
        result = response.json()
        if result.get("ok"):
            logger.info("Webhook deleted successfully with direct HTTP request")
            return True
        else:
            logger.error(f"Failed to delete webhook: {result}")
            return False
    except Exception as e:
        logger.error(f"Error with direct webhook reset: {e}")
        return False\2\3"""
        
        updated_content = re.sub(
            reset_pattern,
            r'\1' + enhanced_reset,
            updated_content,
            flags=re.DOTALL
        )
        
        # Fix the webhook path in the API route
        webhook_route_pattern = r"(app\.router\.add_post\(\")\/webhook(\", webhook_handler\))"
        
        updated_content = re.sub(
            webhook_route_pattern,
            r'\1/comm_webhook\2',
            updated_content,
            flags=re.DOTALL
        )
        
        # Write updated content back to file
        with open(COMMUNICATOR_BOT_FILE, 'w') as file:
            file.write(updated_content)
            
        logger.info(f"Updated {COMMUNICATOR_BOT_FILE} with proper webhook setup")
        return True
    except Exception as e:
        logger.error(f"Error updating {COMMUNICATOR_BOT_FILE}: {e}")
        return False

async def set_webhook(bot_token, webhook_url, bot_name="Unknown"):
    """Set webhook for a bot using HTTP request."""
    if not bot_token:
        logger.error(f"Cannot set webhook for {bot_name}: Token not provided")
        return False
    
    if not webhook_url:
        logger.error(f"Cannot set webhook for {bot_name}: No webhook URL provided")
        return False
        
    logger.info(f"Setting webhook for {bot_name} to: {webhook_url}")
    
    # Make sure webhook URL starts with https://
    if not webhook_url.startswith("https://"):
        webhook_url = f"https://{webhook_url}"
    
    # Create a session with relaxed SSL configuration
    connector = aiohttp.TCPConnector(verify_ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        # First, delete any existing webhook
        try:
            async with session.get(
                f"https://api.telegram.org/bot{bot_token}/deleteWebhook?drop_pending_updates=true"
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get("ok"):
                        logger.info(f"{bot_name} webhook deleted successfully")
                    else:
                        error = result.get("description", "Unknown error")
                        logger.error(f"Failed to delete webhook: {error}")
                else:
                    logger.error(f"Failed to delete webhook: HTTP {response.status}")
        except Exception as e:
            logger.error(f"Error deleting webhook: {e}")
        
        # Wait a bit before setting new webhook
        await asyncio.sleep(1)
        
        # Set new webhook
        try:
            async with session.post(
                f"https://api.telegram.org/bot{bot_token}/setWebhook",
                json={"url": webhook_url, "drop_pending_updates": True}
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get("ok"):
                        logger.info(f"{bot_name} webhook set successfully to: {webhook_url}")
                        return True
                    else:
                        error = result.get("description", "Unknown error")
                        logger.error(f"Failed to set webhook: {error}")
                else:
                    logger.error(f"Failed to set webhook: HTTP {response.status}")
        except Exception as e:
            logger.error(f"Error setting webhook: {e}")
    
    # If async method failed, try with regular requests
    try:
        logger.info(f"Trying alternative method for {bot_name}...")
        # First, delete any existing webhook
        response = requests.get(
            f"https://api.telegram.org/bot{bot_token}/deleteWebhook?drop_pending_updates=true",
            verify=False,
            timeout=10
        )
        
        # Set new webhook
        response = requests.post(
            f"https://api.telegram.org/bot{bot_token}/setWebhook",
            json={"url": webhook_url, "drop_pending_updates": True},
            verify=False,
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get("ok"):
                logger.info(f"{bot_name} webhook set successfully with alternative method to: {webhook_url}")
                return True
            else:
                error = result.get("description", "Unknown error")
                logger.error(f"Failed to set webhook with alternative method: {error}")
        else:
            logger.error(f"Failed to set webhook: HTTP {response.status_code}")
    except Exception as e:
        logger.error(f"Error with alternative webhook setting: {e}")
    
    return False

def create_railway_config():
    """Create or update the Railway config file to use webhook mode."""
    railway_config = "railway.toml"
    
    config_content = """# Railway Configuration
# Generated by fix_webhook_mode.py at {timestamp}

[build]
builder = "nixpacks"
buildCommand = "pip install -r requirements.txt"

[deploy]
startCommand = "python -m src.main"
healthcheckPath = "/health"
healthcheckTimeout = 10
restartPolicyType = "on-failure"
restartPolicyMaxRetries = 5

[environments]
  # Production environment
  [environments.production]
    # Force webhook mode
    USE_WEBHOOK = "true"
    # Optimize worker settings
    numReplicas = 1
    
    # Health check settings
    healthcheckPath = "/health"
    healthcheckTimeout = 10
    
    # Optimize for Railway
    PORT = "8080"
    
    # Bot settings
    # You need to provide valid tokens in Railway dashboard
    # BOT_TOKEN = "YOUR_MAIN_BOT_TOKEN"
    # COMMUNICATOR_BOT_TOKEN = "YOUR_COMMUNICATOR_BOT_TOKEN"
    # Communicator bot username (without @)
    COMMUNICATOR_BOT_USERNAME = "AllkindsChatBot"
    
    # Webhook paths
    BOT_WEBHOOK_PATH = "/webhook"
    COMMUNICATOR_WEBHOOK_PATH = "/comm_webhook"
    
    # Optional settings for debugging 
    LOG_LEVEL = "INFO"
""".format(timestamp=datetime.now().isoformat())
    
    try:
        # Make a backup if the file exists
        if os.path.exists(railway_config):
            backup_path = f"{railway_config}.bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            os.rename(railway_config, backup_path)
            logger.info(f"Created backup of existing config: {backup_path}")
        
        # Write the new config
        with open(railway_config, "w") as f:
            f.write(config_content)
        
        logger.info(f"Created new Railway configuration file: {railway_config}")
        return True
    except Exception as e:
        logger.error(f"Error creating Railway config: {e}")
        return False

def verify_and_correct_token(bot_name, token_var_name):
    """Verify and correct token in environment variables."""
    token = os.environ.get(token_var_name)
    if not token:
        logger.error(f"{bot_name} token not found in environment variables")
        return None
    
    # Token should be alphanumeric with potential colons
    token = token.strip()
    if token.startswith('"') and token.endswith('"'):
        token = token[1:-1]
    if token.startswith("'") and token.endswith("'"):
        token = token[1:-1]
    
    # Correct token
    os.environ[token_var_name] = token
    logger.info(f"Verified and corrected {bot_name} token format")
    return token

async def main():
    """Main function to fix webhook mode."""
    logger.info("Starting webhook mode fix script...")
    
    # Verify and correct tokens
    main_bot_token = verify_and_correct_token("Main Bot", "BOT_TOKEN")
    comm_bot_token = verify_and_correct_token("Communicator Bot", "COMMUNICATOR_BOT_TOKEN")
    
    if not main_bot_token or not comm_bot_token:
        logger.error("Bot token verification failed. Cannot continue.")
        return False
    
    # Update .env file
    update_env_file()
    
    # Set environment variables
    os.environ["USE_WEBHOOK"] = "true"
    
    # Get webhook host from Railway if available
    railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN")
    webhook_host = f"https://{railway_domain}" if railway_domain else os.environ.get("WEBHOOK_HOST")
    
    if not webhook_host:
        logger.warning("No webhook host found in environment. Using default.")
        webhook_host = "https://allkindsteambot-production.up.railway.app"
    
    # Define webhook paths
    main_webhook_path = "/webhook"
    comm_webhook_path = "/comm_webhook"
    
    # Set webhooks for both bots
    main_webhook_url = f"{webhook_host}{main_webhook_path}"
    comm_webhook_url = f"{webhook_host}{comm_webhook_path}"
    
    # Create Railway configuration
    create_railway_config()
    
    # Fix configuration files
    config_result = fix_config_file()
    main_result = fix_main_file()
    main_bot_result = fix_main_bot_file()
    comm_bot_result = fix_communicator_bot_file()
    
    # Set webhooks directly with Telegram API
    main_webhook_set = await set_webhook(main_bot_token, main_webhook_url, "Main Bot")
    comm_webhook_set = await set_webhook(comm_bot_token, comm_webhook_url, "Communicator Bot")
    
    logger.info("================= SUMMARY =================")
    logger.info(f".env file updated with USE_WEBHOOK=true: ✅")
    logger.info(f"Railway config created: ✅")
    logger.info(f"Config file updated: {'✅' if config_result else '❌'}")
    logger.info(f"Main file updated: {'✅' if main_result else '❌'}")
    logger.info(f"Main bot file updated: {'✅' if main_bot_result else '❌'}")
    logger.info(f"Communicator bot file updated: {'✅' if comm_bot_result else '❌'}")
    logger.info(f"Main bot webhook set: {'✅' if main_webhook_set else '❌'}")
    logger.info(f"Communicator bot webhook set: {'✅' if comm_webhook_set else '❌'}")
    logger.info("===========================================")
    logger.info("To apply these changes to your Railway deployment:")
    logger.info("1. Commit and push these changes to your repository")
    logger.info("2. Your Railway deployment should automatically update")
    logger.info("3. Both bots should now respond properly in webhook mode")
    
    return True

if __name__ == "__main__":
    asyncio.run(main()) 