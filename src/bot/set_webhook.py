#!/usr/bin/env python3
"""
Script to manually check and reset the Telegram webhook.
Run this when the bot isn't receiving updates to verify webhook configuration.
"""

import os
import sys
import asyncio
import logging
import json
from aiogram import Bot
from loguru import logger

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.core.config import get_settings

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)

async def check_and_set_webhook():
    """Check the current webhook status and optionally reset it."""
    settings = get_settings()
    
    # Get bot token from environment or settings
    bot_token = os.environ.get("BOT_TOKEN", settings.BOT_TOKEN)
    if not bot_token:
        logger.error("No BOT_TOKEN provided!")
        return False
    
    # Create bot instance
    bot = Bot(token=bot_token)
    
    try:
        # Check current webhook
        webhook_info = await bot.get_webhook_info()
        logger.info(f"Current webhook URL: {webhook_info.url}")
        logger.info(f"Pending updates: {webhook_info.pending_update_count}")
        logger.info(f"Last error: {webhook_info.last_error_message or 'None'}")
        logger.info(f"Last error date: {webhook_info.last_error_date or 'None'}")
        
        # Get possible webhook domains
        webhook_domain = os.environ.get("WEBHOOK_DOMAIN")
        railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN")
        railway_url = os.environ.get("RAILWAY_PUBLIC_URL")
        
        logger.info(f"WEBHOOK_DOMAIN: {webhook_domain or 'Not set'}")
        logger.info(f"RAILWAY_PUBLIC_DOMAIN: {railway_domain or 'Not set'}")
        logger.info(f"RAILWAY_PUBLIC_URL: {railway_url or 'Not set'}")
        
        # Display menu options
        print("\nOptions:")
        print("1. Reset webhook")
        print("2. Delete command menu")
        print("3. Check recent updates")
        print("4. Quit")
        
        choice = input("\nEnter choice (1-4): ")
        
        if choice == '1':
            # Delete current webhook
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("Deleted current webhook")
            
            # Choose which domain to use
            domain = None
            
            if webhook_domain:
                domain = webhook_domain
                logger.info(f"Using WEBHOOK_DOMAIN: {domain}")
            elif railway_domain:
                domain = railway_domain
                logger.info(f"Using RAILWAY_PUBLIC_DOMAIN: {domain}")
            elif railway_url:
                domain = railway_url
                logger.info(f"Using RAILWAY_PUBLIC_URL: {domain}")
            else:
                domain = input("Enter webhook domain (without https://): ")
                if not domain:
                    logger.error("No domain provided. Webhook not set.")
                    return False
            
            # Set the webhook
            webhook_path = f"/webhook/{bot_token}"
            webhook_url = f"https://{domain}{webhook_path}"
            
            await bot.set_webhook(webhook_url)
            logger.info(f"Webhook set to: {webhook_url}")
            
            # Verify new webhook
            webhook_info = await bot.get_webhook_info()
            logger.info(f"New webhook URL: {webhook_info.url}")
        
        elif choice == '2':
            # Delete bot commands menu
            await bot.delete_my_commands()
            logger.info("Bot commands menu removed successfully")
            
        elif choice == '3':
            # Check for recent updates
            logger.info("Checking for recent updates...")
            try:
                updates = await bot.get_updates(limit=10, timeout=5)
                if updates:
                    logger.info(f"Found {len(updates)} recent updates")
                    for update in updates:
                        logger.info(f"Update ID: {update.update_id}")
                        if update.message:
                            logger.info(f"Message from {update.message.from_user.id}: {update.message.text}")
                        if update.callback_query:
                            logger.info(f"Callback query from {update.callback_query.from_user.id}: {update.callback_query.data}")
                else:
                    logger.info("No recent updates found")
            except Exception as e:
                logger.error(f"Error getting updates: {e}")
        
        else:
            logger.info("Exiting without changes")
            
        return True
    except Exception as e:
        logger.error(f"Error: {e}")
        return False
    finally:
        # Close the bot session
        await bot.session.close()


if __name__ == "__main__":
    try:
        success = asyncio.run(check_and_set_webhook())
        if success:
            logger.info("Operation completed successfully")
        else:
            logger.error("Operation failed")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Unhandled error: {e}")
        sys.exit(1) 