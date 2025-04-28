#!/usr/bin/env python3
"""
Script to fix the orphaned except block in start.py
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

# The issue is that there's an orphaned except block at around line 9943
# First try block is from line 9906-9908 (properly closed with an except at line 9909)
# Second block is the orphaned except at line 9943

# We need to remove the orphaned except block from line 9943 to the end of its scope
# Let's identify the start and end of the orphaned block
start_line = 9943  # Line of the orphaned except
end_line = None

# Find where the orphaned except block ends (usually before the next if statement)
for i in range(start_line, min(start_line + 30, len(lines))):
    line = lines[i].strip()
    if line.startswith('if ') or line.startswith('# Get the') or line.startswith('# Deduct'):
        end_line = i
        break

if end_line is None:
    print("Error: Could not find the end of the orphaned except block")
    sys.exit(1)

print(f"Identified orphaned except block from line {start_line} to line {end_line-1}")

# Check if we've identified the correct section
for i in range(start_line - 1, end_line):
    print(f"Line {i+1}: {lines[i].strip()}")

# Remove the orphaned except block
lines_to_remove = end_line - start_line
print(f"Removing {lines_to_remove} lines from {start_line} to {end_line-1}")
del lines[start_line - 1:end_line]

# Write the modified content back to the file
with open(START_PY_PATH, 'w') as file:
    file.writelines(lines)

print(f"Successfully removed the orphaned except block.")
print("Please rebuild the application to verify the fix.") 