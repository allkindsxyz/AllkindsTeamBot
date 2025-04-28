#!/usr/bin/env python3
"""
Script to update all references to the communicator bot in the codebase
to ensure the correct production bot is used.
"""

import os
import sys
import re
from pathlib import Path

# Define the correct bot username and token
CORRECT_BOT_USERNAME = "AllkindsChat"  # Update with your production bot username
CORRECT_BOT_TOKEN = "8018043989:AAGXTjJ5EZ1JjAhZLwd700W_FmRmyDD-AzQ"  # The production token

# Files to check
START_PY_PATH = "src/bot/handlers/start.py"
ENV_FILE_PATH = ".env"

print("Checking and updating communicator bot references...")

# Update the .env file
if os.path.exists(ENV_FILE_PATH):
    with open(ENV_FILE_PATH, 'r') as file:
        env_content = file.read()
        
    # Check for COMMUNICATOR_BOT_USERNAME
    username_pattern = r'^COMMUNICATOR_BOT_USERNAME=(.*)$'
    username_match = re.search(username_pattern, env_content, re.MULTILINE)
    
    # Check for COMMUNICATOR_BOT_TOKEN
    token_pattern = r'^COMMUNICATOR_BOT_TOKEN=(.*)$'
    token_match = re.search(token_pattern, env_content, re.MULTILINE)
    
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
    
    if token_match:
        current_token = token_match.group(1)
        if current_token != CORRECT_BOT_TOKEN:
            print(f"Updating COMMUNICATOR_BOT_TOKEN to the correct production token")
            env_content = re.sub(
                token_pattern,
                f'COMMUNICATOR_BOT_TOKEN={CORRECT_BOT_TOKEN}',
                env_content,
                flags=re.MULTILINE
            )
        else:
            print(f"COMMUNICATOR_BOT_TOKEN is already set to the correct production token")
    else:
        # Add the token variable
        env_content = env_content.rstrip() + f"\nCOMMUNICATOR_BOT_TOKEN={CORRECT_BOT_TOKEN}\n"
        print(f"Adding COMMUNICATOR_BOT_TOKEN to .env file")
    
    # Write the updated content back to the file
    with open(ENV_FILE_PATH, 'w') as file:
        file.write(env_content)
else:
    print(f"Creating new .env file with bot configurations")
    with open(ENV_FILE_PATH, 'w') as f:
        f.write(f"COMMUNICATOR_BOT_USERNAME={CORRECT_BOT_USERNAME}\n")
        f.write(f"COMMUNICATOR_BOT_TOKEN={CORRECT_BOT_TOKEN}\n")

# Update the start.py file
if os.path.exists(START_PY_PATH):
    # Create a backup
    backup_path = f"{START_PY_PATH}.bot_config_bak"
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
        (r'communicator_bot_username\s*=\s*["\'](AllkindsCommunicatorBot|AllkindsTestChat)["\']', 
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
print("\n2. Update the environment variables in Railway dashboard:")
print("   - COMMUNICATOR_BOT_USERNAME should be set to", CORRECT_BOT_USERNAME)
print("   - COMMUNICATOR_BOT_TOKEN should be set to [your production token]")
print("\n3. Deploy the changes to Railway:")
print("   railway up")
print("\n4. Monitor the logs to ensure the correct bot is being used:")
print("   railway logs")
print("\nThese changes will ensure your main bot uses the correct production communicator bot.") 