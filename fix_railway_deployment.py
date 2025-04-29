#!/usr/bin/env python3
"""
Railway Deployment Fix Script

This script diagnoses and fixes common issues with Railway deployment:
1. Ensures COMMUNICATOR_BOT_USERNAME is properly read from environment variables
2. Fixes bot verification and deep link generation 
3. Corrects database connection issues
"""

import os
import sys
import re
import shutil
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Files to check and update
CONFIG_FILE = "src/core/config.py"
MAIN_BOT_START_FILE = "src/bot/handlers/start.py"
MAIN_BOT_FILE = "src/bot/main.py"
COMMUNICATOR_BOT_FILE = "src/communicator_bot/main.py"
DB_FILE = "src/db/base.py"

def backup_file(file_path):
    """Create a backup of a file before modifying it."""
    if not os.path.exists(file_path):
        logger.warning(f"File not found, cannot backup: {file_path}")
        return False
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{file_path}.railway_fix_{timestamp}.bak"
    
    try:
        shutil.copy2(file_path, backup_path)
        logger.info(f"Created backup: {backup_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to create backup of {file_path}: {e}")
        return False

def fix_config_file():
    """Update config.py to properly get COMMUNICATOR_BOT_USERNAME from environment."""
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
            
        # Define the regex pattern to find and update the COMMUNICATOR_BOT_USERNAME field
        pattern = r"(COMMUNICATOR_BOT_USERNAME\s*:\s*str\s*=\s*Field\().*?(\))"
        
        if re.search(pattern, content, re.DOTALL):
            # Update the field to prioritize environment variables
            updated_content = re.sub(
                pattern,
                r'\1default=os.environ.get("COMMUNICATOR_BOT_USERNAME", "AllkindsCommunicatorBot"), alias="COMMUNICATOR_BOT_USERNAME"\2',
                content,
                flags=re.DOTALL
            )
            
            # Make sure os is imported
            if "import os" not in content:
                updated_content = "import os\n" + updated_content
                
            # Write updated content back to file
            with open(CONFIG_FILE, 'w') as file:
                file.write(updated_content)
                
            logger.info(f"Updated {CONFIG_FILE} to prioritize COMMUNICATOR_BOT_USERNAME from environment")
            return True
        else:
            logger.warning(f"Could not find COMMUNICATOR_BOT_USERNAME field in {CONFIG_FILE}")
            return False
            
    except Exception as e:
        logger.error(f"Error updating {CONFIG_FILE}: {e}")
        return False

