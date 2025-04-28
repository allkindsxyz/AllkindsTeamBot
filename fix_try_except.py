#!/usr/bin/env python3
"""
Script to fix the try-except block structure in start.py at line 9906-9908
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
    lines = file.readlines()

# Find the try-except block and fix it
try_line_number = 9906
log_line_number = 9908

if try_line_number - 1 < len(lines) and log_line_number - 1 < len(lines):
    try_line = lines[try_line_number - 1]
    log_line = lines[log_line_number - 1]
    
    print(f"Original try line {try_line_number}: {try_line}")
    print(f"Original log line {log_line_number}: {log_line}")
    
    # Check if the try block doesn't have an except
    if 'try:' in try_line and not any('except' in line for line in lines[try_line_number:try_line_number + 10]):
        # Fix the structure by properly indenting and adding an except block
        lines[log_line_number - 1] = '            logger.info(f"Found {len(match_results)} potential matches for user {db_user.id} in group {group_id}")\n'
        
        # Add the except block after the log line
        lines.insert(log_line_number, '        except Exception as match_error:\n')
        lines.insert(log_line_number + 1, '            logger.error(f"Error in find_matches call: {str(match_error)}")\n')
        lines.insert(log_line_number + 2, '            import traceback\n')
        lines.insert(log_line_number + 3, '            logger.error(f"Traceback: {traceback.format_exc()}")\n')
        lines.insert(log_line_number + 4, '            \n')
        lines.insert(log_line_number + 5, '            await message.answer("❌ An error occurred while finding matches. Please try again later.")\n')
        lines.insert(log_line_number + 6, '            await show_group_menu(message, group_id, group.name, state, session=session)\n')
        lines.insert(log_line_number + 7, '            return\n')
        
        print(f"Fixed the try-except block structure at lines {try_line_number}-{log_line_number}")
    else:
        print(f"The try block may already have an except, or this is not the right pattern to fix.")
        sys.exit(1)
else:
    print(f"Error: Line {try_line_number} or {log_line_number} doesn't exist in the file")
    sys.exit(1)

# Remove the duplicate potential matches line at line 9934
potential_matches_line = 9934
if potential_matches_line - 1 < len(lines):
    duplicate_line = lines[potential_matches_line - 1]
    if 'potential matches for user' in duplicate_line:
        lines.pop(potential_matches_line - 1)
        print(f"Removed duplicate line at {potential_matches_line}: {duplicate_line.strip()}")

# Write the modified content back to the file
with open(START_PY_PATH, 'w') as file:
    file.writelines(lines)

print(f"Successfully fixed the try-except block structure.")
print("Please rebuild the application to verify the fix.") 