#!/usr/bin/env python3
"""
Script to fix chat link generation in on_start_anon_chat function
"""

import os
import sys
import re
import shutil
import logging
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Define the file path
START_PY_PATH = "src/bot/handlers/start.py"

if not os.path.exists(START_PY_PATH):
    print(f"Error: {START_PY_PATH} not found!")
    sys.exit(1)

print(f"Checking chat link generation in {START_PY_PATH}...")

def fix_on_start_anon_chat():
    """
    Fix the communicator bot username issue in the on_start_anon_chat function.
    
    This script addresses issues with the COMMUNICATOR_BOT_USERNAME environment variable
    by adding proper validation, error handling, and ensuring the username is properly
    formatted when generating deep links.
    """
    # File path
    file_path = "src/bot/handlers/start.py"
    
    # Create backup of the original file
    backup_path = f"{file_path}.chat_links_bak"
    logger.info(f"Creating backup at {backup_path}")
    shutil.copy2(file_path, backup_path)
    
    try:
        # Read the original file
        with open(file_path, 'r') as file:
            content = file.read()
        
        # Define the pattern to match
        pattern = r'# Generate a deep link to the communicator bot\s+communicator_bot_username = settings\.COMMUNICATOR_BOT_USERNAME\s+# Ensure username is valid before creating the link\s+if not communicator_bot_username or communicator_bot_username == "":\s+communicator_bot_username = "AllkindsChatBot"\s+# Fallback to a known username\s+logger\.warning\(f"Using fallback communicator bot username: \{communicator_bot_username\}"\)\s+\s+# Create the deep link with proper validation\s+deep_link = f"https://t\.me/\{communicator_bot_username\}\?start=chat_\{chat_id\}"'
        
        # Define the replacement with improved error handling and validation
        replacement = """# Generate a deep link to the communicator bot
        try:
            communicator_bot_username = settings.COMMUNICATOR_BOT_USERNAME
            # Ensure username is valid before creating the link
            if not communicator_bot_username or communicator_bot_username == "":
                communicator_bot_username = "AllkindsCommunicatorBot"  # Fallback to a known username
                logger.warning(f"Using fallback communicator bot username: {communicator_bot_username}")
            
            # Remove @ if it's included in the username
            if communicator_bot_username.startswith('@'):
                communicator_bot_username = communicator_bot_username[1:]
                logger.info(f"Removed @ prefix from bot username, using: {communicator_bot_username}")
                
            # Create the deep link with proper validation
            deep_link = f"https://t.me/{communicator_bot_username}?start=chat_{chat_id}"
            logger.info(f"Generated deep link: {deep_link}")
        except Exception as e:
            logger.error(f"Error generating deep link: {e}")
            communicator_bot_username = "AllkindsCommunicatorBot"  # Emergency fallback
            deep_link = f"https://t.me/{communicator_bot_username}?start=chat_{chat_id}"
            logger.warning(f"Using emergency fallback for deep link: {deep_link}")"""
        
        # Apply the replacement
        new_content = re.sub(pattern, replacement, content)
        
        # Check if any changes were made
        if new_content == content:
            logger.warning("No changes made - pattern may not have matched any content in the file.")
            return False
        
        # Write the modified content back to the file
        with open(file_path, 'w') as file:
            file.write(new_content)
        
        logger.info("Successfully updated the on_start_anon_chat function with improved error handling.")
        logger.info("Please restart your bot for changes to take effect.")
        return True
        
    except Exception as e:
        logger.error(f"Error fixing the on_start_anon_chat function: {e}")
        return False

if __name__ == "__main__":
    fix_on_start_anon_chat()

# Second check: find the function that generates chat links directly
direct_deep_link_pattern = r"deep_link = f\"https://t\.me/\{bot_username\}\?start=chat_\{session_id\}\""

# Replacement with proper validation
direct_deep_link_replacement = """# Ensure bot username is valid before creating the link
        if not bot_username or bot_username.strip() == "":
            logger.warning("[DEEP_LINK] Bot username is empty or invalid")
            bot_username = "AllkindsCommunicatorBot"  # Use fallback
            logger.info(f"[DEEP_LINK] Using fallback username: {bot_username}")
            
        deep_link = f"https://t.me/{bot_username}?start=chat_{session_id}"
        logger.info(f"[DEEP_LINK] Generated deep link: {deep_link}")"""

# Replace the direct deep link generation code
updated_content = re.sub(direct_deep_link_pattern, direct_deep_link_replacement, updated_content)

# Check if any additional changes were made
if updated_content == content:
    print("No direct deep link generation code found to fix.")
else:
    # Write the updated content
    with open(START_PY_PATH, 'w') as file:
        file.write(updated_content)
    print("Direct deep link generation code fixed successfully!")

print("Chat link fixes completed! Please restart the bot for the changes to take effect.") 