#!/usr/bin/env python3
"""
Script to fix the unterminated string literal in start.py at line 9908
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

# Find the line with the unterminated string literal
error_line_number = 9908
if error_line_number - 1 < len(lines):
    error_line = lines[error_line_number - 1]
    print(f"Original line {error_line_number}: {error_line}")
    
    # Fix the line - complete the f-string
    if 'logger.info(f"Found {len(match_results)}' in error_line and not error_line.strip().endswith('"'):
        lines[error_line_number - 1] = 'logger.info(f"Found {len(match_results)} potential matches for user {db_user.id} in group {group_id}")\n'
        print(f"Fixed line {error_line_number}: {lines[error_line_number - 1]}")
    else:
        print(f"Line doesn't match expected pattern: {error_line}")
        sys.exit(1)
else:
    print(f"Error: Line {error_line_number} doesn't exist in the file")
    sys.exit(1)

# Write the modified content back to the file
with open(START_PY_PATH, 'w') as file:
    file.writelines(lines)

print(f"Successfully fixed the unterminated string literal at line {error_line_number}.")
print("Please rebuild the application to verify the fix.") 