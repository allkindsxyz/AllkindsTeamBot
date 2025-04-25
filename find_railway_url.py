#!/usr/bin/env python
"""
Railway URL Finder

This script tries multiple approaches to identify your Railway public URL.
"""

import os
import sys
import subprocess
import json
import requests
from loguru import logger

# Set up logging
logger.remove()
logger.add(sys.stderr, level="INFO")
logger.add("find_railway_url.log", rotation="1 MB", level="DEBUG")

def check_environment_variables():
    """Check for Railway-related environment variables."""
    logger.info("Checking environment variables...")
    
    railway_vars = {
        'RAILWAY_PUBLIC_URL': os.environ.get('RAILWAY_PUBLIC_URL'),
        'RAILWAY_STATIC_URL': os.environ.get('RAILWAY_STATIC_URL'),
        'RAILWAY_PUBLIC_DOMAIN': os.environ.get('RAILWAY_PUBLIC_DOMAIN'),
        'WEBHOOK_DOMAIN': os.environ.get('WEBHOOK_DOMAIN')
    }
    
    for name, value in railway_vars.items():
        if value:
            logger.info(f"{name}: {value}")
            return value
        else:
            logger.info(f"{name}: Not set")
    
    return None

def check_railway_cli():
    """Try to get information using Railway CLI."""
    logger.info("Checking Railway CLI...")
    
    try:
        # Check if Railway CLI is installed
        result = subprocess.run(["railway", "--version"], capture_output=True, text=True)
        if result.returncode != 0:
            logger.error("Railway CLI not installed or not in PATH")
            return None
            
        logger.info(f"Railway CLI version: {result.stdout.strip()}")
        
        # Try to get project info
        result = subprocess.run(["railway", "status", "--json"], capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"Error running 'railway status': {result.stderr}")
            return None
            
        try:
            data = json.loads(result.stdout)
            logger.info(f"Project: {data.get('project', {}).get('name')}")
            
            # Try to find domains
            environments = data.get('environments', [])
            for env in environments:
                domains = env.get('domains', [])
                if domains:
                    domain = domains[0].get('domain')
                    logger.info(f"Found domain: {domain}")
                    return f"https://{domain}"
        except json.JSONDecodeError:
            logger.error("Failed to parse Railway CLI output")
        
    except Exception as e:
        logger.error(f"Error checking Railway CLI: {e}")
    
    return None

def check_bot_webhook_info(token):
    """Check the current webhook info to find the domain."""
    if not token:
        logger.warning("No bot token provided, skipping webhook check")
        return None
        
    logger.info("Checking current webhook info...")
    
    try:
        url = f"https://api.telegram.org/bot{token}/getWebhookInfo"
        response = requests.get(url)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('ok'):
                webhook_url = data.get('result', {}).get('url')
                if webhook_url:
                    logger.info(f"Current webhook URL: {webhook_url}")
                    return webhook_url.split('/webhook/')[0]  # Extract the domain part
        else:
            logger.error(f"Failed to get webhook info: {response.status_code}")
    except Exception as e:
        logger.error(f"Error checking webhook info: {e}")
    
    return None

def check_railway_dashboard():
    """Provide instructions for checking the Railway dashboard."""
    logger.info("For manual lookup, follow these steps:")
    logger.info("1. Go to https://railway.app/dashboard")
    logger.info("2. Select your AllkindsTeamBot project")
    logger.info("3. Click on the main service (not the database)")
    logger.info("4. Look for 'Deployments' section and find the latest successful deployment")
    logger.info("5. The URL should be shown as 'Generated Domain'")
    
    return None

def main():
    """Find Railway URL using multiple methods."""
    logger.info("=== RAILWAY URL FINDER ===")
    
    # Ask for bot token (optional)
    token = input("Enter your Telegram bot token (or press Enter to skip this step): ").strip()
    
    # Try different methods
    url = check_environment_variables()
    
    if not url:
        url = check_railway_cli()
    
    if not url and token:
        url = check_bot_webhook_info(token)
    
    if url:
        logger.info(f"\n=== RESULT ===\nRailway URL found: {url}")
        
        if token:
            webhook_url = f"{url}/webhook/{token}"
            logger.info(f"Complete webhook URL: {webhook_url}")
            
            logger.info("\nTo reset your webhook, run:")
            logger.info(f"python3 direct_reset_webhook.py --token {token} --url {webhook_url}")
    else:
        logger.warning("\n=== RESULT ===\nCould not automatically determine Railway URL")
        check_railway_dashboard()
        
        logger.info("\nIf you find the URL manually, run:")
        if token:
            logger.info(f"python3 direct_reset_webhook.py --token {token} --url YOUR_RAILWAY_URL/webhook/{token}")
        else:
            logger.info("python3 direct_reset_webhook.py --token YOUR_BOT_TOKEN --url YOUR_RAILWAY_URL/webhook/YOUR_BOT_TOKEN")

if __name__ == "__main__":
    main() 