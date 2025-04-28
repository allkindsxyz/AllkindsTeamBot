#!/usr/bin/env python3
"""
Script to fix deep link generation in both handle_start_anon_chat and on_start_anon_chat functions.
This script adds better error handling, validation, and ensures consistent bot username usage.
"""

import os
import re
import sys
import shutil
from datetime import datetime
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('fix_deep_link.log')
    ]
)
logger = logging.getLogger(__name__)

# Define the correct bot username
CORRECT_BOT_USERNAME = "AllkindsCommunicatorBot"

# Path to the main file that needs fixing
START_PY_PATH = "src/bot/handlers/start.py"

# Create backup of the original file
def create_backup(file_path):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{file_path}.deep_link_bak_{timestamp}"
    try:
        shutil.copy2(file_path, backup_path)
        logger.info(f"Created backup at {backup_path}")
        return True
    except Exception as e:
        logger.error(f"Error creating backup: {e}")
        return False

def fix_handle_start_anon_chat():
    """Fix deep link generation in handle_start_anon_chat function"""
    if not create_backup(START_PY_PATH):
        logger.error("Failed to create backup, aborting to be safe.")
        return False
    
    # Read the file content
    try:
        with open(START_PY_PATH, 'r') as file:
            content = file.read()
    except Exception as e:
        logger.error(f"Error reading file {START_PY_PATH}: {e}")
        return False
    
    # Improved logic for bot username checking and deep link generation in handle_start_anon_chat
    pattern1 = r"""(\s+# Create deep link to communicator bot\s+logger\.debug\(f"\[START_ANON_CHAT\] Creating deep link to communicator bot"\)\s+bot_username = settings\.COMMUNICATOR_BOT_USERNAME\s+if not bot_username:(?:[^#]+?))bot_username = "AllkindsChatBot"((?:[^#]+?)deep_link = f"https://t\.me/{bot_username}\?start=chat_)"""
    
    replacement1 = r"""\1bot_username = "AllkindsCommunicatorBot"  # Always use the correct bot username as fallback
        # Log the fallback use for monitoring
        logger.warning(f"[DEEP_LINK] Using fallback communicator bot username: {bot_username}")
        
        # Double check username is not empty after fallback (defensive programming)
        if not bot_username or bot_username.strip() == "":
            logger.error("[DEEP_LINK] Critical error: Bot username is still empty after fallback")
            bot_username = "AllkindsCommunicatorBot"  # Final safety check
            
\2"""

    # Improved logic for on_start_anon_chat function
    pattern2 = r"""(\s+# Generate a deep link to the communicator bot\s+communicator_bot_username = settings\.COMMUNICATOR_BOT_USERNAME\s+# Ensure username is valid before creating the link\s+if not communicator_bot_username or communicator_bot_username == "":(?:[^#]+?))communicator_bot_username = "AllkindsChatBot"((?:[^#]+?)deep_link = f"https://t\.me/{communicator_bot_username}\?start=chat_)"""
    
    replacement2 = r"""\1communicator_bot_username = "AllkindsCommunicatorBot"  # Always use the correct bot username
            # Log the fallback use for diagnostic purposes
            logger.warning(f"[DEEP_LINK] Using fallback communicator bot username: {communicator_bot_username}")
            
            # Add additional validation to ensure username is never empty (extra safety)
            if not communicator_bot_username or communicator_bot_username.strip() == "":
                logger.error("[DEEP_LINK] Critical error: Bot username is still empty after fallback")
                communicator_bot_username = "AllkindsCommunicatorBot"  # Final safety check
\2"""
    
    # Apply replacements with error checking
    try:
        # First replacement
        updated_content = re.sub(pattern1, replacement1, content, flags=re.DOTALL)
        if updated_content == content:
            logger.warning("First pattern (handle_start_anon_chat) didn't match any content")
        else:
            logger.info("Updated handle_start_anon_chat function")
            
        # Second replacement
        final_content = re.sub(pattern2, replacement2, updated_content, flags=re.DOTALL)
        if final_content == updated_content:
            logger.warning("Second pattern (on_start_anon_chat) didn't match any content")
        else:
            logger.info("Updated on_start_anon_chat function")
        
        # Only proceed if at least one change was made
        if final_content == content:
            logger.warning("No changes were made to the file content")
            return False
            
        # Write updated content back to the file
        with open(START_PY_PATH, 'w') as file:
            file.write(final_content)
        logger.info(f"Updated deep link generation logic in {START_PY_PATH}")
        return True
    except Exception as e:
        logger.error(f"Error updating file: {e}")
        return False

def fix_import_section():
    """Ensure necessary imports are present"""
    try:
        with open(START_PY_PATH, 'r') as file:
            content = file.read()
            
        # Check if settings import is present
        if "from src.core.config import get_settings" not in content:
            # Find the imports section and add the missing import
            import_pattern = r"(from|import).*?\n\n"
            import_section = re.search(import_pattern, content, re.DOTALL)
            if import_section:
                # Add the import at the end of the import section
                updated_content = content[:import_section.end()] + "from src.core.config import get_settings\n\n" + content[import_section.end():]
                with open(START_PY_PATH, 'w') as file:
                    file.write(updated_content)
                logger.info("Added missing import for settings")
            else:
                logger.warning("Could not locate import section to add missing import")
    except Exception as e:
        logger.error(f"Error fixing import section: {e}")

if __name__ == "__main__":
    logger.info("Starting deep link generation fix...")
    if fix_handle_start_anon_chat():
        fix_import_section()
        logger.info("Deep link generation fixes completed successfully!")
        logger.info("Please restart the bot for changes to take effect.")
    else:
        logger.error("Failed to update deep link generation logic.") 