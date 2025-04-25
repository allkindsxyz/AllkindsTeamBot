#!/usr/bin/env python
"""
Direct Webhook Reset Script

This script uses direct API calls to Telegram to reset the webhook without needing
to execute it on Railway. You can run this locally.

Usage:
    python direct_reset_webhook.py --token YOUR_BOT_TOKEN --url YOUR_WEBHOOK_URL
"""

import requests
import sys
import logging
import argparse
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def delete_webhook(token):
    """Delete the current webhook."""
    logger.info("Deleting current webhook...")
    
    url = f"https://api.telegram.org/bot{token}/deleteWebhook?drop_pending_updates=true"
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()
        if data.get('ok'):
            logger.info("Webhook successfully deleted")
            return True
        else:
            logger.error(f"Failed to delete webhook: {data.get('description')}")
    else:
        logger.error(f"Error deleting webhook: {response.status_code} - {response.text}")
    
    return False

def set_webhook(token, webhook_url):
    """Set a new webhook."""
    logger.info(f"Setting webhook to: {webhook_url}")
    
    url = f"https://api.telegram.org/bot{token}/setWebhook"
    params = {
        'url': webhook_url,
        'drop_pending_updates': True,
        'allowed_updates': ['message', 'callback_query']
    }
    
    response = requests.post(url, json=params)
    
    if response.status_code == 200:
        data = response.json()
        if data.get('ok'):
            logger.info("Webhook successfully set")
            return True
        else:
            logger.error(f"Failed to set webhook: {data.get('description')}")
    else:
        logger.error(f"Error setting webhook: {response.status_code} - {response.text}")
    
    return False

def check_webhook_info(token):
    """Get information about the current webhook."""
    logger.info("Checking webhook info...")
    
    url = f"https://api.telegram.org/bot{token}/getWebhookInfo"
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()
        if data.get('ok'):
            result = data.get('result', {})
            logger.info(f"Current webhook URL: {result.get('url')}")
            logger.info(f"Has custom certificate: {result.get('has_custom_certificate')}")
            logger.info(f"Pending updates: {result.get('pending_update_count')}")
            logger.info(f"Max connections: {result.get('max_connections')}")
            
            allowed_updates = result.get('allowed_updates', [])
            logger.info(f"Allowed updates: {', '.join(allowed_updates) if allowed_updates else 'All'}")
            
            if result.get('last_error_date'):
                error_date = datetime.fromtimestamp(result['last_error_date'])
                logger.info(f"Last error: {error_date} - {result.get('last_error_message')}")
            
            if result.get('ip_address'):
                logger.info(f"IP Address: {result.get('ip_address')}")
            
            return result
        else:
            logger.error(f"Failed to get webhook info: {data.get('description')}")
    else:
        logger.error(f"Error getting webhook info: {response.status_code} - {response.text}")
    
    return None

def get_bot_info(token):
    """Get information about the bot."""
    logger.info("Getting bot info...")
    
    url = f"https://api.telegram.org/bot{token}/getMe"
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()
        if data.get('ok'):
            result = data.get('result', {})
            logger.info(f"Bot ID: {result.get('id')}")
            logger.info(f"Bot username: @{result.get('username')}")
            logger.info(f"Bot name: {result.get('first_name')}")
            
            return result
        else:
            logger.error(f"Failed to get bot info: {data.get('description')}")
    else:
        logger.error(f"Error getting bot info: {response.status_code} - {response.text}")
    
    return None

def main():
    """Reset the webhook."""
    parser = argparse.ArgumentParser(description='Reset Telegram bot webhook')
    parser.add_argument('--token', required=True, help='Telegram bot token')
    parser.add_argument('--url', required=True, help='Webhook URL')
    parser.add_argument('--check-only', action='store_true', help='Only check webhook status, don\'t modify')
    parser.add_argument('--delete-only', action='store_true', help='Only delete webhook, don\'t set a new one')
    
    args = parser.parse_args()
    
    # Validate the URL
    if not args.url.startswith('https://'):
        logger.error("Webhook URL must start with https://")
        sys.exit(1)
    
    # Get bot info
    bot_info = get_bot_info(args.token)
    if not bot_info:
        logger.error("Failed to get bot info. Please check your token.")
        sys.exit(1)
    
    # Check current webhook
    webhook_info = check_webhook_info(args.token)
    
    # If check only, exit here
    if args.check_only:
        logger.info("Check only mode, exiting without changes")
        return
    
    # Delete current webhook
    if delete_webhook(args.token):
        if args.delete_only:
            logger.info("Delete only mode, webhook deleted successfully")
            return
            
        # Set new webhook
        if set_webhook(args.token, args.url):
            # Check again to verify
            check_webhook_info(args.token)
        else:
            logger.error("Failed to set webhook")
            sys.exit(1)
    else:
        logger.error("Failed to delete webhook")
        sys.exit(1)
    
    logger.info("Webhook reset completed successfully")

if __name__ == "__main__":
    main() 