def fix_db_connection():
    """Fix database connection handling for Railway."""
    if not os.path.exists(DB_FILE):
        logger.error(f"Database file not found: {DB_FILE}")
        return False
        
    # Backup the file first
    if not backup_file(DB_FILE):
        return False
        
    try:
        # Read the file
        with open(DB_FILE, 'r') as file:
            content = file.read()
            
        # Check for Railway environment detection
        if "IS_RAILWAY = os.environ.get('RAILWAY_ENVIRONMENT')" not in content:
            # Add Railway environment detection near the top of the file
            content = re.sub(
                r"(from sqlalchemy\.orm import DeclarativeBase.*?)\n",
                r"\1\nimport os\n# Check if we're in Railway\nIS_RAILWAY = os.environ.get('RAILWAY_ENVIRONMENT') is not None\n\n",
                content,
                flags=re.DOTALL
            )
            
        # Improve database URL processing with Railway-specific handling
        url_processing_pattern = r"(def process_database_url\(url\):.*?return url\s*\n)(.*?)\n"
        
        improved_url_processing = r"""    # Parse the URL to handle parameters safely
    try:
        # Handle Railway's postgres:// format
        if url.startswith('postgres://') or url.startswith('postgresql://'):
            # For asyncpg, we need to use postgresql+asyncpg://
            if 'asyncpg' not in url:
                if url.startswith('postgres://'):
                    url = url.replace('postgres://', 'postgresql+asyncpg://', 1)
                else:
                    url = url.replace('postgresql://', 'postgresql+asyncpg://', 1)
            
            # We no longer modify hostnames as they need to remain as provided by Railway
            logger.info(f"Processed database URL (starts with): {url[:15]}...")
            return url
"""
        
        content = re.sub(
            url_processing_pattern,
            r"\1\n" + improved_url_processing + r"\n",
            content,
            flags=re.DOTALL
        )
            
        # Update PostgreSQL connection arguments for better stability in cloud environment
        connect_args_pattern = r"(# PostgreSQL specific connect args.*?connect_args = \{)(.*?)(\})"
        connect_args_replacement = r'\1\n        "timeout": 60, \n        "command_timeout": 60, \n        "server_settings": {\n            "application_name": "allkinds",\n            "idle_in_transaction_session_timeout": "60000"\n        },\n        "statement_cache_size": 0\n    \3'
        
        content = re.sub(
            connect_args_pattern,
            connect_args_replacement,
            content,
            flags=re.DOTALL
        )
        
        # Update engine configuration for better connection pooling
        engine_pattern = r"(engine = create_async_engine\(\s+SQLALCHEMY_DATABASE_URL,.*?)(pool_[^,]+,(?:\s+pool_[^,]+,)+)(.*?\))"
        engine_replacement = r'\1pool_recycle=120, pool_timeout=60, pool_size=5, max_overflow=10, pool_use_lifo=True,\3'
        
        content = re.sub(
            engine_pattern,
            engine_replacement,
            content,
            flags=re.DOTALL
        )
            
        # Write updated content back to file
        with open(DB_FILE, 'w') as file:
            file.write(content)
            
        logger.info(f"Updated {DB_FILE} with improved database connection handling for Railway")
        return True
            
    except Exception as e:
        logger.error(f"Error updating {DB_FILE}: {e}")
        return False

def fix_communicator_bot():
    """Fix communicator bot to properly use environment variable for username."""
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
            
        # Add enhanced bot username handling
        bot_username_pattern = r"(# Verify token by getting bot info\s+try:)(.*?)(\s+bot_info = await bot\.get_me\(\))"
        bot_username_replacement = r"""\1
            # Check for bot username in environment
            bot_username = os.environ.get("COMMUNICATOR_BOT_USERNAME", "")
            if not bot_username:
                from src.core.config import get_settings
                settings = get_settings()
                bot_username = settings.COMMUNICATOR_BOT_USERNAME
                logger.info(f"Using bot username from settings: {bot_username}")
            else:
                logger.info(f"Using bot username from environment: {bot_username}")
                
            # Remove @ if it's included
            if bot_username and bot_username.startswith("@"):
                bot_username = bot_username[1:]
                logger.info(f"Removed @ prefix from bot username: {bot_username}")
                
            # Log token information for debugging (safely)
            if COMMUNICATOR_BOT_TOKEN:
                token_prefix = COMMUNICATOR_BOT_TOKEN[:4] if len(COMMUNICATOR_BOT_TOKEN) > 4 else "N/A"
                logger.info(f"Bot token available (prefix: {token_prefix}...)")
            else:
                logger.error("Bot token is empty or not set!")\2\3"""
                
        content = re.sub(
            bot_username_pattern,
            bot_username_replacement,
            content,
            flags=re.DOTALL
        )
        
        # Improve webhook handling to prevent conflicts
        webhook_pattern = r"(async def reset_webhook\(\):.*?return False)(.*?)(async def start_communicator_bot\(\))"
        webhook_replacement = r"""\1
    
    # Try again with direct HTTP request as fallback
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
            return False
    except Exception as e:
        logger.error(f"Error with direct webhook reset: {e}")
        return False\2\3"""
        
        content = re.sub(
            webhook_pattern,
            webhook_replacement,
            content,
            flags=re.DOTALL
        )
            
        # Write updated content back to file
        with open(COMMUNICATOR_BOT_FILE, 'w') as file:
            file.write(content)
            
        logger.info(f"Updated {COMMUNICATOR_BOT_FILE} with improved bot username handling")
        return True
            
    except Exception as e:
        logger.error(f"Error updating {COMMUNICATOR_BOT_FILE}: {e}")
        return False

