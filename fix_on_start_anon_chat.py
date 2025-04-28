#!/usr/bin/env python3
"""
Script to fix COMMUNICATOR_BOT_USERNAME issues in the on_start_anon_chat function.
This script adds fallback logic and better error handling for the communicator bot username.
"""

import os
import re
import time
import shutil
from pathlib import Path
from datetime import datetime

# Configuration
target_file = "src/bot/handlers/start.py"
backup_suffix = f".bak.{datetime.now().strftime('%Y%m%d%H%M%S')}"
fallback_username = "AllkindsCommunicatorBot"  # Default fallback username

def make_backup(file_path):
    """Create a backup of the original file."""
    backup_path = f"{file_path}{backup_suffix}"
    shutil.copy2(file_path, backup_path)
    print(f"Created backup at {backup_path}")
    return backup_path

def fix_on_start_anon_chat():
    """Fix the communicator bot username issue in the on_start_anon_chat function."""
    if not os.path.exists(target_file):
        print(f"Error: {target_file} not found!")
        return False
    
    # Create backup
    backup_path = make_backup(target_file)
    
    # Read the file content
    with open(target_file, 'r', encoding='utf-8') as file:
        content = file.read()
    
    # Define the pattern to match the problematic code block
    pattern = (
        r'(# Generate a deep link to the communicator bot\s+)'
        r'communicator_bot_username = settings\.COMMUNICATOR_BOT_USERNAME\s+'
        r'(# Ensure username is valid before creating the link\s+)'
        r'if not communicator_bot_username or communicator_bot_username == "":\s+'
        r'communicator_bot_username = "[^"]+"\s+'
        r'logger\.warning\(f"Using fallback communicator bot username: \{communicator_bot_username\}"\)\s+'
        r'(\s+# Create the deep link with proper validation\s+)'
        r'deep_link = f"https://t\.me/\{communicator_bot_username\}\?start=chat_\{chat_id\}"'
    )
    
    # Define replacement with improved error handling and fallback
    replacement = (
        r'\1'
        r'# Try to get communicator bot username from settings\n'
        r'        try:\n'
        r'            communicator_bot_username = settings.COMMUNICATOR_BOT_USERNAME\n'
        r'        except Exception as e:\n'
        r'            logger.error(f"Error accessing COMMUNICATOR_BOT_USERNAME: {e}")\n'
        r'            communicator_bot_username = ""\n'
        r'            \n'
        r'        \2'
        r'# Validate the username more thoroughly\n'
        r'        if not communicator_bot_username or communicator_bot_username == "":\n'
        f'            communicator_bot_username = "{fallback_username}"  # Fallback username\n'
        r'            logger.warning(f"Using fallback communicator bot username: {communicator_bot_username}")\n'
        r'        \n'
        r'        # Remove any @ prefix if present\n'
        r'        if communicator_bot_username.startswith("@"):\n'
        r'            communicator_bot_username = communicator_bot_username[1:]\n'
        r'            logger.info(f"Removed @ prefix from bot username: {communicator_bot_username}")\n'
        r'            \n'
        r'        \3'
        r'# Create the deep link with proper validation\n'
        r'        deep_link = f"https://t.me/{communicator_bot_username}?start=chat_{chat_id}"\n'
        r'        logger.info(f"Generated deep link: {deep_link}")'
    )
    
    # Apply the replacement
    new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)
    
    # Check if any changes were made
    if new_content == content:
        print("No changes were made. Pattern may not have matched.")
        return False
    
    # Write the updated content
    with open(target_file, 'w', encoding='utf-8') as file:
        file.write(new_content)
    
    print(f"Successfully updated {target_file} with improved communicator bot username handling")
    return True

if __name__ == "__main__":
    print(f"Starting to fix communicator bot username issues in {target_file}")
    result = fix_on_start_anon_chat()
    if result:
        print("Fix completed successfully. Please restart your bot for changes to take effect.")
    else:
        print("Fix was not applied. Please check the errors above.") 