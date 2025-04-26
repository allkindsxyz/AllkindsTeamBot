#!/usr/bin/env python3
"""
Direct webhook reset script for Allkinds bot.
This bypasses the environment variables and directly
deletes and optionally sets a webhook with the provided token and URL.
"""

import sys
import json
import argparse
import requests
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

def delete_webhook(token):
    """Delete the webhook for the bot"""
    logger.info("Deleting webhook...")
    url = f"https://api.telegram.org/bot{token}/deleteWebhook?drop_pending_updates=true"
    
    try:
        response = requests.get(url)
        data = response.json()
        
        if data.get('ok'):
            logger.info("✅ Webhook deleted successfully!")
            return True
        else:
            logger.error(f"❌ Failed to delete webhook: {data.get('description')}")
            return False
    except Exception as e:
        logger.error(f"❌ Error deleting webhook: {e}")
        return False

def set_webhook(token, webhook_url):
    """Set a new webhook for the bot"""
    if not webhook_url:
        logger.info("No webhook URL provided, not setting a new webhook.")
        return True
        
    logger.info(f"Setting webhook to: {webhook_url}")
    url = f"https://api.telegram.org/bot{token}/setWebhook"
    params = {
        "url": webhook_url,
        "drop_pending_updates": True,
        "max_connections": 100,
        "allowed_updates": ["message", "edited_message", "callback_query"]
    }
    
    try:
        response = requests.post(url, json=params)
        data = response.json()
        
        if data.get('ok'):
            logger.info("✅ Webhook set successfully!")
            return True
        else:
            logger.error(f"❌ Failed to set webhook: {data.get('description')}")
            return False
    except Exception as e:
        logger.error(f"❌ Error setting webhook: {e}")
        return False

def get_webhook_info(token):
    """Get current webhook info"""
    logger.info("Getting webhook info...")
    url = f"https://api.telegram.org/bot{token}/getWebhookInfo"
    
    try:
        response = requests.get(url)
        data = response.json()
        
        if data.get('ok'):
            webhook_info = data.get('result', {})
            logger.info("Current webhook information:")
            logger.info(f"URL: {webhook_info.get('url', 'Not set')}")
            logger.info(f"Pending updates: {webhook_info.get('pending_update_count', 0)}")
            has_custom_cert = webhook_info.get('has_custom_certificate', False)
            logger.info(f"Has custom certificate: {has_custom_cert}")
            logger.info(f"Last error date: {webhook_info.get('last_error_date', 'None')}")
            logger.info(f"Last error message: {webhook_info.get('last_error_message', 'None')}")
            return webhook_info
        else:
            logger.error(f"❌ Failed to get webhook info: {data.get('description')}")
            return None
    except Exception as e:
        logger.error(f"❌ Error getting webhook info: {e}")
        return None

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Reset webhook for Telegram bot')
    parser.add_argument('--token', required=True, help='Bot token')
    parser.add_argument('--url', required=False, help='Webhook URL to set (optional)')
    return parser.parse_args()

def main():
    """Main function"""
    args = parse_args()
    
    # Ensure valid token
    if not args.token or ":" not in args.token:
        logger.error("Invalid token format. Must be in format 123456789:ABC...XYZ")
        return 1
    
    # Get current webhook info
    current_info = get_webhook_info(args.token)
    
    # Delete webhook
    if not delete_webhook(args.token):
        logger.error("Failed to delete webhook. Check bot token.")
        return 1
    
    # Set new webhook if URL provided
    if args.url:
        if not set_webhook(args.token, args.url):
            logger.error("Failed to set webhook.")
            return 1
    
    # Get updated webhook info
    updated_info = get_webhook_info(args.token)
    
    return 0

if __name__ == "__main__":
    if len(sys.argv) == 1:
        # Show usage example if no args
        print("Usage examples:")
        print("    python direct_reset_webhook.py --token YOUR_BOT_TOKEN --url YOUR_WEBHOOK_URL")
        print("    python direct_reset_webhook.py --token YOUR_BOT_TOKEN")  # Delete only
        print("\nThe correct token for @allkindsteam_bot is: 7910000886:AAHwuYKz8je_JSrpf53lXX8S6V5mfTqLd6Y")
        sys.exit(1)
        
    sys.exit(main()) 