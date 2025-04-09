#!/usr/bin/env python3
import re
from pathlib import Path

def fix_file():
    file_path = Path("src/bot/handlers/start.py")
    print(f"Processing {file_path}...")
    
    # Read the file
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Create a backup
    backup_path = f"{file_path}.bak.cmd_start_fix"
    with open(backup_path, 'w') as f:
        f.write(content)
    print(f"Created backup at {backup_path}")
    
    # Find the section with the indentation issue using a targeted approach
    pattern = r"                    if is_member:.*?return\n                    else:\n                    # User is not in this group, ask to join"
    replacement = r"                    if is_member:.*?return\n                    else:\n                        # User is not in this group, ask to join"
    
    # Use regex to fix this specific indentation issue
    fixed_content = re.sub(pattern, replacement, content, flags=re.DOTALL)
    
    # Also fix other indentation issues in the file
    lines = fixed_content.split('\n')
    fixed_lines = []
    
    for i, line in enumerate(lines):
        # Fix specific indentation patterns
        # Fix "else:" at beginning of line that should be indented
        if line.strip() == "else:" and i > 0 and lines[i-1].strip().endswith("return"):
            leading_spaces = len(lines[i-1]) - len(lines[i-1].lstrip())
            fixed_lines.append(" " * leading_spaces + line.strip())
        # Keep line as is if no pattern matched
        else:
            fixed_lines.append(line)
    
    # Write the fixed content
    with open(file_path, 'w') as f:
        f.write('\n'.join(fixed_lines))
    
    print("Fixed indentation issues in cmd_start function")

if __name__ == "__main__":
    fix_file()
    print("Done!") 