def fix_deep_links():
    """Fix deep link generation to properly use COMMUNICATOR_BOT_USERNAME."""
    if not os.path.exists(MAIN_BOT_START_FILE):
        logger.error(f"Main bot start file not found: {MAIN_BOT_START_FILE}")
        return False
        
    # Backup the file first
    if not backup_file(MAIN_BOT_START_FILE):
        return False
        
    try:
        # Read the file
        with open(MAIN_BOT_START_FILE, 'r') as file:
            content = file.read()
            
        # Ensure settings import exists
        if "from src.core.config import get_settings" not in content:
            content = "from src.core.config import get_settings\n" + content
            logger.info(f"Added settings import to {MAIN_BOT_START_FILE}")
            
        # Add settings initialization to functions that generate deep links
        functions_with_deep_links = [
            "on_start_anon_chat", 
            "on_find_match", 
            "on_create_group"
        ]
        
        for func_name in functions_with_deep_links:
            func_pattern = rf"(async def {func_name}\([^)]+\):)"
            if func_name in content:
                # Add settings initialization at the beginning of the function
                content = re.sub(
                    func_pattern,
                    r"\1\n    settings = get_settings()",
                    content
                )
                logger.info(f"Added settings initialization to {func_name} function")
                
        # Fix deep link generation
        deep_link_pattern = r'f"https://t\.me/([a-zA-Z0-9_]+)\?start=([^"]+)"'
        deep_link_replacement = r'f"https://t.me/{settings.COMMUNICATOR_BOT_USERNAME}?start=\2"'
        
        if re.search(deep_link_pattern, content):
            # Replace deep links with proper environment-based username
            content = re.sub(
                deep_link_pattern,
                deep_link_replacement,
                content
            )
            logger.info(f"Fixed deep link generation in {MAIN_BOT_START_FILE}")
            
        # Add logging of all deep links generated for debugging
        anon_chat_pattern = r"(chat_link = f\"https://t\.me/.*?\n)(.*?)(await message\.answer)"
        anon_chat_replacement = r"\1    # Log the generated deep link for debugging\n    logger.info(f\"Generated deep link: {chat_link}\")\n\2\3"
        
        content = re.sub(
            anon_chat_pattern,
            anon_chat_replacement,
            content,
            flags=re.DOTALL
        )
            
        # Write updated content back to file
        with open(MAIN_BOT_START_FILE, 'w') as file:
            file.write(content)
            
        logger.info(f"Updated {MAIN_BOT_START_FILE} with improved deep link generation")
        return True
            
    except Exception as e:
        logger.error(f"Error updating {MAIN_BOT_START_FILE}: {e}")
        return False

