#!/usr/bin/env python3
"""
Script to fix all communicator bot issues:
1. Fix chat link generation in on_start_anon_chat function
2. Ensure COMMUNICATOR_BOT_USERNAME is correctly used from settings
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

# Define the file paths
START_PY_PATH = "src/bot/handlers/start.py"
ENV_FILE_PATH = ".env"

def check_env_file():
    """Check .env file for COMMUNICATOR_BOT_USERNAME and update if needed"""
    try:
        if not os.path.exists(ENV_FILE_PATH):
            logger.warning(f"No .env file found at {ENV_FILE_PATH}. Will create one.")
            env_content = "COMMUNICATOR_BOT_USERNAME=AllkindsCommunicatorBot\n"
            with open(ENV_FILE_PATH, "w") as f:
                f.write(env_content)
            logger.info(f"Created .env file with COMMUNICATOR_BOT_USERNAME=AllkindsCommunicatorBot")
            return True
            
        with open(ENV_FILE_PATH, "r") as f:
            env_content = f.read()
            
        # Check if COMMUNICATOR_BOT_USERNAME is already set
        if re.search(r'^COMMUNICATOR_BOT_USERNAME=', env_content, re.MULTILINE):
            # Update existing variable if it doesn't have the correct value
            if not re.search(r'^COMMUNICATOR_BOT_USERNAME=AllkindsCommunicatorBot', env_content, re.MULTILINE):
                env_content = re.sub(
                    r'^COMMUNICATOR_BOT_USERNAME=.*$', 
                    'COMMUNICATOR_BOT_USERNAME=AllkindsCommunicatorBot', 
                    env_content, 
                    flags=re.MULTILINE
                )
                with open(ENV_FILE_PATH, "w") as f:
                    f.write(env_content)
                logger.info(f"Updated COMMUNICATOR_BOT_USERNAME in .env file")
                return True
            else:
                logger.info("COMMUNICATOR_BOT_USERNAME already set correctly in .env file")
                return False
        else:
            # Add the variable if it doesn't exist
            env_content += "\nCOMMUNICATOR_BOT_USERNAME=AllkindsCommunicatorBot\n"
            with open(ENV_FILE_PATH, "w") as f:
                f.write(env_content)
            logger.info(f"Added COMMUNICATOR_BOT_USERNAME=AllkindsCommunicatorBot to .env file")
            return True
            
    except Exception as e:
        logger.error(f"Error updating .env file: {e}")
        return False

def fix_on_start_anon_chat():
    """
    Fix the communicator bot username issue in the on_start_anon_chat function.
    """
    if not os.path.exists(START_PY_PATH):
        logger.error(f"Error: {START_PY_PATH} not found!")
        return False
        
    # Create backup of the original file
    backup_path = f"{START_PY_PATH}.fix_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    logger.info(f"Creating backup at {backup_path}")
    shutil.copy2(START_PY_PATH, backup_path)
    
    try:
        # Read the original file
        with open(START_PY_PATH, 'r') as file:
            content = file.read()
        
        # Define the pattern for the deep link generation code
        pattern = r'# Generate a deep link to the communicator bot\s+communicator_bot_username = settings\.COMMUNICATOR_BOT_USERNAME\s+# Ensure username is valid before creating the link\s+if not communicator_bot_username or communicator_bot_username == "":\s+communicator_bot_username = "AllkindsCommunicatorBot"\s+# Fallback to a known username\s+logger\.warning\(f"Using fallback communicator bot username: \{communicator_bot_username\}"\)\s+\s+# Create the deep link with proper validation\s+deep_link = f"https://t\.me/\{communicator_bot_username\}\?start=chat_\{chat_id\}"'
        
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
        
        # Alternative pattern in case the first one doesn't match
        alt_pattern = r'# Generate a deep link to the communicator bot\s+communicator_bot_username\s*=\s*settings\.COMMUNICATOR_BOT_USERNAME\s+.*?\s+deep_link\s*=\s*f"https://t\.me/\{communicator_bot_username\}\?start=chat_\{chat_id\}"'
        
        # If no changes were made, try with the alternative pattern
        if new_content == content:
            logger.warning("Primary pattern didn't match, trying alternative pattern...")
            new_content = re.sub(alt_pattern, replacement, content, flags=re.DOTALL)
        
        # Check if any changes were made
        if new_content == content:
            logger.warning("No changes made to on_start_anon_chat - patterns did not match.")
            
            # Try a more general approach - find all instances of deep_link generation
            logger.info("Trying to find all instances of deep link generation...")
            deep_link_pattern = r'deep_link\s*=\s*f"https://t\.me/[^}]*\{[^}]+\}\?start=chat_\{[^}]+\}"'
            
            matches = re.findall(deep_link_pattern, content)
            if matches:
                logger.info(f"Found {len(matches)} potential deep link generations.")
                for i, match in enumerate(matches):
                    logger.info(f"Match {i+1}: {match}")
                
                # We found matches but couldn't replace them with regex
                # Let's provide instructions for manual edit
                logger.warning("Couldn't automatically replace deep link generation code.")
                logger.warning("Please manually check the following sections in your code:")
                for i, match in enumerate(matches):
                    logger.warning(f"{i+1}. {match}")
                
                logger.warning("Replace them with the following template:")
                logger.warning(replacement)
            else:
                logger.error("No deep link generation patterns found in the code.")
            
            return False
        
        # Write the modified content back to the file
        with open(START_PY_PATH, 'w') as file:
            file.write(new_content)
        
        logger.info("Successfully updated the on_start_anon_chat function with improved error handling.")
        return True
        
    except Exception as e:
        logger.error(f"Error fixing the on_start_anon_chat function: {e}")
        return False

def fix_other_deep_links():
    """Fix other deep link generations in the file"""
    try:
        # Read the file
        with open(START_PY_PATH, 'r') as file:
            content = file.read()
        
        # Pattern for other deep link generations
        other_deep_link_pattern = r'deep_link\s*=\s*f"https://t\.me/\{([^}]+)\}\?start=([^"]+)"'
        
        # Find all matches
        matches = re.finditer(other_deep_link_pattern, content)
        
        # Flag to track if any changes were made
        changes_made = False
        
        # Go through each match and modify the content
        modified_content = content
        for match in matches:
            # Get the full match and the bot username variable
            full_match = match.group(0)
            bot_username_var = match.group(1)
            start_param = match.group(2)
            
            # Skip if it's already fixed
            if "AllkindsCommunicatorBot" in full_match and "try:" in full_match[:100]:
                continue
                
            # Create a safer version with fallback
            replacement = f"""# Ensure bot username is valid
            bot_username = {bot_username_var}
            if not bot_username or bot_username == "":
                bot_username = "AllkindsCommunicatorBot"  # Fallback
                logger.warning(f"Using fallback bot username: {{bot_username}}")
            
            # Remove @ if it's included
            if isinstance(bot_username, str) and bot_username.startswith('@'):
                bot_username = bot_username[1:]
                
            deep_link = f"https://t.me/{{bot_username}}?start={start_param}" """
            
            # Replace in the content
            modified_content = modified_content.replace(full_match, replacement)
            changes_made = True
        
        # If changes were made, write back to the file
        if changes_made:
            with open(START_PY_PATH, 'w') as file:
                file.write(modified_content)
            logger.info("Fixed additional deep link generations in the code")
            return True
        else:
            logger.info("No additional deep link generations found or needed fixing")
            return False
            
    except Exception as e:
        logger.error(f"Error fixing other deep links: {e}")
        return False

if __name__ == "__main__":
    logger.info("Starting comprehensive fix for communicator bot issues...")
    
    env_updated = check_env_file()
    on_start_anon_chat_fixed = fix_on_start_anon_chat()
    other_deep_links_fixed = fix_other_deep_links()
    
    if env_updated or on_start_anon_chat_fixed or other_deep_links_fixed:
        logger.info("""
        ✅ Updates completed!
        
        Changes made:
        - Environment file (.env): {}
        - on_start_anon_chat function: {}
        - Other deep link generations: {}
        
        Please restart your bot for the changes to take effect.
        """.format(
            "Updated" if env_updated else "No changes needed",
            "Fixed" if on_start_anon_chat_fixed else "No changes made",
            "Fixed" if other_deep_links_fixed else "No changes needed"
        ))
    else:
        logger.info("No changes were made. Your code may already be up to date.")
    
    logger.info("Script completed.") 