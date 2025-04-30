#!/usr/bin/env python3
"""
Bot Token Validator

This script checks if your bot tokens are valid by:
1. Validating token format
2. Making a getMe API call to verify authentication
3. Providing a diagnostic report
"""

import os
import sys
import logging
import asyncio
import aiohttp
import ssl
import requests
from dotenv import load_dotenv
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
try:
    load_dotenv()
    logger.info("Loaded environment variables from .env file")
except Exception as e:
    logger.warning(f"Error loading .env file: {e}")

def is_valid_token_format(token):
    """Check if the token has a valid format (numbers:letters)."""
    if not token:
        return False
    
    # Basic format check - should contain a colon
    if ':' not in token:
        return False
    
    # Should be relatively long (typical token is around 46 chars)
    if len(token) < 30:
        return False
    
    # First part should be numeric, second part alphanumeric
    parts = token.split(':', 1)
    if len(parts) != 2:
        return False
    
    bot_id, token_part = parts
    return bot_id.isdigit() and token_part.isalnum()

async def validate_token_with_api(token, bot_name="Unknown"):
    """Validate token by making an API call to Telegram."""
    if not token:
        logger.error(f"Cannot validate {bot_name} token: No token provided")
        return False, None
    
    logger.info(f"Validating {bot_name} token...")
    
    # Create a default SSL context that doesn't verify
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    # Create a session with relaxed SSL configuration
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            async with session.get(
                f"https://api.telegram.org/bot{token}/getMe",
                ssl=False
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get("ok"):
                        bot_info = result.get("result", {})
                        logger.info(f"{bot_name} token is valid")
                        logger.info(f"  Bot username: @{bot_info.get('username', 'Unknown')}")
                        logger.info(f"  Bot ID: {bot_info.get('id', 'Unknown')}")
                        logger.info(f"  Bot name: {bot_info.get('first_name', 'Unknown')}")
                        return True, bot_info
                    else:
                        error = result.get("description", "Unknown error")
                        logger.error(f"{bot_name} token validation failed: {error}")
                else:
                    logger.error(f"{bot_name} token validation failed: HTTP {response.status}")
        except Exception as e:
            logger.error(f"Error validating {bot_name} token: {e}")
    
    # Try with regular requests as fallback
    try:
        logger.info(f"Trying alternative method for {bot_name}...")
        response = requests.get(
            f"https://api.telegram.org/bot{token}/getMe",
            verify=False,
            timeout=10
        )
        if response.status_code == 200:
            result = response.json()
            if result.get("ok"):
                bot_info = result.get("result", {})
                logger.info(f"{bot_name} token is valid (alternative method)")
                logger.info(f"  Bot username: @{bot_info.get('username', 'Unknown')}")
                logger.info(f"  Bot ID: {bot_info.get('id', 'Unknown')}")
                logger.info(f"  Bot name: {bot_info.get('first_name', 'Unknown')}")
                return True, bot_info
            else:
                error = result.get("description", "Unknown error")
                logger.error(f"{bot_name} token validation failed (alternative method): {error}")
        else:
            logger.error(f"{bot_name} token validation failed: HTTP {response.status_code}")
    except Exception as e:
        logger.error(f"Error with alternative validation: {e}")
    
    return False, None

def extract_cleaned_token(bot_name, token_var_name):
    """Extract and clean token from environment variables."""
    token = os.environ.get(token_var_name)
    if not token:
        logger.error(f"{bot_name} token not found in environment variables")
        return None
    
    # Clean up the token
    token = token.strip()
    if token.startswith('"') and token.endswith('"'):
        token = token[1:-1]
    if token.startswith("'") and token.endswith("'"):
        token = token[1:-1]
    
    return token

def update_env_with_valid_token(token_var_name, valid_token):
    """Update .env file with a valid token."""
    env_file = ".env"
    if not os.path.exists(env_file):
        logger.warning(f".env file not found, creating new one")
        with open(env_file, "w") as f:
            f.write(f"# Created by check_tokens.py at {datetime.now().isoformat()}\n")
            f.write(f"{token_var_name}={valid_token}\n")
        return True
    
    # Read existing file
    lines = []
    token_updated = False
    try:
        with open(env_file, "r") as f:
            for line in f:
                if line.strip().startswith(f"{token_var_name}="):
                    lines.append(f"{token_var_name}={valid_token}\n")
                    token_updated = True
                else:
                    lines.append(line)
    except Exception as e:
        logger.error(f"Error reading .env file: {e}")
        return False
    
    # Add token if it wasn't updated
    if not token_updated:
        lines.append(f"{token_var_name}={valid_token}\n")
    
    # Write updated file
    try:
        with open(env_file, "w") as f:
            f.writelines(lines)
        logger.info(f"Updated {token_var_name} in .env file")
        return True
    except Exception as e:
        logger.error(f"Error updating .env file: {e}")
        return False

async def run_token_checks(token_var_name, bot_name, fix=False):
    """Run comprehensive validation on a bot token."""
    # Extract token
    token = extract_cleaned_token(bot_name, token_var_name)
    if not token:
        return {
            "found": False,
            "valid_format": False,
            "api_valid": False,
            "bot_info": None,
            "error": "Token not found in environment variables"
        }
    
    # Check format
    format_valid = is_valid_token_format(token)
    if not format_valid:
        logger.warning(f"{bot_name} token has invalid format")
    
    # Check with API
    api_valid, bot_info = await validate_token_with_api(token, bot_name)
    
    # If fixing and token is invalid, prompt for new token
    if fix and not api_valid:
        new_token = input(f"\n{bot_name} token is invalid. Enter a new token (leave empty to skip): ").strip()
        if new_token:
            # Validate new token
            new_format_valid = is_valid_token_format(new_token)
            if not new_format_valid:
                logger.warning(f"New {bot_name} token has invalid format, but will try anyway")
            
            new_api_valid, new_bot_info = await validate_token_with_api(new_token, f"New {bot_name}")
            if new_api_valid:
                # Update environment variable
                os.environ[token_var_name] = new_token
                # Update .env file
                update_env_with_valid_token(token_var_name, new_token)
                
                return {
                    "found": True,
                    "valid_format": new_format_valid,
                    "api_valid": True,
                    "bot_info": new_bot_info,
                    "fixed": True
                }
    
    return {
        "found": True,
        "valid_format": format_valid,
        "api_valid": api_valid,
        "bot_info": bot_info
    }

def print_diagnostic_report(main_bot_result, comm_bot_result):
    """Print a comprehensive diagnostic report."""
    print("\n" + "="*50)
    print(" TELEGRAM BOT TOKEN VALIDATION REPORT")
    print("="*50)
    
    print("\nMAIN BOT:")
    print(f"  Token found in environment: {'✅' if main_bot_result.get('found') else '❌'}")
    print(f"  Token format valid: {'✅' if main_bot_result.get('valid_format') else '❌'}")
    print(f"  API authentication valid: {'✅' if main_bot_result.get('api_valid') else '❌'}")
    
    if main_bot_result.get('api_valid'):
        bot_info = main_bot_result.get('bot_info', {})
        print(f"  Bot username: @{bot_info.get('username', 'Unknown')}")
        print(f"  Bot ID: {bot_info.get('id', 'Unknown')}")
        print(f"  Bot name: {bot_info.get('first_name', 'Unknown')}")
    
    print("\nCOMMUNICATOR BOT:")
    print(f"  Token found in environment: {'✅' if comm_bot_result.get('found') else '❌'}")
    print(f"  Token format valid: {'✅' if comm_bot_result.get('valid_format') else '❌'}")
    print(f"  API authentication valid: {'✅' if comm_bot_result.get('api_valid') else '❌'}")
    
    if comm_bot_result.get('api_valid'):
        bot_info = comm_bot_result.get('bot_info', {})
        print(f"  Bot username: @{bot_info.get('username', 'Unknown')}")
        print(f"  Bot ID: {bot_info.get('id', 'Unknown')}")
        print(f"  Bot name: {bot_info.get('first_name', 'Unknown')}")
    
    print("\nRECOMMENDATIONS:")
    if not main_bot_result.get('api_valid'):
        print("  ❌ Main bot token is invalid. Please update your BOT_TOKEN environment variable.")
        print("     Run this script with --fix to update the token.")
    
    if not comm_bot_result.get('api_valid'):
        print("  ❌ Communicator bot token is invalid. Please update your COMMUNICATOR_BOT_TOKEN environment variable.")
        print("     Run this script with --fix to update the token.")
    
    if main_bot_result.get('api_valid') and comm_bot_result.get('api_valid'):
        print("  ✅ Both bot tokens are valid.")
        print("  ✅ Try running your application with 'python -m src.main'")
    
    print("="*50)

async def main():
    """Main entry point for the token validator."""
    logger.info("Starting bot token validation")
    
    # Check for fix flag
    fix_mode = "--fix" in sys.argv
    
    if fix_mode:
        logger.info("Running in fix mode - will prompt for new tokens if invalid")
    
    # Validate main bot token
    main_bot_result = await run_token_checks("BOT_TOKEN", "Main Bot", fix=fix_mode)
    
    # Validate communicator bot token
    comm_bot_result = await run_token_checks("COMMUNICATOR_BOT_TOKEN", "Communicator Bot", fix=fix_mode)
    
    # Print diagnostic report
    print_diagnostic_report(main_bot_result, comm_bot_result)
    
    # Return success if both tokens are valid
    return main_bot_result.get('api_valid', False) and comm_bot_result.get('api_valid', False)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Validation interrupted by user")
    except Exception as e:
        logger.error(f"Unhandled exception: {e}")
        import traceback
        traceback.print_exc() 