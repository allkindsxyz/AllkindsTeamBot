#!/usr/bin/env python3
"""
Script to update all bot username references to consistently use 'AllkindsCommunicatorBot' as the fallback
"""

import os
import re
import sys
import shutil
from datetime import datetime

# Define the correct bot username
CORRECT_BOT_USERNAME = "AllkindsCommunicatorBot"  # This is the correct username

# Path to the main file that needs fixing
START_PY_PATH = "src/bot/handlers/start.py"

# Create backup of the original file
def create_backup(file_path):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{file_path}.bak_{timestamp}"
    try:
        shutil.copy2(file_path, backup_path)
        print(f"Created backup at {backup_path}")
        return True
    except Exception as e:
        print(f"Error creating backup: {e}")
        return False

def update_bot_username_references():
    # Create backup first
    if not create_backup(START_PY_PATH):
        print("Failed to create backup, aborting to be safe.")
        return False
    
    # Read the file content
    try:
        with open(START_PY_PATH, 'r') as file:
            content = file.read()
    except Exception as e:
        print(f"Error reading file {START_PY_PATH}: {e}")
        return False
    
    # Pattern to find the fallback username in handle_start_anon_chat function
    pattern1 = r'(bot_username = ")(AllkindsChatBot|AllkindsBot|AllkindsCommunicatorBot)(".*?# Use fallback)'
    replacement1 = f'\\1{CORRECT_BOT_USERNAME}\\3'
    
    # Pattern to find the fallback username in on_start_anon_chat function
    pattern2 = r'(communicator_bot_username = ")(AllkindsChatBot|AllkindsBot|AllkindsCommunicatorBot)(".*?# Fallback)'
    replacement2 = f'\\1{CORRECT_BOT_USERNAME}\\3'
    
    # Apply replacements
    updated_content = re.sub(pattern1, replacement1, content, flags=re.DOTALL)
    updated_content = re.sub(pattern2, replacement2, updated_content, flags=re.DOTALL)
    
    # Check if content was actually modified
    if content == updated_content:
        print("No changes needed, all bot username references are already correct.")
        return True
    
    # Write updated content back to the file
    try:
        with open(START_PY_PATH, 'w') as file:
            file.write(updated_content)
        print(f"Updated bot username references in {START_PY_PATH}")
        return True
    except Exception as e:
        print(f"Error writing updated content to {START_PY_PATH}: {e}")
        return False

def update_env_file():
    # Update .env file if it exists
    env_file_path = ".env"
    if os.path.exists(env_file_path):
        try:
            with open(env_file_path, 'r') as file:
                env_content = file.read()
            
            # Check if COMMUNICATOR_BOT_USERNAME already exists
            username_pattern = r'^COMMUNICATOR_BOT_USERNAME=(.*)$'
            username_match = re.search(username_pattern, env_content, re.MULTILINE)
            
            if username_match:
                current_username = username_match.group(1)
                if current_username != CORRECT_BOT_USERNAME:
                    # Replace existing value
                    env_content = re.sub(
                        username_pattern,
                        f'COMMUNICATOR_BOT_USERNAME={CORRECT_BOT_USERNAME}',
                        env_content,
                        flags=re.MULTILINE
                    )
                    print(f"Updating COMMUNICATOR_BOT_USERNAME from '{current_username}' to '{CORRECT_BOT_USERNAME}'")
                else:
                    print(f"COMMUNICATOR_BOT_USERNAME is already set to {CORRECT_BOT_USERNAME}")
            else:
                # Add the variable if it doesn't exist
                env_content = env_content.rstrip() + f"\nCOMMUNICATOR_BOT_USERNAME={CORRECT_BOT_USERNAME}\n"
                print(f"Adding COMMUNICATOR_BOT_USERNAME={CORRECT_BOT_USERNAME} to .env file")
            
            # Write updated content back to .env file
            with open(env_file_path, 'w') as file:
                file.write(env_content)
            print(f"Updated .env file")
        except Exception as e:
            print(f"Error updating .env file: {e}")
    else:
        # Create .env file if it doesn't exist
        try:
            with open(env_file_path, 'w') as file:
                file.write(f"COMMUNICATOR_BOT_USERNAME={CORRECT_BOT_USERNAME}\n")
            print(f"Created new .env file with COMMUNICATOR_BOT_USERNAME={CORRECT_BOT_USERNAME}")
        except Exception as e:
            print(f"Error creating .env file: {e}")

if __name__ == "__main__":
    print("Updating bot username references...")
    if update_bot_username_references():
        update_env_file()
        print("Updates completed successfully!")
        print("Please restart the bot for changes to take effect.")
    else:
        print("Failed to update bot username references.") 