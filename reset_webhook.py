#!/usr/bin/env python
"""
Simple Telegram Bot Webhook Reset Script

This script deletes the current webhook and sets a new one using the WEBHOOK_DOMAIN environment variable.
It's designed to be run directly on Railway to fix webhook issues.
"""

import os
import requests
import sys
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_token():
    """Get the bot token from environment."""
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN environment variable not found")
        sys.exit(1)
    return token

def get_webhook_url():
    """Construct the webhook URL based on environment variables."""
    webhook_domain = os.environ.get('WEBHOOK_DOMAIN') or os.environ.get('RAILWAY_PUBLIC_URL')
    if not webhook_domain:
        logger.error("No webhook domain found. Set WEBHOOK_DOMAIN or use Railway.")
        sys.exit(1)
        
    # Ensure it has https://
    if not webhook_domain.startswith('http'):
        webhook_domain = f'https://{webhook_domain}'
    
    # Remove trailing slash if present
    webhook_domain = webhook_domain.rstrip('/')
    
    # Get token
    token = get_token()
    
    # Construct webhook path
    return f"{webhook_domain}/webhook/{token}"

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
        'drop_pending_updates': True
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
            logger.info(f"Pending updates: {result.get('pending_update_count')}")
            
            if result.get('last_error_date'):
                from datetime import datetime
                error_date = datetime.fromtimestamp(result['last_error_date'])
                logger.info(f"Last error: {error_date} - {result.get('last_error_message')}")
            
            return result
        else:
            logger.error(f"Failed to get webhook info: {data.get('description')}")
    else:
        logger.error(f"Error getting webhook info: {response.status_code} - {response.text}")
    
    return None

def main():
    """Reset the webhook."""
    logger.info("Starting webhook reset...")
    
    # Get token
    token = get_token()
    
    # Check current webhook
    check_webhook_info(token)
    
    # Delete current webhook
    if delete_webhook(token):
        # Set new webhook
        webhook_url = get_webhook_url()
        logger.info(f"Using webhook URL: {webhook_url}")
        
        if set_webhook(token, webhook_url):
            # Check again to verify
            check_webhook_info(token)
        else:
            logger.error("Failed to set webhook")
    else:
        logger.error("Failed to delete webhook")

if __name__ == "__main__":
    main() 