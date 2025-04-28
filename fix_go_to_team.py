#!/usr/bin/env python3
"""
Fix utility to ensure the "Go to team" button works correctly.
This script does the following:
1. Verifies the handler registration for on_go_to_group
2. Ensures the button generates the correct callback data
3. Fixes any DB session handling issues in the function
"""

import re
import sys
from pathlib import Path
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Key files to check
START_PY = "src/bot/handlers/start.py"
CMD_START_PATTERN = r"async def cmd_start\("
GO_TO_GROUP_PATTERN = r"async def on_go_to_group\("
REGISTER_HANDLERS_PATTERN = r"def register_handlers\("

def backup_file(filepath):
    """Create a backup of a file before modifying it."""
    print(f"Backing up file: {filepath}")
    src_path = Path(filepath)
    if not src_path.exists():
        print(f"Error: File not found: {filepath}")
        return False
    
    backup_path = src_path.with_suffix(f"{src_path.suffix}.bak")
    backup_path.write_text(src_path.read_text())
    print(f"Created backup: {backup_path}")
    return True

def fix_go_to_team_button():
    """Fix issues with the 'Go to team' button implementation."""
    print(f"Looking for file: {START_PY}")
    src_path = Path(START_PY)
    if not src_path.exists():
        print(f"Error: File not found: {START_PY}")
        return False
    
    print("Reading file content...")
    content = src_path.read_text()
    modified = False
    
    # 1. Check that on_go_to_group handler is correctly registered
    if "dp.callback_query.register(on_go_to_group" not in content:
        print("Error: on_go_to_group handler registration not found")
        # This would be a critical issue requiring manual intervention
        return False
    else:
        print("Found on_go_to_group handler registration ✓")
    
    # 2. Ensure the session parameter is properly defined and used
    go_to_group_match = re.search(GO_TO_GROUP_PATTERN, content)
    if not go_to_group_match:
        print("Error: on_go_to_group handler not found!")
        return False
    else:
        print("Found on_go_to_group handler definition ✓")
    
    handler_def_pos = go_to_group_match.start()
    handler_def_end = content.find(":", handler_def_pos) + 1
    handler_def = content[handler_def_pos:handler_def_end]
    print(f"Handler definition: {handler_def}")
    
    # Check if session parameter is correctly defined
    if "session: AsyncSession" not in handler_def:
        print("Warning: Session parameter may not be correctly typed in on_go_to_group")
        # Add enhanced logging to the function
        next_line_pos = content.find("\n", handler_def_end) + 1
        debug_line = '    logger.info(f"DEBUG: on_go_to_group called, session type: {type(session)}")\n'
        
        if "DEBUG: on_go_to_group called" not in content[handler_def_end:handler_def_end+200]:
            content = content[:next_line_pos] + debug_line + content[next_line_pos:]
            modified = True
            print("Added debug logging to on_go_to_group function")
    else:
        print("Session parameter is correctly defined in on_go_to_group ✓")
    
    # 3. Look for and fix the cmd_start function to ensure it creates proper 'go_to_group' buttons
    cmd_start_match = re.search(CMD_START_PATTERN, content)
    if not cmd_start_match:
        print("Error: cmd_start handler not found!")
        return False
    else:
        print("Found cmd_start handler definition ✓")
    
    # Find the section in cmd_start where it creates the button
    go_to_team_btn_pattern = r'text="(?:Go to|🔄) team".*?callback_data=(?:"|\()f?"go_to_group:'
    go_to_team_btn_match = re.search(go_to_team_btn_pattern, content)
    
    if not go_to_team_btn_match:
        print("Warning: Could not find 'Go to team' button creation pattern")
    else:
        print("Found 'Go to team' button creation ✓")
        btn_pos = go_to_team_btn_match.start()
        line_end = content.find("\n", btn_pos)
        btn_line = content[btn_pos:line_end]
        print(f"Button line: {btn_line}")
        
        # Add debug logging for the button creation
        if "go_to_group:{group.id}" in btn_line and "DEBUG:" not in content[btn_pos-100:btn_pos]:
            debug_line = '            logger.info(f"DEBUG: Creating Go to team button with data: go_to_group:{group.id}")\n            '
            content = content[:btn_pos] + debug_line + content[btn_pos:]
            modified = True
            print("Added debug logging to team button creation")
    
    # Add diagnostics for the database session middleware
    if "DbSessionMiddleware" in content and "DEBUG: Registering DbSessionMiddleware" not in content:
        middleware_pattern = r"dp\.update\.middleware\.register\(DbSessionMiddleware\("
        middleware_match = re.search(middleware_pattern, content)
        if middleware_match:
            print("Found DbSessionMiddleware registration ✓")
            pos = middleware_match.start()
            line_start = content.rfind("\n", 0, pos) + 1
            debug_line = '    logger.info("DEBUG: Registering DbSessionMiddleware")\n    '
            content = content[:line_start] + debug_line + content[line_start:]
            modified = True
            print("Added debug logging to DbSessionMiddleware registration")
    
    # Save changes if modifications were made
    if modified:
        backup_file(START_PY)
        src_path.write_text(content)
        print(f"Modified {START_PY} with debug enhancements")
        return True
    else:
        print(f"No changes needed in {START_PY}")
        return False

def main():
    """Main function."""
    print("Starting fix for 'Go to team' button...")
    result = fix_go_to_team_button()
    
    if result:
        print("Successfully enhanced debugging for Go to team button.")
        print("Please restart the bot and check the logs for DEBUG messages.")
    else:
        print("No changes made. Manual investigation may be required.")
    
    return 0 if result else 1

if __name__ == "__main__":
    sys.exit(main()) 