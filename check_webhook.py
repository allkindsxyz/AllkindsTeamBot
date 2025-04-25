#!/usr/bin/env python
"""
Telegram Bot Webhook Verification and Reset Tool

This script helps diagnose webhook issues and can reset the webhook if needed.
Usage:
    python check_webhook.py                   # Check webhook status
    python check_webhook.py --reset           # Reset webhook
    python check_webhook.py --delete          # Delete webhook
    python check_webhook.py --set <url>       # Set webhook to specified URL
"""

import requests
import os
import sys
import argparse
import json
from urllib.parse import urljoin

def get_token():
    """Get the bot token from environment variables."""
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN environment variable not found.")
        print("Please set it before running this script.")
        sys.exit(1)
    return token

def get_webhook_url():
    """Get the webhook URL from environment variables or build it."""
    # Try to use WEBHOOK_DOMAIN environment variable
    webhook_domain = os.environ.get('WEBHOOK_DOMAIN')
    if webhook_domain:
        # Clean it up
        if not webhook_domain.startswith('http'):
            webhook_domain = f"https://{webhook_domain}"
        # Remove trailing slash
        webhook_domain = webhook_domain.rstrip('/')
        
        # Get token
        token = get_token()
        
        # Build webhook path
        webhook_path = f"/webhook/{token}"
        
        # Combine
        return f"{webhook_domain}{webhook_path}"
    
    # Fallback to RAILWAY_PUBLIC_URL
    railway_url = os.environ.get('RAILWAY_PUBLIC_URL')
    if railway_url:
        # Clean it up
        if not railway_url.startswith('http'):
            railway_url = f"https://{railway_url}"
        # Remove trailing slash
        railway_url = railway_url.rstrip('/')
        
        # Get token
        token = get_token()
        
        # Build webhook path
        webhook_path = f"/webhook/{token}"
        
        # Combine
        return f"{railway_url}{webhook_path}"
    
    # If all else fails, ask user
    print("No webhook URL found in environment variables.")
    print("Please enter the webhook URL:")
    return input("> ")

def check_webhook(token):
    """Check the current webhook status."""
    url = f"https://api.telegram.org/bot{token}/getWebhookInfo"
    
    try:
        response = requests.get(url)
        data = response.json()
        
        print("\n=== WEBHOOK STATUS ===")
        
        if not response.ok:
            print(f"Error: {data.get('description', 'Unknown error')}")
            return False
        
        result = data.get('result', {})
        
        # Pretty print the webhook info
        print(f"URL: {result.get('url', 'Not set')}")
        print(f"Has custom certificate: {result.get('has_custom_certificate', False)}")
        print(f"Pending update count: {result.get('pending_update_count', 0)}")
        
        if result.get('last_error_date'):
            import datetime
            error_date = datetime.datetime.fromtimestamp(result['last_error_date'])
            print(f"Last error: {error_date} - {result.get('last_error_message', 'No message')}")
        
        if result.get('max_connections'):
            print(f"Max connections: {result['max_connections']}")
        
        if result.get('ip_address'):
            print(f"IP Address: {result['ip_address']}")
        
        if result.get('allowed_updates'):
            print(f"Allowed updates: {', '.join(result['allowed_updates'])}")
        
        webhook_url = result.get('url')
        if not webhook_url:
            print("\nStatus: NO WEBHOOK SET")
            return False
        else:
            print("\nStatus: WEBHOOK IS SET")
            return True
            
    except Exception as e:
        print(f"Error checking webhook: {e}")
        return False

def delete_webhook(token):
    """Delete the current webhook."""
    url = f"https://api.telegram.org/bot{token}/deleteWebhook?drop_pending_updates=true"
    
    try:
        response = requests.get(url)
        data = response.json()
        
        if not response.ok:
            print(f"Error: {data.get('description', 'Unknown error')}")
            return False
        
        if data.get('result'):
            print("Webhook successfully deleted!")
            return True
        else:
            print("Failed to delete webhook.")
            print(data)
            return False
            
    except Exception as e:
        print(f"Error deleting webhook: {e}")
        return False

def set_webhook(token, webhook_url):
    """Set the webhook to the specified URL."""
    url = f"https://api.telegram.org/bot{token}/setWebhook"
    
    try:
        params = {
            'url': webhook_url,
            'allowed_updates': json.dumps(['message', 'callback_query']),
            'drop_pending_updates': True
        }
        
        response = requests.post(url, params=params)
        data = response.json()
        
        if not response.ok:
            print(f"Error: {data.get('description', 'Unknown error')}")
            return False
        
        if data.get('result'):
            print(f"Webhook successfully set to {webhook_url}!")
            return True
        else:
            print("Failed to set webhook.")
            print(data)
            return False
            
    except Exception as e:
        print(f"Error setting webhook: {e}")
        return False

def reset_webhook(token):
    """Reset the webhook (delete and set again)."""
    print("Resetting webhook...")
    
    # Delete the current webhook
    if not delete_webhook(token):
        print("Failed to delete webhook. Aborting reset.")
        return False
    
    # Get the webhook URL
    webhook_url = get_webhook_url()
    
    # Set the webhook
    return set_webhook(token, webhook_url)

def get_bot_info(token):
    """Get information about the bot."""
    url = f"https://api.telegram.org/bot{token}/getMe"
    
    try:
        response = requests.get(url)
        data = response.json()
        
        if not response.ok:
            print(f"Error: {data.get('description', 'Unknown error')}")
            return False
        
        result = data.get('result', {})
        
        print("\n=== BOT INFO ===")
        print(f"ID: {result.get('id')}")
        print(f"Name: {result.get('first_name')}")
        print(f"Username: @{result.get('username')}")
        print(f"Can join groups: {result.get('can_join_groups', False)}")
        print(f"Can read all group messages: {result.get('can_read_all_group_messages', False)}")
        print(f"Supports inline queries: {result.get('supports_inline_queries', False)}")
        
        return True
            
    except Exception as e:
        print(f"Error getting bot info: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Telegram Bot Webhook Tool')
    
    # Action group (mutually exclusive)
    action_group = parser.add_mutually_exclusive_group()
    action_group.add_argument('--check', action='store_true', help='Check webhook status (default action)')
    action_group.add_argument('--reset', action='store_true', help='Reset webhook (delete and set again)')
    action_group.add_argument('--delete', action='store_true', help='Delete webhook')
    action_group.add_argument('--set', metavar='URL', help='Set webhook to specified URL')
    
    # Parse arguments
    args = parser.parse_args()
    
    # Get token
    token = get_token()
    
    # Get bot info
    get_bot_info(token)
    
    # Process actions
    if args.reset:
        reset_webhook(token)
    elif args.delete:
        delete_webhook(token)
    elif args.set:
        set_webhook(token, args.set)
    else:
        # Default action: check webhook
        check_webhook(token)

if __name__ == "__main__":
    main() 