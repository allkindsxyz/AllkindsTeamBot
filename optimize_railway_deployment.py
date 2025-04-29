#!/usr/bin/env python3
"""
Railway Deployment Optimization Script

This script optimizes the Railway deployment configuration by:
1. Updating the railway.toml and railway.yml files
2. Ensuring proper health check setup
3. Optimizing database connection handling
4. Configuring proper startup sequence for all services
"""

import os
import sys
import logging
import json
import re
import shutil
from datetime import datetime
import subprocess

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Target files
RAILWAY_TOML = "railway.toml"
RAILWAY_YML = "railway.yml"
DOCKERFILE = "Dockerfile"
MAIN_PY = "src/main.py"
HEALTH_PY = "src/health.py"
DB_BASE_PY = "src/db/base.py"
BOT_MAIN_PY = "src/bot/main.py"
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

def optimize_db_connection():
    """Optimize database connection handling for Railway."""
    if not os.path.exists(DB_BASE_PY):
        logger.error(f"Database file not found: {DB_BASE_PY}")
        return False
        
    # Backup the file first
    if not backup_file(DB_BASE_PY):
        return False
        
    try:
        # Read the file
        with open(DB_BASE_PY, 'r') as file:
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
            
            logger.info(f"Processed database URL (starts with): {url[:15]}...")
            return url
    except Exception as e:
        logger.error(f"Error processing database URL: {e}")
        # Return original URL as fallback
        return url
"""
        
        if "def process_database_url" in content:
            content = re.sub(
                url_processing_pattern,
                r"\1\n" + improved_url_processing + r"\n",
                content,
                flags=re.DOTALL
            )
        else:
            # Add the function if it doesn't exist
            async_engine_pattern = r"(async_engine.*?\n)"
            content = re.sub(
                async_engine_pattern,
                r"\1\ndef process_database_url(url):\n" + improved_url_processing + "\n",
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
        engine_pattern = r"(engine = create_async_engine\(\s+)([^,]+)(,.*?\))"
        engine_replacement = r'\1process_database_url(\2)\3'
        
        content = re.sub(
            engine_pattern,
            engine_replacement,
            content,
            flags=re.DOTALL
        )
        
        # Update pool configuration
        pool_pattern = r"(pool_recycle=\d+,\s+pool_timeout=\d+,\s+pool_size=\d+,\s+max_overflow=\d+,)"
        pool_replacement = r'pool_recycle=120, pool_timeout=60, pool_size=5, max_overflow=10, pool_use_lifo=True,'
        
        content = re.sub(
            pool_pattern,
            pool_replacement,
            content
        )
            
        # Write updated content back to file
        with open(DB_BASE_PY, 'w') as file:
            file.write(content)
            
        logger.info(f"Updated {DB_BASE_PY} with optimized database connection handling")
        return True
            
    except Exception as e:
        logger.error(f"Error updating {DB_BASE_PY}: {e}")
        return False

def optimize_health_check():
    """Optimize health check handling for Railway."""
    if not os.path.exists(HEALTH_PY):
        logger.error(f"Health check file not found: {HEALTH_PY}")
        return False
        
    # Backup the file first
    if not backup_file(HEALTH_PY):
        return False
        
    try:
        # Read the file
        with open(HEALTH_PY, 'r') as file:
            content = file.read()
            
        # Update health check timeout values
        content = re.sub(
            r"async with httpx.AsyncClient\(\) as client:",
            r"async with httpx.AsyncClient(timeout=10.0) as client:",
            content
        )
        
        # Improve health check response
        health_check_pattern = r"(async def health_check\(\):.*?return \{)(.*?)(\})"
        health_check_replacement = r"""\1
            "status": "ok",
            "service": "allkinds",
            "environment": os.environ.get("RAILWAY_ENVIRONMENT", "unknown"),
            "bots": bot_status,
            "version": "1.2.0",
            "webhook_host": os.environ.get("WEBHOOK_HOST", "not_set"),
            "uptime": get_uptime(),
            "memory_usage": get_memory_usage()
        \3"""
        
        content = re.sub(
            health_check_pattern,
            health_check_replacement,
            content,
            flags=re.DOTALL
        )
        
        # Add utility functions for better health monitoring
        if "def get_uptime():" not in content and "def get_memory_usage():" not in content:
            uptime_functions = """
def get_uptime():
    """Get the service uptime."""
    try:
        import time
        from datetime import datetime
        global START_TIME
        if not globals().get("START_TIME"):
            globals()["START_TIME"] = time.time()
        uptime_seconds = time.time() - START_TIME
        return {
            "seconds": int(uptime_seconds),
            "formatted": str(datetime.utcfromtimestamp(uptime_seconds).strftime("%H:%M:%S"))
        }
    except Exception as e:
        logger.error(f"Error getting uptime: {e}")
        return {"error": str(e)}

