#!/usr/bin/env python3
"""
Script to remove the floating text at line 9943 in start.py
"""

import os
import sys

# Define the file path
START_PY_PATH = "src/bot/handlers/start.py"

if not os.path.exists(START_PY_PATH):
    print(f"Error: {START_PY_PATH} not found!")
    sys.exit(1)

# Read the file content
with open(START_PY_PATH, 'r') as file:
    lines = file.readlines()

# Target problematic line
line_number = 9943
if line_number - 1 < len(lines):
    line = lines[line_number - 1].strip()
    print(f"Line {line_number}: {line}")
    
    if 'potential matches for user' in line:
        print(f"Removing floating text at line {line_number}")
        lines.pop(line_number - 1)
        
        # Write the modified content back to the file
        with open(START_PY_PATH, 'w') as file:
            file.writelines(lines)
        
        print(f"Successfully removed floating text")
    else:
        print(f"Line doesn't match expected pattern, no changes made")
else:
    print(f"Error: Line {line_number} doesn't exist in the file")
    sys.exit(1)

print("Please rebuild the application to verify the fix.") 