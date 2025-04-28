#!/usr/bin/env python3
"""
Adds enhanced debug logging to find match functions to help diagnose issues.
"""

import re
import sys
from pathlib import Path

# Files to modify
START_PY = "src/bot/handlers/start.py" 
MATCH_REPO_PY = "src/db/repositories/match_repo.py"

def add_debug_to_function(filepath, func_pattern, debug_msg):
    """Add debug logging to a function in a file."""
    print(f"Looking for {func_pattern} in {filepath}")
    path = Path(filepath)
    
    if not path.exists():
        print(f"Error: File not found: {filepath}")
        return False
    
    content = path.read_text()
    
    # Find the function
    func_match = re.search(func_pattern, content)
    if not func_match:
        print(f"Function not found with pattern: {func_pattern}")
        return False
    
    # Add debug at the start of function body
    func_start = func_match.start()
    func_end = content.find(":", func_start) + 1
    next_line = content.find("\n", func_end) + 1
    
    # Skip if debug already exists
    if "DEBUG_MATCH" in content[next_line:next_line+200]:
        print("Debug logging already exists")
        return False
    
    # Create backup
    backup_path = path.with_suffix(f"{path.suffix}.bak")
    backup_path.write_text(content)
    print(f"Created backup: {backup_path}")
    
    # Add debug line
    debug_line = f'    print(f"{debug_msg}")\n    logger.info(f"{debug_msg}")\n'
    new_content = content[:next_line] + debug_line + content[next_line:]
    
    # Write updated content
    path.write_text(new_content)
    print(f"Added debug to {func_pattern}")
    return True

def main():
    """Add debug logging to find match functions."""
    print("Adding debug logging to find match functions...")
    
    # Functions to add debugging to
    functions = [
        (START_PY, r"async def on_find_match_callback\(", "DEBUG_MATCH: on_find_match_callback called with data={callback.data}"),
        (START_PY, r"async def handle_find_match_message\(", "DEBUG_MATCH: handle_find_match_message called, session={session is not None}"),
        (MATCH_REPO_PY, r"async def find_matches\(", "DEBUG_MATCH: find_matches called with user_id={user_id}, group_id={group_id}")
    ]
    
    results = []
    for filepath, pattern, msg in functions:
        result = add_debug_to_function(filepath, pattern, msg)
        results.append(result)
    
    if any(results):
        print("Debug logging added successfully. Restart the bot to see debug output.")
        return 0
    else:
        print("No changes made. Debug logging may already exist.")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 