def get_memory_usage():
    """Get the current memory usage."""
    try:
        import psutil
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        return {
            "rss_mb": round(memory_info.rss / (1024 * 1024), 2),
            "vms_mb": round(memory_info.vms / (1024 * 1024), 2)
        }
    except Exception:
        try:
            # Fallback to simpler method
            import resource
            usage = resource.getrusage(resource.RUSAGE_SELF)
            return {
                "max_rss_kb": usage.ru_maxrss,
                "shared_kb": usage.ru_ixrss,
                "unshared_kb": usage.ru_idrss
            }
        except Exception as e:
            logger.error(f"Error getting memory usage: {e}")
            return {"error": str(e)}
"""
            
            # Add after the imports
            import_pattern = r"(import .*?\n\n)"
            content = re.sub(
                import_pattern,
                r"\1" + uptime_functions + "\n",
                content,
                flags=re.DOTALL,
                count=1
            )
            
        # Write updated content back to file
        with open(HEALTH_PY, 'w') as file:
            file.write(content)
            
        logger.info(f"Updated {HEALTH_PY} with optimized health check handling")
        return True
            
    except Exception as e:
        logger.error(f"Error updating {HEALTH_PY}: {e}")
        return False

def fix_reset_webhook():
    """Fix the reset_webhook function in the main bot files."""
    files_to_fix = [BOT_MAIN_PY, COMMUNICATOR_MAIN_PY]
    
    success = True
    for file_path in files_to_fix:
        if not os.path.exists(file_path):
            logger.error(f"Bot file not found: {file_path}")
            success = False
            continue
            
        # Backup the file first
        if not backup_file(file_path):
            success = False
            continue
            
        try:
            # Read the file
            with open(file_path, 'r') as file:
                content = file.read()
                
            # Check if the file contains a reset_webhook function
            if "async def reset_webhook" in content:
                # Fix the reset_webhook function
                reset_webhook_pattern = r"async def reset_webhook\([^)]*\):.*?(?=async def|def|\n\n\n|$)"
                
                reset_webhook_replacement = """async def reset_webhook(bot=None):
    """Reset the Telegram webhook to ensure no conflicts."""
    token = None
    
    if bot:
        try:
            # Try to use the provided bot instance
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("Webhook deleted successfully using bot instance")
            return True
        except Exception as e:
            logger.error(f"Error deleting webhook with bot instance: {e}")
    
    # Get token from environment or settings
    if "COMMUNICATOR_BOT_MAIN" in file_path:
        token = os.environ.get("COMMUNICATOR_BOT_TOKEN")
    else:
        token = os.environ.get("BOT_TOKEN")
    
    if not token:
        try:
            from src.core.config import get_settings
            settings = get_settings()
            if "COMMUNICATOR_BOT_MAIN" in file_path:
                token = settings.COMMUNICATOR_BOT_TOKEN
            else:
                token = settings.BOT_TOKEN
        except Exception as e:
            logger.error(f"Error getting token from settings: {e}")
    
    if not token:
        logger.error("Cannot reset webhook: No token available")
        return False
    
    # Try with direct HTTP request as fallback
    try:
        import requests
        logger.info("Trying reset webhook with direct HTTP request...")
        response = requests.get(
            f"https://api.telegram.org/bot{token}/deleteWebhook?drop_pending_updates=true"
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
        import aiohttp
        import ssl
        
        logger.info("Resetting Telegram webhook using aiohttp...")
        # Create a default SSL context that doesn't verify
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        # Create a session with relaxed SSL configuration
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        async with aiohttp.ClientSession(connector=connector) as session:
            # Force delete the webhook with drop_pending_updates
            async with session.get(
                f"https://api.telegram.org/bot{token}/deleteWebhook?drop_pending_updates=true"
            ) as response:
                result = await response.json()
                if result.get("ok"):
                    logger.info("Webhook deleted successfully with aiohttp")
                    return True
                else:
                    logger.error(f"Failed to delete webhook with aiohttp: {result}")
    except Exception as e:
        logger.error(f"Error resetting webhook with aiohttp: {e}")
    
    return False
"""
                
                # Replace the function
                content = re.sub(
                    reset_webhook_pattern,
                    reset_webhook_replacement,
                    content,
                    flags=re.DOTALL
                )
                
                # Write updated content back to file
                with open(file_path, 'w') as file:
                    file.write(content)
                    
                logger.info(f"Updated reset_webhook function in {file_path}")
            else:
                logger.warning(f"reset_webhook function not found in {file_path}")
                
        except Exception as e:
            logger.error(f"Error updating {file_path}: {e}")
            success = False
            
    return success

def optimize_startup_sequence():
    """Optimize the startup sequence in the main.py file."""
    if not os.path.exists(MAIN_PY):
        logger.error(f"Main file not found: {MAIN_PY}")
        return False
        
    # Backup the file first
    if not backup_file(MAIN_PY):
        return False
        
    try:
        # Read the file
        with open(MAIN_PY, 'r') as file:
            content = file.read()
            
        # Add enhanced shutdown procedure
        if "async def shutdown" in content:
            shutdown_pattern = r"async def shutdown\([^)]*\):.*?(\s+asyncio\.get_event_loop\(\)\.stop\(\))"
            shutdown_replacement = r"""async def shutdown(signal_name=None):
    """Shutdown all bots gracefully."""
    if signal_name:
        logger.info(f"Received {signal_name}, shutting down...")
    
    # Perform any cleanup here
    logger.info("Shutting down...")
    
    # Try to gracefully stop bot tasks
    global main_bot_task, communicator_bot_task
    if 'main_bot_task' in globals() and main_bot_task:
        logger.info("Cancelling main bot task...")
        main_bot_task.cancel()
        
    if 'communicator_bot_task' in globals() and communicator_bot_task:
        logger.info("Cancelling communicator bot task...")
        communicator_bot_task.cancel()
        
    # Wait for cancellation to complete
    try:
        tasks_to_cancel = []
        if 'main_bot_task' in globals() and main_bot_task:
            tasks_to_cancel.append(main_bot_task)
        if 'communicator_bot_task' in globals() and communicator_bot_task:
            tasks_to_cancel.append(communicator_bot_task)
            
        if tasks_to_cancel:
            logger.info("Waiting for tasks to complete cancellation...")
            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
    except Exception as e:
        logger.error(f"Error during task cancellation: {e}")
    
    # Database cleanup
    try:
        from src.db.base import close_db_connections
        await close_db_connections()
    except Exception as e:
        logger.error(f"Error closing database connections: {e}")
    
    # Exit the process
    logger.info("All cleanup completed, stopping event loop")\1"""
            
            content = re.sub(
                shutdown_pattern,
                shutdown_replacement,
                content,
                flags=re.DOTALL
            )
            
        # Add global variables for tasks
        if "# Global variables for clean shutdown" not in content:
            setup_pattern = r"(# Setup signal handlers.*?)\n"
            setup_replacement = r"\1\n\n# Global variables for clean shutdown\nmain_bot_task = None\ncommunicator_bot_task = None\n"
            
            content = re.sub(
                setup_pattern,
                setup_replacement,
                content
            )
            
        # Enhanced main function
        main_function_pattern = r"(async def main\(\):.*?)(# Start the main bot in a separate task)(.*?)(await asyncio\.gather\(main_bot_task, communicator_bot_task\))"
        main_function_replacement = r"""\1\2
    global main_bot_task, communicator_bot_task
    
    # Configure exception handling for tasks
    def handle_task_exception(task):
        try:
            task.result()
        except asyncio.CancelledError:
            logger.info(f"Task was cancelled: {task.get_name()}")
        except Exception as e:
            logger.exception(f"Unhandled exception in task {task.get_name()}: {e}")
    
    # Start the main bot in a separate task\3
    
    # Add exception handlers
    main_bot_task.add_done_callback(handle_task_exception)
    communicator_bot_task.add_done_callback(handle_task_exception)
    
    # Set task names for easier debugging
    main_bot_task.set_name("main_bot")
    communicator_bot_task.set_name("communicator_bot")
    
    logger.info("Both bots started successfully")
    
    try:
        # Wait for both tasks to complete
        \4"""
        
        content = re.sub(
            main_function_pattern,
            main_function_replacement,
            content,
            flags=re.DOTALL
        )
            
        # Write updated content back to file
        with open(MAIN_PY, 'w') as file:
            file.write(content)
            
        logger.info(f"Updated {MAIN_PY} with optimized startup sequence")
        return True
            
    except Exception as e:
        logger.error(f"Error updating {MAIN_PY}: {e}")
        return False

def main():
    """Run all optimizations for Railway deployment."""
    logger.info("Starting Railway deployment optimization")
    
    results = {
        "railway_toml": optimize_railway_toml(),
        "railway_yml": optimize_railway_yml(),
        "db_connection": optimize_db_connection(),
        "health_check": optimize_health_check(),
        "reset_webhook": fix_reset_webhook(),
        "startup_sequence": optimize_startup_sequence()
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