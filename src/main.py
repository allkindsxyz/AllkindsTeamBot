#!/usr/bin/env python3
"""
Main entry point for Allkinds Team Bot
"""

import asyncio
import logging
import sys
import os
import signal
import subprocess
from loguru import logger
import time

# Configure logging
log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
logging.basicConfig(level=logging.INFO, format=log_format)
logger.remove()
logger.add(sys.stderr, level="INFO")
logger.add("logs/allkinds_bot_{time}.log", rotation="10 MB", level="DEBUG")

# Import must be done after logging setup
from src.bot.main import start_bot as start_main_bot
from src.communicator_bot.main import start_communicator_bot
from src.core.config import get_settings

# Signal handler for graceful shutdown
async def shutdown(signal_name=None):
    """Shutdown all bots gracefully."""
    if signal_name:
        logger.info(f"Received {signal_name}, shutting down...")
    
    # Perform any cleanup here
    logger.info("Shutting down...")
    
    # Exit the process
    asyncio.get_event_loop().stop()

def setup_signal_handlers():
    """Set up signal handlers for graceful shutdown."""
    for sig_name in ('SIGINT', 'SIGTERM'):
        asyncio.get_event_loop().add_signal_handler(
            getattr(signal, sig_name),
            lambda sig_name=sig_name: asyncio.create_task(shutdown(sig_name))
        )

def get_webhook_url():
    """Get the webhook URL from environment or settings."""
    # Try to get from environment first
    webhook_host = os.environ.get("WEBHOOK_HOST")
    if not webhook_host:
        # Try Railway's static URL
        railway_url = os.environ.get("RAILWAY_PUBLIC_DOMAIN")
        if railway_url:
            webhook_host = f"https://{railway_url}"
            logger.info(f"Using Railway public domain: {webhook_host}")
        else:
            # Fallback to settings
            settings = get_settings()
            webhook_host = settings.WEBHOOK_HOST
            logger.info(f"Using webhook host from settings: {webhook_host}")
    else:
        logger.info(f"Using webhook host from environment: {webhook_host}")
    
    return webhook_host
    
async def setup_simple_health_check(port=8080):
    """Set up a simple health check endpoint."""
    from aiohttp import web
    
    app = web.Application()
    
    async def health_handler(request):
        """Simple health check endpoint."""
        return web.Response(text='{"status":"ok","service":"allkinds"}',
                          content_type='application/json')
                          
    app.router.add_get("/health", health_handler)
    app.router.add_get("/", health_handler)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    
    logger.info(f"Health check server running on port {port}")
    
    try:
        # Keep the task running
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        logger.info("Health check server task cancelled")
        await runner.cleanup()

async def main():
    """Main entry point for all bots."""
    # Setup signal handlers
    setup_signal_handlers()
    
    # Log environment variables (safely)
    logger.info("Checking environment variables:")
    env_vars = {
        "BOT_TOKEN": bool(os.environ.get("BOT_TOKEN")),
        "COMMUNICATOR_BOT_TOKEN": bool(os.environ.get("COMMUNICATOR_BOT_TOKEN")),
        "COMMUNICATOR_BOT_USERNAME": os.environ.get("COMMUNICATOR_BOT_USERNAME", "Not set"),
        "WEBHOOK_HOST": os.environ.get("WEBHOOK_HOST", "Not set"),
        "RAILWAY_PUBLIC_DOMAIN": os.environ.get("RAILWAY_PUBLIC_DOMAIN", "Not set"),
        "RAILWAY_ENVIRONMENT": os.environ.get("RAILWAY_ENVIRONMENT", "Not set"),
        "PORT": os.environ.get("PORT", "Not set")
    }
    for var, value in env_vars.items():
        if isinstance(value, bool):
            logger.info(f"  {var}: {'Set' if value else 'Not set'}")
        else:
            logger.info(f"  {var}: {value}")
            
    # Get webhook URL for Railway
    webhook_url = get_webhook_url()
    logger.info(f"Webhook URL: {webhook_url}")
    
    # Set environment variables for children processes
    os.environ["WEBHOOK_HOST"] = webhook_url
    os.environ["WEBHOOK_PATH"] = "/webhook"
    
    # Start health check in a separate task
    health_port = int(os.environ.get("PORT", 8080))
    health_task = asyncio.create_task(setup_simple_health_check(health_port))
    logger.info(f"Started health check on port {health_port}")
    
    try:
        # Start the main bot in a separate task
        logger.info("Starting Allkinds Team Bot...")
        main_bot_task = asyncio.create_task(start_main_bot())
        
        # Start the communicator bot in a separate task
        logger.info("Starting Communicator Bot...")
        communicator_bot_task = asyncio.create_task(start_communicator_bot())
        
        # Wait for both tasks to complete
        await asyncio.gather(main_bot_task, communicator_bot_task)
    except Exception as e:
        logger.exception(f"Unhandled exception: {e}")
    finally:
        # Cancel health check task
        health_task.cancel()
        try:
            await health_task
        except asyncio.CancelledError:
            pass
        
        logger.info("All bots shutdown complete")

if __name__ == "__main__":
    # Run the main function
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bots stopped by keyboard interrupt")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1) 