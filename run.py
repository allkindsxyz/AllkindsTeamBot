import asyncio
import os
import sys
import signal
import datetime
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
    # Register signal handlers
    signal.signal(signal.SIGINT, handle_termination)
    signal.signal(signal.SIGTERM, handle_termination)
    
    if is_already_running():
        logger.error("Another instance is already running. Exiting.")
        sys.exit(1)
        
    if not create_pid_file():
        logger.error("Failed to create PID file. Exiting.")
        sys.exit(1)
        
    try:
        await init_db()
        await start_bot()
    except Exception as e:
        logger.exception("Bot stopped with error")
        raise
    finally:
        remove_pid_file()


if __name__ == "__main__":
    asyncio.run(main()) 