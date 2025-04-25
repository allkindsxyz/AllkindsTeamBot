#!/usr/bin/env python
"""
Telegram Bot Test Tool

This script tests the bot's ability to send and receive messages from Telegram.
Usage:
    python test_telegram.py                       # Check bot info
    python test_telegram.py --send <user_id>      # Send a test message to a user
"""

import requests
import os
import sys
import argparse
import json
import time

def get_token():
    """Get the bot token from environment variables."""
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN environment variable not found.")
        print("Please set it before running this script.")
        sys.exit(1)
    return token

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

def send_test_message(token, chat_id):
    """Send a test message to a chat."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    try:
        timestamp = int(time.time())
        message = f"Test message from Railway deployment at {timestamp}"
        
        params = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'Markdown'
        }
        
        print(f"Sending message to chat ID: {chat_id}")
        response = requests.post(url, params=params)
        data = response.json()
        
        if not response.ok:
            print(f"Error: {data.get('description', 'Unknown error')}")
            return False
        
        print("Message sent successfully!")
        print(f"Chat ID: {data['result']['chat']['id']}")
        print(f"Message ID: {data['result']['message_id']}")
        return True
            
    except Exception as e:
        print(f"Error sending message: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Telegram Bot Test Tool')
    
    parser.add_argument('--send', metavar='CHAT_ID', help='Send a test message to a chat ID')
    parser.add_argument('--keyboard', action='store_true', help='Include inline keyboard in test message')
    
    args = parser.parse_args()
    
    # Get token
    token = get_token()
    
    # Get bot info
    get_bot_info(token)
    
    # Process actions
    if args.send:
        send_test_message(token, args.send)

if __name__ == "__main__":
    main() 