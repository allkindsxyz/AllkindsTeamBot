#!/usr/bin/env python3
"""
Script to check and fix the on_find_match_callback function to ensure
it properly forwards to handle_find_match_message and has proper error handling.
"""

import os
import re
import sys

# Define the file path
START_PY_PATH = "src/bot/handlers/start.py"

if not os.path.exists(START_PY_PATH):
    print(f"Error: {START_PY_PATH} not found!")
    sys.exit(1)

# Read the file content
with open(START_PY_PATH, 'r') as file:
    content = file.read()

# Pattern to match the on_find_match_callback function
# We want to make sure it has proper session validation and error handling
pattern = re.compile(
    r'async def on_find_match_callback\('
    r'.*?callback: types\.CallbackQuery, state: FSMContext, session: AsyncSession = None'
    r'.*?\) -> None:.*?'
    r'"""Handle the \'Find Match\' button from inline keyboard.""".*?'
    r'(.*?)'  # Capture the entire function body
    r'(async def .*?)'  # Next function definition
    , re.DOTALL)

# Find the function in the content
match = pattern.search(content)

if not match:
    print("Could not find the on_find_match_callback function in the file.")
    sys.exit(1)

# Check if the function already has robust error handling
function_body = match.group(1)

# If the function doesn't have robust error handling around handle_find_match_message,
# update it to ensure it properly forwards and handles errors
if "try:" in function_body and "except Exception as e:" in function_body:
    print("The on_find_match_callback function already has error handling. No changes needed.")
    sys.exit(0)

# Create a new function body with improved error handling and session validation
new_function_body = '''
    """Handle the 'Find Match' button from inline keyboard."""
    logger.info(f"[DEBUG] Find Match callback triggered by user {callback.from_user.id}")
    logger.info(f"[DEBUG] Callback data: '{callback.data}'")
    logger.info(f"[DEBUG] Session available: {session is not None}, type: {type(session) if session else 'None'}")
    
    # Log state data
    data = await state.get_data()
    logger.info(f"[DEBUG] State data: {data}")
    group_id = data.get("current_group_id")
    logger.info(f"[DEBUG] Group ID from state: {group_id}")
    
    # Answer callback to clear the query
    await callback.answer()
    
    # Validate session
    if not session:
        logger.error(f"No database session available in on_find_match_callback for user {callback.from_user.id}")
        await callback.message.answer("❌ Database connection error. Please try again or use /start to restart.")
        return
    
    # Validate group_id
    if not group_id:
        logger.error(f"Missing group_id in state for user {callback.from_user.id}")
        await callback.message.answer("Please select a group first.")
        return
    
    # Forward to the common handler
    try:
        logger.info(f"[DEBUG] Forwarding to handle_find_match_message for user {callback.from_user.id}")
        await handle_find_match_message(callback.message, state, session)
    except Exception as e:
        logger.exception(f"[ERROR] Exception in on_find_match_callback: {e}")
        await callback.message.answer("❌ An error occurred while processing your request. Please try again.")
'''

# Replace the function body in the content
new_content = re.sub(
    r'async def on_find_match_callback\('
    r'.*?callback: types\.CallbackQuery, state: FSMContext, session: AsyncSession = None'
    r'.*?\) -> None:.*?'
    r'"""Handle the \'Find Match\' button from inline keyboard.""".*?'
    r'(?:.*?)(?=async def )',  # Non-capturing group up to the next function
    f"async def on_find_match_callback(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession = None) -> None:{new_function_body}\n\n",
    content,
    flags=re.DOTALL
)

# Check if changes were made
if content == new_content:
    print("No changes were needed to the on_find_match_callback function.")
    sys.exit(0)

# Write the changes back to the file
with open(START_PY_PATH, 'w') as file:
    file.write(new_content)

print("Successfully updated the on_find_match_callback function.")
print("Added robust error handling and session validation.")
print("Ensures proper forwarding to handle_find_match_message.") 