import asyncio
import os
import sys
import signal
import datetime
import traceback
from pathlib import Path
from loguru import logger

from src.bot.main import start_bot
from src.db.init_db import init_db

# Configure logger to write to console and file
logger.remove()  # Remove default handler
logger.add(sys.stderr, level="INFO")  # Console output
logger.add(
    "logs/allkinds_bot_{time}.log",
    rotation="1 day",
    retention="7 days",
    compression="zip",
    level="DEBUG"
)

def get_pid_file_path() -> Path:
    """Get the path to the PID file."""
    return Path.home() / ".allkinds_bot.pid"


def is_already_running() -> bool:
    """Check if another instance is already running."""
    # Skip this check on Railway as we have auto-restart policies
    if os.environ.get("RAILWAY_ENVIRONMENT") == "production":
        return False
        
    pid_file = get_pid_file_path()
    
    if not pid_file.exists():
        return False
        
    try:
        with pid_file.open() as f:
            pid = int(f.read().strip())
            
        # Check if process exists
        try:
            os.kill(pid, 0)  # Signal 0 just checks if process exists
            return True
        except OSError:
            # Process doesn't exist, remove stale PID file
            pid_file.unlink()
            return False
    except Exception as e:
        logger.error(f"Error checking PID file: {e}")
        return False


def create_pid_file() -> bool:
    """Create PID file with current process ID."""
    # Skip on Railway
    if os.environ.get("RAILWAY_ENVIRONMENT") == "production":
        return True
        
    try:
        pid_file = get_pid_file_path()
        with pid_file.open('w') as f:
            f.write(str(os.getpid()))
        return True
    except Exception as e:
        logger.error(f"Error creating PID file: {e}")
        return False


def remove_pid_file() -> None:
    """Remove PID file."""
    # Skip on Railway
    if os.environ.get("RAILWAY_ENVIRONMENT") == "production":
        return
        
    try:
        pid_file = get_pid_file_path()
        if pid_file.exists():
            pid_file.unlink()
    except Exception as e:
        logger.error(f"Error removing PID file: {e}")


def handle_termination(signum, frame):
    """Handle termination signals."""
    logger.info("Received termination signal, cleaning up...")
    remove_pid_file()
    sys.exit(0)


async def main() -> None:
    """Main entry point."""
    logger.info("=== STARTING BOT APPLICATION ===")
    
    # Register signal handlers
    signal.signal(signal.SIGINT, handle_termination)
    signal.signal(signal.SIGTERM, handle_termination)
    
    # Log information about the environment
    is_railway = os.environ.get("RAILWAY_ENVIRONMENT") == "production"
    logger.info(f"Running in Railway: {is_railway}")
    if is_railway:
        logger.info(f"Railway Public URL: {os.environ.get('RAILWAY_PUBLIC_URL', 'Not set')}")
        logger.info(f"Webhook Domain: {os.environ.get('WEBHOOK_DOMAIN', 'Not set')}")
        logger.info(f"Port: {os.environ.get('PORT', 'Not set')}")
    
    if is_already_running():
        logger.error("Another instance is already running. Exiting.")
        sys.exit(1)
        
    if not create_pid_file():
        logger.error("Failed to create PID file. Exiting.")
        sys.exit(1)
        
    try:
        # Initialize database
        logger.info("Initializing database...")
        try:
            await init_db()
            logger.info("Database initialization completed successfully")
        except Exception as e:
            logger.error(f"Database initialization error: {str(e)}")
            logger.error(traceback.format_exc())
            if not is_railway:
                # In local development, fail immediately
                raise
            # On Railway, try to continue anyway
            logger.warning("Continuing despite database initialization error")
        
        # Start the bot
        logger.info("Starting bot...")
        await start_bot()
    except Exception as e:
        logger.exception(f"Bot stopped with error: {str(e)}")
        if is_railway:
            # On Railway, sleep for a bit to prevent immediate restarts
            logger.error("Sleeping for 10 seconds before exiting to prevent rapid restarts...")
            await asyncio.sleep(10)
        raise
    finally:
        remove_pid_file()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Fatal error in main: {str(e)}")
        logger.error(traceback.format_exc())
        sys.exit(1) 