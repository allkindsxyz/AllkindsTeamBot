#!/usr/bin/env python3
"""Simple script to test if a Telegram bot token is valid"""

import os
import sys
import requests
import json

def test_token(token):
    """Test if a token is valid by calling getMe"""
    print(f"Testing token: {token[:4]}...{token[-4:]}")
    url = f"https://api.telegram.org/bot{token}/getMe"
    
    try:
        response = requests.get(url)
        data = response.json()
        
        if data.get('ok'):
            bot_info = data.get('result', {})
            print(f"✅ Token is VALID!")
            print(f"Bot name: {bot_info.get('first_name')}")
            print(f"Bot username: @{bot_info.get('username')}")
            print(f"Bot ID: {bot_info.get('id')}")
            return True
        else:
            print(f"❌ Token is INVALID! Error: {data.get('description')}")
            return False
    except Exception as e:
        print(f"❌ Error testing token: {e}")
        return False

if __name__ == "__main__":
    # Token to test
    token = "7910000886:AAHwuYKz8je_JSrpf53lXX8S6V5mfTqLd6Y"
    
    if len(sys.argv) > 1:
        token = sys.argv[1]
    
    test_token(token) 