#!/usr/bin/env python3
"""
Debug script to diagnose issues with matching and team navigation functionality.
This script will add enhanced logging to critical handler functions.
"""

import os
import re
import sys
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Define the file to modify
START_HANDLER_FILE = "src/bot/handlers/start.py"

def add_debug_to_handler(filepath, handler_name, prefix_pattern, debug_statement):
    """Add debug logging statements to a specific handler function."""
    file_path = Path(filepath)
    if not file_path.exists():
        logger.error(f"File not found: {filepath}")
        return False
    
    content = file_path.read_text()
    handler_pattern = rf"async def {handler_name}\(.*?\).*?:\n"
    match = re.search(handler_pattern, content, re.DOTALL)
    
    if not match:
        logger.error(f"Handler {handler_name} not found in {filepath}")
        return False
    
    handler_start = match.end()
    
    # Find the indentation of the first line after the function definition
    next_line_match = re.search(r'\n(\s+)', content[handler_start:])
    if not next_line_match:
        logger.error(f"Could not determine indentation for {handler_name}")
        return False
    
    indentation = next_line_match.group(1)
    
    # Create the debug statement with proper indentation
    debug_log = f"{indentation}{debug_statement}\n"
    
    # Find the position to insert after the docstring or function definition
    docstring_pattern = rf'{indentation}""".*?"""\n'
    docstring_match = re.search(docstring_pattern, content[handler_start:], re.DOTALL)
    
    if docstring_match:
        insert_position = handler_start + docstring_match.end()
    else:
        # If no docstring, insert after the first line with code
        first_line_match = re.search(rf"\n{indentation}[^\s]", content[handler_start:])
        if first_line_match:
            insert_position = handler_start + first_line_match.start() + 1
        else:
            insert_position = handler_start
    
    # Check if the debug statement is already there
    if prefix_pattern in content[insert_position:insert_position+200]:
        logger.info(f"Debug statements already added to {handler_name}")
        return True
    
    # Insert the debug statement
    new_content = content[:insert_position] + debug_log + content[insert_position:]
    file_path.write_text(new_content)
    
    logger.info(f"Added debug statements to {handler_name}")
    return True

def add_all_debug_statements():
    """Add debug statements to all relevant handlers."""
    # Debug statement for on_go_to_group
    team_handler_debug = 'logger.info(f"[DEBUG_TEAM] Entering on_go_to_group for user {callback.from_user.id}, data={callback.data}")'
    add_debug_to_handler(START_HANDLER_FILE, "on_go_to_group", "[DEBUG_TEAM]", team_handler_debug)
    
    # Debug statement for on_find_match_callback
    match_callback_debug = 'logger.info(f"[DEBUG_MATCH] on_find_match_callback triggered by user {callback.from_user.id}, data={callback.data}")'
    add_debug_to_handler(START_HANDLER_FILE, "on_find_match_callback", "[DEBUG_MATCH]", match_callback_debug)
    
    # Debug statement for handle_find_match_message
    match_handler_debug = 'logger.info(f"[DEBUG_MATCH] handle_find_match_message for user {message.from_user.id}, session={session is not None}")'
    add_debug_to_handler(START_HANDLER_FILE, "handle_find_match_message", "[DEBUG_MATCH]", match_handler_debug)
    
    # Debug statement for find_matches database function
    match_db_debug = 'logger.info(f"[DEBUG_MATCH_DB] find_matches called with user_id={user_id}, group_id={group_id}")'
    add_debug_to_handler("src/db/repositories/match_repo.py", "find_matches", "[DEBUG_MATCH_DB]", match_db_debug)
    
    return True

def check_registrations():
    """Check that handlers are properly registered in the dispatcher."""
    filepath = START_HANDLER_FILE
    file_path = Path(filepath)
    if not file_path.exists():
        logger.error(f"File not found: {filepath}")
        return
    
    content = file_path.read_text()
    
    # Check for go_to_group registration
    go_to_group_pattern = r'dp\.callback_query\.register\(on_go_to_group,\s+F\.data\.startswith\("go_to_group:"\)\)'
    if not re.search(go_to_group_pattern, content):
        logger.warning("on_go_to_group handler may not be properly registered!")
    else:
        logger.info("on_go_to_group handler is properly registered.")
    
    # Check for find_match callback registration
    find_match_pattern = r'dp\.callback_query\.register\(on_find_match_callback,\s+F\.data\s*==\s*"find_match"\)'
    if not re.search(find_match_pattern, content):
        logger.warning("on_find_match_callback handler may not be properly registered!")
    else:
        logger.info("on_find_match_callback handler is properly registered.")
    
    # Check for message handler registration
    find_match_msg_pattern = r'dp\.message\.register\(handle_find_match_message,\s+F\.text\s*==\s*"Find Match"'
    if not re.search(find_match_msg_pattern, content):
        logger.warning("handle_find_match_message handler may not be properly registered!")
    else:
        logger.info("handle_find_match_message handler is properly registered.")

def main():
    """Main function to run diagnostics and add debugging."""
    logger.info("Starting diagnostic for matching and team navigation...")
    
    # Check handler registrations
    check_registrations()
    
    # Add debug statements to handlers
    if add_all_debug_statements():
        logger.info("Debug statements added successfully.")
        logger.info("Please restart the bot to apply changes.")
    else:
        logger.error("Failed to add debug statements.")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 