def fix_main_bot():
    """Fix main bot to properly handle environment variables and initialization."""
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
            
        # Add enhanced environment variable logging
        start_bot_pattern = r"(async def start_bot\(\):.*?)(# Initialize repositories)"
        start_bot_replacement = r"""\1# Log environment variables (safely)
    logger.info("Checking environment variables:")
    env_vars = {
        "BOT_TOKEN": bool(os.environ.get("BOT_TOKEN")),
        "COMMUNICATOR_BOT_TOKEN": bool(os.environ.get("COMMUNICATOR_BOT_TOKEN")),
        "COMMUNICATOR_BOT_USERNAME": os.environ.get("COMMUNICATOR_BOT_USERNAME", "Not set"),
        "DATABASE_URL": bool(os.environ.get("DATABASE_URL")),
        "RAILWAY_ENVIRONMENT": os.environ.get("RAILWAY_ENVIRONMENT", "Not set"),
        "PORT": os.environ.get("PORT", "Not set")
    }
    for var, value in env_vars.items():
        if isinstance(value, bool):
            logger.info(f"  {var}: {'Set' if value else 'Not set'}")
        else:
            logger.info(f"  {var}: {value}")
    
    \2"""
        
        content = re.sub(
            start_bot_pattern,
            start_bot_replacement,
            content,
            flags=re.DOTALL
        )
        
        # Improve bot initialization with better error handling
        init_bot_pattern = r"(# Initialize bot.*?)(dp = Dispatcher\(\))"
        init_bot_replacement = r"""\1# Get token from environment
    bot_token = os.environ.get("BOT_TOKEN")
    if not bot_token:
        # Fall back to settings
        bot_token = settings.BOT_TOKEN
        logger.info("Using BOT_TOKEN from settings")
    else:
        logger.info("Using BOT_TOKEN from environment")
        
    if not bot_token:
        logger.error("BOT_TOKEN is not set! Cannot initialize bot.")
        raise ValueError("BOT_TOKEN is required to initialize the bot")
        
    # Initialize bot with token
    bot = Bot(token=bot_token, parse_mode=ParseMode.HTML)
    \2"""
        
        content = re.sub(
            init_bot_pattern,
            init_bot_replacement,
            content,
            flags=re.DOTALL
        )
        
        # Add webhook reset function
        webhook_reset_function = '''
async def reset_webhook(bot):
    """Reset webhook to prevent conflicts."""
    logger.info("Resetting webhook for main bot...")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Webhook reset successfully")
        return True
    except Exception as e:
        logger.error(f"Error resetting webhook: {e}")
        # Try a direct HTTP request as fallback
        try:
            import aiohttp
            logger.info("Attempting direct HTTP request to delete webhook...")
            bot_token = bot.token
            url = f"https://api.telegram.org/bot{bot_token}/deleteWebhook?drop_pending_updates=true"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    result = await response.json()
                    if result.get("ok"):
                        logger.info("Webhook reset successfully via direct HTTP request")
                        return True
                    else:
                        logger.error(f"Failed to reset webhook via direct HTTP: {result}")
        except Exception as inner_e:
            logger.error(f"Error in fallback webhook reset: {inner_e}")
        return False
'''
        
        # Add webhook reset if it doesn't exist
        if "async def reset_webhook" not in content:
            # Add after imports
            content = re.sub(
                r"(from aiogram import Bot, Dispatcher.*?\n\n)",
                r"\1" + webhook_reset_function,
                content
            )
            
            # Call the function during startup
            content = re.sub(
                r"(# Initialize bot.*?bot = Bot.*?\n)",
                r"\1\n    # Reset webhook\n    await reset_webhook(bot)\n",
                content
            )
            
            logger.info(f"Added webhook reset functionality to {MAIN_BOT_FILE}")
            
        # Write updated content back to file
        with open(MAIN_BOT_FILE, 'w') as file:
            file.write(content)
            
        logger.info(f"Updated {MAIN_BOT_FILE} with improved environment handling")
        return True
            
    except Exception as e:
        logger.error(f"Error updating {MAIN_BOT_FILE}: {e}")
        return False

