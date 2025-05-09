#!/usr/bin/env python3
"""
Simple script to start the Allkinds bot locally.
"""

import asyncio
import logging
import sys
import os
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Make sure .env is loaded
if not load_dotenv():
    logger.warning(".env file not found or empty. Make sure environment variables are set.")

# Check if BOT_TOKEN is available
if not os.environ.get("BOT_TOKEN"):
    logger.error("BOT_TOKEN environment variable is not set!")
    logger.info("Please set BOT_TOKEN in your .env file or environment.")
    sys.exit(1)

# Force polling mode for local development
os.environ["USE_WEBHOOK"] = "false"

async def main():
    """Import and start the main bot."""
    try:
        # Import here to ensure .env is loaded first
        from src.main import main as start_bot
        await start_bot()
    except ImportError as e:
        logger.error(f"Failed to import necessary modules: {e}")
        logger.info("Make sure all dependencies are installed.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by keyboard interrupt")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1) 