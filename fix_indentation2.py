#!/usr/bin/env python3
import re
import sys
from pathlib import Path

def fix_indentation(file_path):
    """Fix indentation issues in the start.py file."""
    print(f"Processing {file_path}...")
    
    # Read the file content
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Create a backup
    backup_path = f"{file_path}.bak.before_fix2"
    with open(backup_path, 'w') as f:
        f.write(content)
    print(f"Created backup at {backup_path}")
    
    # Fix patterns where "if" statements are incorrectly indented with 8 spaces
    content = re.sub(r'^(\s{8})(if .+:)$', r'    \2', content, flags=re.MULTILINE)
    
    # Fix patterns where "await" statements are incorrectly indented
    content = re.sub(r'^(\s{8})(await .+)$', r'    \2', content, flags=re.MULTILINE)
    
    # Fix patterns where "keyboard =" is incorrectly indented
    content = re.sub(r'^(\s{8})(keyboard = .+)$', r'    \2', content, flags=re.MULTILINE)
    
    # Fix patterns where "except" matches with proper indentation
    content = re.sub(r'^(\s{4})(except .+:)$', r'    \2', content, flags=re.MULTILINE)
    
    # Fix patterns where "else:" needs proper indentation
    content = re.sub(r'^\s*(else:)$', r'    \1', content, flags=re.MULTILINE)
    
    # Fix cases where an if statement appears at the start of a line but should be indented
    content = re.sub(r'^(if .+:)$', r'    \1', content, flags=re.MULTILINE)
    
    # Write the fixed content
    with open(file_path, 'w') as f:
        f.write(content)
    
    print(f"Fixed indentation issues in {file_path}")

if __name__ == "__main__":
    target_file = Path("src/bot/handlers/start.py")
    if not target_file.exists():
        print(f"Error: File {target_file} not found")
        sys.exit(1)
    
    fix_indentation(target_file)
    print("Done!") 