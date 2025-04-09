#!/usr/bin/env python3
import re
import sys
from pathlib import Path

def fix_indentation(file_path):
    """Fix indentation issues in the start.py file."""
    print(f"Processing {file_path}...")
    
    # Read the file content
    with open(file_path, 'r') as f:
        lines = f.readlines()
    
    # Create a backup
    backup_path = f"{file_path}.bak.before_fix"
    with open(backup_path, 'w') as f:
        f.writelines(lines)
    print(f"Created backup at {backup_path}")
    
    # Process lines
    fixed_lines = []
    fixed_count = 0
    line_num = 0
    
    for line in lines:
        line_num += 1
        original_line = line
        
        # Fix indentation issues
        if re.match(r'^\s{8}if ', line):
            # Indentation level should be 4 spaces not 8
            line = re.sub(r'^(\s{8})(if .*)', r'    \2', line)
            if line != original_line:
                print(f"Fixed line {line_num}: {original_line.strip()} -> {line.strip()}")
                fixed_count += 1
        
        # Fix other indentation issues like keyboard_buttons.append, await callbacks, etc.
        if re.match(r'^\s{8}(keyboard_buttons\.append|await callback|keyboard =)', line):
            line = re.sub(r'^(\s{8})(.*)', r'    \2', line)
            if line != original_line:
                print(f"Fixed line {line_num}: {original_line.strip()} -> {line.strip()}")
                fixed_count += 1
                
        # Fix missing indentation for if blocks (opposite problem)
        if re.match(r'^if ', line) and line_num > 1 and not lines[line_num-2].strip() == '':
            line = '    ' + line
            if line != original_line:
                print(f"Fixed line {line_num}: {original_line.strip()} -> {line.strip()}")
                fixed_count += 1
        
        fixed_lines.append(line)
    
    # Write the fixed content
    with open(file_path, 'w') as f:
        f.writelines(fixed_lines)
    
    print(f"Fixed {fixed_count} indentation issues")

if __name__ == "__main__":
    target_file = Path("src/bot/handlers/start.py")
    if not target_file.exists():
        print(f"Error: File {target_file} not found")
        sys.exit(1)
    
    fix_indentation(target_file)
    print("Done!") 