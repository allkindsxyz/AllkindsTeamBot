#!/usr/bin/env python3
"""
Script to fix HTML span tags in confirmation messages that cause Telegram parsing errors
"""

import os
import sys
import re

# Define the file path
START_PY_PATH = "src/bot/handlers/start.py"

if not os.path.exists(START_PY_PATH):
    print(f"Error: {START_PY_PATH} not found!")
    sys.exit(1)

print(f"Fixing HTML span tags in {START_PY_PATH}...")

# Read the file content
with open(START_PY_PATH, 'r') as file:
    content = file.read()

# Create a backup
with open(f"{START_PY_PATH}.html_fix_bak", 'w') as backup_file:
    backup_file.write(content)
    print(f"Created backup at {START_PY_PATH}.html_fix_bak")

# Pattern to locate span tags with class='hidden'
span_pattern = r"confirmation_text \+= f\"<span class='hidden'>group_id:\{group_id\}</span>\""

# Replacement - comment out the line
span_replacement = r"# Removed HTML tag that caused Telegram errors\n        # confirmation_text += f\"<span class='hidden'>group_id:{group_id}</span>\""

# Replace the span tags
updated_content = re.sub(span_pattern, span_replacement, content)

# Check if any replacements were made
if updated_content == content:
    print("No span tags found to replace.")
    sys.exit(0)

# Write the updated content
with open(START_PY_PATH, 'w') as file:
    file.write(updated_content)

print("HTML span tags fixed successfully!") 