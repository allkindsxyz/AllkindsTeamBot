#!/usr/bin/env python3
"""
Main entry point for Allkinds Team Bot
"""

import asyncio
import logging
import sys
import os
from loguru import logger
import signal
from aiohttp import web

# Configure logging
log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
logging.basicConfig(level=logging.INFO, format=log_format)
logger.remove()
logger.add(sys.stderr, level="INFO")
logger.add("logs/allkinds_bot_{time}.log", rotation="10 MB", level="DEBUG")

# Import must be done after logging setup
from src.bot.main import start_bot
from src.core.config import get_settings

# Setup health check server for Railway
async def setup_health_server():
    """Create a simple health check server for Railway."""
    port = os.environ.get("PORT", "8080")
    
    # Create a simple health check endpoint
    async def health_handler(request):
        """Handler for health endpoint."""
        logger.debug("Health check received")
        return web.Response(text='{"status": "ok", "service": "allkinds"}', 
                          content_type='application/json')
    
    app = web.Application()
    app.router.add_get("/health", health_handler)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(port))
    
    try:
        await site.start()
        logger.info(f"Health check server running on port {port}")
        
        # Keep running until cancelled
        while True:
            await asyncio.sleep(3600)  # Sleep for an hour
    except asyncio.CancelledError:
        logger.info("Health check server task cancelled")
    finally:
        logger.info("Shutting down health check server")
        await runner.cleanup()

# Signal handler for graceful shutdown
async def shutdown(signal_name=None):
    """Shutdown the bot gracefully."""
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

async def main():
    """Main entry point for the bot."""
    # Setup signal handlers
    setup_signal_handlers()
    
    # Start the health check server in a separate task
    health_task = asyncio.create_task(setup_health_server())
    
    try:
        # Start the main bot
        logger.info("Starting Allkinds Team Bot...")
        settings = get_settings()
        
        # Log version and environment info
        logger.info(f"Running in {'production' if settings.is_production else 'development'} mode")
        logger.info(f"Using database: {settings.db_url[:10]}...")
        
        # Start the bot
        await start_bot()
    except KeyboardInterrupt:
        logger.info("Bot stopped by keyboard interrupt")
    except Exception as e:
        logger.exception(f"Unhandled exception: {e}")
    finally:
        # Cancel health check task
        health_task.cancel()
        try:
            await health_task
        except asyncio.CancelledError:
            pass
        
        logger.info("Bot shutdown complete")

if __name__ == "__main__":
    # Run the main function
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by keyboard interrupt")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1) 