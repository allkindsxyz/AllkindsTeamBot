#!/usr/bin/env python3
"""
Utility script to test a Telegram bot token.
"""
import os
import sys
import argparse
import requests
from typing import Dict, Any, Union, Optional

def get_bot_info(token: str) -> Union[Dict[str, Any], None]:
    """
    Get information about a Telegram bot using its token.
    
    Args:
        token: The bot token to test
        
    Returns:
        Dictionary containing bot information or None if token is invalid
    """
    try:
        response = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=5)
        response.raise_for_status()
        return response.json()["result"]
    except Exception as e:
        print(f"Error testing token: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description='Test a Telegram bot token')
    parser.add_argument('--token', help='The bot token to test')
    args = parser.parse_args()
    
    # Get token from arguments, environment, or prompt
    token = args.token or os.environ.get("BOT_TOKEN")
    
    if not token:
        token = input("Enter the bot token to test: ")
    
    if not token:
        print("No token provided. Exiting.")
        sys.exit(1)
    
    print(f"Testing token (first 5 chars: {token[:5]}...)")
    
    # Test the token
    bot_info = get_bot_info(token)
    
    if bot_info:
        print("✅ Token is valid!")
        print(f"Bot details:")
        print(f"  - ID: {bot_info.get('id')}")
        print(f"  - Name: {bot_info.get('first_name')}")
        print(f"  - Username: @{bot_info.get('username')}")
        print(f"  - Can join groups: {bot_info.get('can_join_groups', False)}")
        print(f"  - Can read group messages: {bot_info.get('can_read_all_group_messages', False)}")
        print(f"  - Supports inline queries: {bot_info.get('supports_inline_queries', False)}")
    else:
        print("❌ Token is invalid or an error occurred.")
        sys.exit(1)

if __name__ == "__main__":
    main() 