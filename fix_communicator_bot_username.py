#!/usr/bin/env python3
"""
Script to update the COMMUNICATOR_BOT_USERNAME in the .env file
"""

import os
import sys
import re

# Define the correct bot username
CORRECT_BOT_USERNAME = "AllkindsCommunicatorBot"  # Update this to the actual correct username

# Path to .env file
ENV_FILE_PATH = ".env"

# Check if .env file exists
if not os.path.exists(ENV_FILE_PATH):
    print(f"Error: {ENV_FILE_PATH} not found!")
    print("Creating a new .env file with the COMMUNICATOR_BOT_USERNAME.")
    with open(ENV_FILE_PATH, 'w') as f:
        f.write(f"COMMUNICATOR_BOT_USERNAME={CORRECT_BOT_USERNAME}\n")
    print(f"Created .env file with COMMUNICATOR_BOT_USERNAME={CORRECT_BOT_USERNAME}")
    sys.exit(0)

# Read the .env file
with open(ENV_FILE_PATH, 'r') as file:
    env_content = file.read()

# Check if COMMUNICATOR_BOT_USERNAME is already in the file
communicator_bot_pattern = r'^COMMUNICATOR_BOT_USERNAME=(.*)$'
match = re.search(communicator_bot_pattern, env_content, re.MULTILINE)

if match:
    current_value = match.group(1)
    
    if current_value == CORRECT_BOT_USERNAME:
        print(f"COMMUNICATOR_BOT_USERNAME is already set to {CORRECT_BOT_USERNAME}")
        sys.exit(0)
    
    # Replace the existing value with the correct one
    new_content = re.sub(
        communicator_bot_pattern,
        f'COMMUNICATOR_BOT_USERNAME={CORRECT_BOT_USERNAME}',
        env_content,
        flags=re.MULTILINE
    )
    
    print(f"Updating COMMUNICATOR_BOT_USERNAME from '{current_value}' to '{CORRECT_BOT_USERNAME}'")
else:
    # Add the variable to the end of the file
    new_content = env_content.rstrip() + f"\nCOMMUNICATOR_BOT_USERNAME={CORRECT_BOT_USERNAME}\n"
    print(f"Adding COMMUNICATOR_BOT_USERNAME={CORRECT_BOT_USERNAME} to .env file")

# Write the updated content back to the file
with open(ENV_FILE_PATH, 'w') as file:
    file.write(new_content)

print("Environment variable updated successfully!")
print("Please restart the bot for the changes to take effect.") 