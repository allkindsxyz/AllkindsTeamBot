#!/usr/bin/env python3
"""
Script to fix chat link generation in on_start_anon_chat function
"""

import os
import sys
import re

# Define the file path
START_PY_PATH = "src/bot/handlers/start.py"

if not os.path.exists(START_PY_PATH):
    print(f"Error: {START_PY_PATH} not found!")
    sys.exit(1)

print(f"Checking chat link generation in {START_PY_PATH}...")

# Read the file content
with open(START_PY_PATH, 'r') as file:
    content = file.read()

# Create a backup
with open(f"{START_PY_PATH}.chat_links_bak", 'w') as backup_file:
    backup_file.write(content)
    print(f"Created backup at {START_PY_PATH}.chat_links_bak")

# Pattern to locate the problematic deep link generation
# This pattern matches the line that creates the deep_link without checking if the username is valid
deep_link_pattern = r"deep_link = f\"https://t\.me/\{communicator_bot_username\}\?start=chat_\{chat_id\}\""

# Replacement with proper checks to ensure valid bot username
deep_link_replacement = """# Ensure username is valid before creating the link
        if not communicator_bot_username or communicator_bot_username == "":
            communicator_bot_username = "AllkindsCommunicatorBot"  # Fallback to a known username
            logger.warning(f"Using fallback communicator bot username: {communicator_bot_username}")
        
        # Create the deep link with proper validation
        deep_link = f"https://t.me/{communicator_bot_username}?start=chat_{chat_id}"
        logger.info(f"Generated deep link: {deep_link}")"""

# Replace the deep link generation code
updated_content = re.sub(deep_link_pattern, deep_link_replacement, content)

# Check if any changes were made
if updated_content == content:
    print("No deep link generation code found to fix.")
else:
    # Write the updated content
    with open(START_PY_PATH, 'w') as file:
        file.write(updated_content)
    print("Deep link generation code fixed successfully!")

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