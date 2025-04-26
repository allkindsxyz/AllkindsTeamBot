#!/usr/bin/env python3
"""
Script to update environment variables in .env file.
Specifically designed to toggle between webhook and polling modes.
"""

import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv, set_key

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Update environment variables in .env file")
    parser.add_argument(
        "--webhook", 
        action="store_true", 
        help="Set USE_WEBHOOK=true (use webhook mode)"
    )
    parser.add_argument(
        "--polling", 
        action="store_true", 
        help="Set USE_WEBHOOK=false (use polling mode)"
    )
    parser.add_argument(
        "--env-file", 
        default=".env", 
        help="Path to .env file (default: .env)"
    )
    parser.add_argument(
        "--webhook-domain", 
        help="Set the webhook domain (e.g., https://example.com)"
    )
    parser.add_argument(
        "--webhook-path", 
        help="Set the webhook path (e.g., /webhook)"
    )
    parser.add_argument(
        "--webapp-port", 
        type=int,
        help="Set the webapp port (e.g., 8080)"
    )
    return parser.parse_args()

def main():
    """Main entry point."""
    args = parse_args()
    
    # Load existing variables
    env_file = Path(args.env_file)
    if env_file.exists():
        print(f"Loading existing environment from {env_file}")
        load_dotenv(env_file)
    else:
        print(f"Creating new environment file at {env_file}")
        env_file.touch()
    
    # Check arguments - ensure we don't set contradictory values
    if args.webhook and args.polling:
        print("Error: Cannot set both --webhook and --polling flags")
        sys.exit(1)
    
    # Set webhook mode
    if args.webhook:
        print("Setting webhook mode: USE_WEBHOOK=true")
        set_key(env_file, "USE_WEBHOOK", "true")
    elif args.polling:
        print("Setting polling mode: USE_WEBHOOK=false")
        set_key(env_file, "USE_WEBHOOK", "false")
    
    # Set webhook domain if provided
    if args.webhook_domain:
        print(f"Setting webhook domain: WEBHOOK_HOST={args.webhook_domain}")
        set_key(env_file, "WEBHOOK_HOST", args.webhook_domain)
    
    # Set webhook path if provided
    if args.webhook_path:
        print(f"Setting webhook path: WEBHOOK_PATH={args.webhook_path}")
        set_key(env_file, "WEBHOOK_PATH", args.webhook_path)
    
    # Set webapp port if provided
    if args.webapp_port:
        print(f"Setting webapp port: WEBAPP_PORT={args.webapp_port}")
        set_key(env_file, "WEBAPP_PORT", str(args.webapp_port))
    
    print(f"Environment updated in {env_file}")
    
    # Show current webhook mode
    webhook_mode = os.environ.get("USE_WEBHOOK", "false").lower() == "true"
    print(f"Current mode: {'Webhook' if webhook_mode else 'Polling'}")

if __name__ == "__main__":
    main() 