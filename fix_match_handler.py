#!/usr/bin/env python3
"""
Script to fix the match finding logic in handle_find_match_message to ensure
points are only deducted when matches are found and to eliminate redundant
match finding operations.
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

# The pattern to match the section where we find matches and then deduct points
# This captures the code between finding matches and deducting points
pattern = re.compile(
    r'(# Find matches first.*?try\s*:\s*'  # Beginning of the match finding
    r'match_results = await find_matches.*?'  # Find matches function call
    r'logger\.info\(f"Found \{len\(match_results\)\}.*?'  # Logging after finding matches
    r')(.*?'  # Group 2: Code between finding matches and deducting points
    r'# Deduct points.*?'  # Comment for deducting points
    r'old_points = db_user\.points.*?'  # Start of point deduction
    r'db_user\.points -= FIND_MATCH_COST.*?'  # Point deduction
    r'await session\.commit\(\).*?'  # Committing the change
    r'logger\.info\(f"Deducted \{FIND_MATCH_COST\}.*?'  # Log message for deduction
    r')(try\s*:\s*'  # Group 3: Second attempt to find matches
    r'match_results = await find_matches.*?'  # Duplicate find matches call
    r'logger\.info\(f"Found \{len\(match_results\)\}.*?)'  # Duplicate logging
    , re.DOTALL)

# The replacement - finds matches once and only deducts points if matches are found
replacement = r'''\1
        if not match_results or len(match_results) == 0:
            # No matches found - no need to deduct points
            logger.info(f"No matches found for user {db_user.id} in group {group_id}")
            
            try:
                # Send no matches message
                await message.answer(
                    "😔 No matches found at this time. Please try again later when more group members have answered questions."
                )
                
                # Show group menu to maintain context
                await show_group_menu(message, group_id, group.name, state, session=session)
            except Exception as menu_error:
                logger.error(f"Error showing group menu after no matches: {menu_error}")
                await message.answer("Please use /start to return to the main menu.")
            
            return
        
        # Deduct points from the initiating user - only now that we know there are matches
        old_points = db_user.points
        db_user.points -= FIND_MATCH_COST
        session.add(db_user)
        await session.commit()
        logger.info(f"Deducted {FIND_MATCH_COST} points from user {db_user.id}, new balance: {db_user.points} (was {old_points})")
        
        # We already have match results, no need to find matches again
'''

# Apply the replacement
modified_content = re.sub(pattern, replacement, content)

# Check if changes were made
if content == modified_content:
    print("No changes were made. The pattern might not match the content.")
    sys.exit(1)

# Write the changes back to the file
with open(START_PY_PATH, 'w') as file:
    file.write(modified_content)

print("Successfully updated the match finding logic in handle_find_match_message function.")
print("Points are now only deducted when matches are actually found.")
print("The redundant second call to find_matches has been removed.") 