def create_health_check_file():
    """Create or update health check file for Railway."""
    health_file = "src/health.py"
    
    try:
        health_check_content = '''#!/usr/bin/env python3
"""
Health check endpoint for Railway deployment.
"""

import os
import logging
import sys

# Setup basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

try:
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    
    # Create FastAPI app
    app = FastAPI(title="Allkinds Health Check")

    @app.get("/health")
    async def health_check():
        """Health check endpoint for Railway."""
        return {
            "status": "ok",
            "service": "allkinds",
            "environment": os.environ.get("RAILWAY_ENVIRONMENT", "unknown")
        }

    @app.get("/")
    async def root():
        """Root endpoint redirects to health check."""
        return await health_check()

    if __name__ == "__main__":
        try:
            import uvicorn
            port = int(os.environ.get("PORT", 8080))
            logger.info(f"Starting health check server on port {port}")
            uvicorn.run(app, host="0.0.0.0", port=port)
        except ImportError:
            logger.error("Uvicorn not installed. Falling back to simple HTTP server.")
            from http.server import HTTPServer, BaseHTTPRequestHandler
            
            class SimpleHandler(BaseHTTPRequestHandler):
                def do_GET(self):
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(b'{"status":"ok","service":"allkinds"}')
            
            port = int(os.environ.get("PORT", 8080))
            httpd = HTTPServer(('0.0.0.0', port), SimpleHandler)
            logger.info(f"Starting simple HTTP server on port {port}")
            httpd.serve_forever()
except ImportError:
    # Fallback to simple HTTP server if FastAPI is not available
    logger.warning("FastAPI not installed. Using simple HTTP server instead.")
    from http.server import HTTPServer, BaseHTTPRequestHandler
    
    class SimpleHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status":"ok","service":"allkinds"}')
    
    if __name__ == "__main__":
        port = int(os.environ.get("PORT", 8080))
        httpd = HTTPServer(('0.0.0.0', port), SimpleHandler)
        logger.info(f"Starting simple HTTP server on port {port}")
        httpd.serve_forever()
'''
        
        with open(health_file, 'w') as f:
            f.write(health_check_content)
            
        logger.info(f"Created health check file at {health_file}")
        return True
            
    except Exception as e:
        logger.error(f"Error creating health check file: {e}")
        return False

def create_railway_specific_files():
    """Create Railway-specific files for deployment."""
    # Create Procfile
    procfile_path = "Procfile"
    procfile_content = "web: python -m src.main & python -m src.communicator_bot.main & python -m src.health & wait"
    
    try:
        with open(procfile_path, 'w') as f:
            f.write(procfile_content)
        logger.info(f"Created {procfile_path}")
    except Exception as e:
        logger.error(f"Error creating {procfile_path}: {e}")
        return False
    
    # Create railway.toml
    railway_toml_path = "railway.toml"
    railway_toml_content = """[build]
builder = "nixpacks"
buildCommand = "pip install -r requirements.txt"

[deploy]
startCommand = "python -m src.main & python -m src.communicator_bot.main & python -m src.health & wait"
healthcheckPath = "/health"
healthcheckTimeout = 10
restartPolicyType = "on-failure"
restartPolicyMaxRetries = 5

[nixpacks]
pkgs = ["python310", "gcc", "build-essential", "curl"]
"""
    
    try:
        with open(railway_toml_path, 'w') as f:
            f.write(railway_toml_content)
        logger.info(f"Created {railway_toml_path}")
    except Exception as e:
        logger.error(f"Error creating {railway_toml_path}: {e}")
        return False
    
    return True

def main():
    """Run all fixes in sequence."""
    logger.info("Starting Railway deployment fixes...")
    
    # Track results of each fix
    results = {
        "Config File": fix_config_file(),
        "Database Connection": fix_db_connection(),
        "Communicator Bot": fix_communicator_bot(),
        "Deep Links": fix_deep_links(),
        "Main Bot": fix_main_bot(),
        "Health Check": create_health_check_file(),
        "Railway Files": create_railway_specific_files()
    }
    
    # Count successes and failures
    successes = sum(1 for result in results.values() if result)
    failures = sum(1 for result in results.values() if not result)
    
    # Print summary
    print("\n" + "=" * 50)
    print("RAILWAY DEPLOYMENT FIX SUMMARY")
    print("=" * 50)
    for fix_name, result in results.items():
        print(f"{fix_name}: {'✅ SUCCESS' if result else '❌ FAILED'}")
    print("=" * 50)
    print(f"Total: {successes} succeeded, {failures} failed")
    print("=" * 50)
    
    if failures == 0:
        print("\n✅ All fixes have been applied successfully.")
        print("You can now push these changes to Railway.")
        print("\nReminder: Make sure the following environment variables are set in Railway:")
        print("- BOT_TOKEN")
        print("- COMMUNICATOR_BOT_TOKEN")
        print("- COMMUNICATOR_BOT_USERNAME")
        print("- DATABASE_URL")
        return True
    else:
        print(f"\n⚠️ {failures} fixes could not be applied.")
        print("Please check the logs above for details.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 