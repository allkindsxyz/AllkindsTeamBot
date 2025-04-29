#!/usr/bin/env python3
"""
Script to update all references to the communicator bot in the codebase
to ensure the correct production bot is used without hardcoding sensitive tokens.
"""

import os
import sys
import re
import subprocess
from pathlib import Path

# Define the correct bot username
CORRECT_BOT_USERNAME = "AllkindsChatBot"  # Updated to match Railway

# Files to check
START_PY_PATH = "src/bot/handlers/start.py"
ENV_FILE_PATH = ".env"

def run_command(command, check=True):
    """Run a shell command and return the output."""
    print(f"Running: {command}")
    result = subprocess.run(command, shell=True, text=True, capture_output=True)
    if check and result.returncode != 0:
        print(f"Command failed with exit code {result.returncode}")
        print(f"Error: {result.stderr}")
        sys.exit(1)
    return result.stdout.strip()

def get_bot_token_from_railway():
    """Try to get the bot token from Railway variables."""
    try:
        output = run_command("railway variables", check=False)
        for line in output.splitlines():
            if "COMMUNICATOR_BOT_TOKEN" in line:
                token = line.split("COMMUNICATOR_BOT_TOKEN")[1].strip()
                if token.startswith("="):
                    token = token[1:].strip()
                print("Retrieved bot token from Railway variables")
                return token
    except Exception as e:
        print(f"Could not get token from Railway: {e}")
    
    print("Bot token not found in Railway variables")
    return None

def get_bot_token_from_env():
    """Try to get the bot token from .env file."""
    if os.path.exists(ENV_FILE_PATH):
        try:
            with open(ENV_FILE_PATH, 'r') as file:
                content = file.read()
                token_match = re.search(r'^COMMUNICATOR_BOT_TOKEN=(.*)$', content, re.MULTILINE)
                if token_match:
                    return token_match.group(1)
        except Exception as e:
            print(f"Error reading token from .env: {e}")
    
    return None

print("Checking and updating communicator bot references...")

# Get the bot token from Railway or .env file
bot_token = get_bot_token_from_railway() or get_bot_token_from_env()

if not bot_token:
    print("⚠️ No bot token found in Railway or .env file. Username-only updates will be applied.")
    print("Please set COMMUNICATOR_BOT_TOKEN manually in Railway and .env file.")

# Update the .env file
if os.path.exists(ENV_FILE_PATH):
    with open(ENV_FILE_PATH, 'r') as file:
        env_content = file.read()
        
    # Check for COMMUNICATOR_BOT_USERNAME
    username_pattern = r'^COMMUNICATOR_BOT_USERNAME=(.*)$'
    username_match = re.search(username_pattern, env_content, re.MULTILINE)
    
    if username_match:
        current_username = username_match.group(1)
        if current_username != CORRECT_BOT_USERNAME:
            print(f"Updating COMMUNICATOR_BOT_USERNAME from '{current_username}' to '{CORRECT_BOT_USERNAME}'")
            env_content = re.sub(
                username_pattern,
                f'COMMUNICATOR_BOT_USERNAME={CORRECT_BOT_USERNAME}',
                env_content,
                flags=re.MULTILINE
            )
        else:
            print(f"COMMUNICATOR_BOT_USERNAME is already set to {CORRECT_BOT_USERNAME}")
    else:
        # Add the username variable
        env_content = env_content.rstrip() + f"\nCOMMUNICATOR_BOT_USERNAME={CORRECT_BOT_USERNAME}\n"
        print(f"Adding COMMUNICATOR_BOT_USERNAME={CORRECT_BOT_USERNAME} to .env file")
    
    # Update token if we have one and it's not already set
    if bot_token:
        token_pattern = r'^COMMUNICATOR_BOT_TOKEN=(.*)$'
        token_match = re.search(token_pattern, env_content, re.MULTILINE)
        
        if token_match:
            current_token = token_match.group(1)
            if current_token != bot_token:
                print(f"Updating COMMUNICATOR_BOT_TOKEN in .env file")
                env_content = re.sub(
                    token_pattern,
                    f'COMMUNICATOR_BOT_TOKEN={bot_token}',
                    env_content,
                    flags=re.MULTILINE
                )
            else:
                print(f"COMMUNICATOR_BOT_TOKEN is already set correctly")
        else:
            # Add the token variable
            env_content = env_content.rstrip() + f"\nCOMMUNICATOR_BOT_TOKEN={bot_token}\n"
            print(f"Adding COMMUNICATOR_BOT_TOKEN to .env file")
    
    # Write the updated content back to the file
    with open(ENV_FILE_PATH, 'w') as file:
        file.write(env_content)
else:
    print(f"Creating new .env file with bot configurations")
    with open(ENV_FILE_PATH, 'w') as f:
        f.write(f"COMMUNICATOR_BOT_USERNAME={CORRECT_BOT_USERNAME}\n")
        if bot_token:
            f.write(f"COMMUNICATOR_BOT_TOKEN={bot_token}\n")

# Update the start.py file
if os.path.exists(START_PY_PATH):
    # Create a backup
    backup_path = f"{START_PY_PATH}.bot_config_bak2"
    print(f"Creating backup of {START_PY_PATH} at {backup_path}")
    
    with open(START_PY_PATH, 'r') as file:
        content = file.read()
        
    with open(backup_path, 'w') as backup_file:
        backup_file.write(content)
    
    # Look for hardcoded bot references
    # Pattern for fallback username assignments
    patterns = [
        # Find any fallback assignment for communicator_bot_username
        (r'communicator_bot_username\s*=\s*["\']([^"\']+)["\']  # Fallback', 
         f'communicator_bot_username = "{CORRECT_BOT_USERNAME}"  # Fallback'),
        
        # Find any fallback assignment for bot_username
        (r'bot_username\s*=\s*["\']([^"\']+)["\']  # Use fallback', 
         f'bot_username = "{CORRECT_BOT_USERNAME}"  # Use fallback'),
        
        # Find direct assignments without the fallback comment
        (r'communicator_bot_username\s*=\s*["\'](AllkindsCommunicatorBot|AllkindsTestChat|AllkindsChat)["\']', 
         f'communicator_bot_username = "{CORRECT_BOT_USERNAME}"'),
        
        # Find getting username from bot token
        (r'get_bot_username_from_token\(communicator_bot_token\)', 
         f'"{CORRECT_BOT_USERNAME}" # Using fixed correct username'),
    ]
    
    changes_made = False
    for pattern, replacement in patterns:
        if re.search(pattern, content):
            content = re.sub(pattern, replacement, content)
            changes_made = True
    
    if changes_made:
        with open(START_PY_PATH, 'w') as file:
            file.write(content)
        print(f"Updated bot references in {START_PY_PATH}")
    else:
        print(f"No bot references to update in {START_PY_PATH}")
else:
    print(f"Error: {START_PY_PATH} not found!")

# Provide guidance for Railway deployment
print("\n=== Railway Deployment Instructions ===")
print("1. Make sure to commit and push these changes to your repository:")
print("   git add .env src/bot/handlers/start.py")
print("   git commit -m \"Update communicator bot to use production configuration\"")
print("   git push")
print("\n2. Verify environment variables in Railway dashboard:")
print("   - COMMUNICATOR_BOT_USERNAME should be set to", CORRECT_BOT_USERNAME)
print("   - COMMUNICATOR_BOT_TOKEN should be set to the correct production token")
print("\n3. Deploy the changes to Railway:")
print("   railway up")
print("\n4. Monitor the logs to ensure the correct bot is being used:")
print("   railway logs")
print("\nThese changes will ensure your main bot uses the correct production communicator bot.") 