#!/usr/bin/env python3
"""
Direct Fix Script

This script directly modifies the necessary code to handle the load_answered_questions callback.
"""

import os
import re
import shutil
from datetime import datetime
import logging
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("direct_fix.log")
    ]
)
logger = logging.getLogger(__name__)

def create_backup(file_path):
    """Create a backup of the file"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{file_path}.bak_{timestamp}"
    shutil.copy2(file_path, backup_path)
    logger.info(f"Created backup at {backup_path}")
    return backup_path

def update_debug_callback():
    """Update the debug_callback function in start.py"""
    start_py_path = "src/bot/handlers/start.py"
    
    if not os.path.exists(start_py_path):
        logger.error(f"File {start_py_path} does not exist")
        return False
    
    # Create backup
    create_backup(start_py_path)
    
    try:
        # Read the file content
        with open(start_py_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Find the debug_callback function
        debug_callback_pattern = r"async def debug_callback\s*\(.*?\).*?(?=async def|$)"
        match = re.search(debug_callback_pattern, content, re.DOTALL)
        
        if not match:
            logger.error("Could not find the debug_callback function")
            return False
            
        debug_callback_function = match.group(0)
        
        # Define handler code once to eliminate duplication
        load_handler_code = """
            logger.info(f"Debug callback handling load_answered_questions for user {callback.from_user.id}")
            try:
                # Import here to avoid circular imports
                from src.bot.handlers.load_answered_questions import on_load_answered_questions
                await on_load_answered_questions(callback, state, session)
                return
            except Exception as e:
                logger.error(f"Error in load_answered_questions handler: {e}", exc_info=True)
                await callback.answer("Error loading your answers. Please try again.", show_alert=True)
                return"""
        
        # Add the proper handler for load_answered_questions
        handler_added = False
        
        # 1. Check if function already has the handler
        if "callback.data == \"load_answered_questions\"" in debug_callback_function:
            # Function has handler but might need fixing
            if "from src.bot.handlers.load_answered_questions import on_load_answered_questions" not in debug_callback_function:
                # Fix import
                load_handler_pattern = r"if callback\.data == \"load_answered_questions\":(.*?)(?=\n\s+#|\n\s+try:|$)"
                handler_match = re.search(load_handler_pattern, debug_callback_function, re.DOTALL)
                
                if handler_match:
                    # Replace the handler section
                    updated_function = debug_callback_function.replace(
                        handler_match.group(0),
                        f"if callback.data == \"load_answered_questions\":{load_handler_code}"
                    )
                    content = content.replace(debug_callback_function, updated_function)
                    logger.info("Fixed existing load_answered_questions handler")
                    handler_added = True
        
        # 2. If no handler found or couldn't fix, add a new one
        if not handler_added:
            # Try to insert handler at the beginning of the function body
            body_start_pattern = r"async def debug_callback.*?\n\s*"
            body_start_match = re.search(body_start_pattern, debug_callback_function)
            
            if body_start_match:
                # Find where to insert the handler - after the function signature and any initial comments/logs
                first_line_pattern = r"async def debug_callback.*?\n\s*(?:'''.*?'''|\"\"\".*?\"\"\"|logger\..*?\n)"
                first_line_match = re.search(first_line_pattern, debug_callback_function, re.DOTALL)
                
                if first_line_match:
                    insertion_point = first_line_match.end()
                else:
                    # If no initial comments/logs, insert after function signature
                    insertion_point = body_start_match.end()
                
                handler_code = f"    # Special handling for load_answered_questions\n    if callback.data == \"load_answered_questions\":{load_handler_code}\n            \n"
                
                updated_function = debug_callback_function[:insertion_point] + handler_code + debug_callback_function[insertion_point:]
                content = content.replace(debug_callback_function, updated_function)
                logger.info("Added new load_answered_questions handler to debug_callback")
                handler_added = True
        
        # Write the updated content
        with open(start_py_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return handler_added
    
    except Exception as e:
        logger.error(f"Error updating debug_callback function: {e}")
        return False

def update_imports():
    """Make sure necessary imports are present"""
    start_py_path = "src/bot/handlers/start.py"
    
    if not os.path.exists(start_py_path):
        logger.error(f"File {start_py_path} does not exist")
        return False
    
    try:
        # Read the file content
        with open(start_py_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check if we have the import
        import_line = "from src.bot.handlers.load_answered_questions import on_load_answered_questions"
        if import_line in content:
            logger.info("Import for on_load_answered_questions already exists")
            return True
        
        # Find the imports section
        import_section_pattern = r"from src\..*?\nimport.*?\n\n"
        import_section_matches = list(re.finditer(import_section_pattern, content, re.DOTALL))
        
        if not import_section_matches:
            logger.error("Could not find imports section")
            return False
        
        # Get the last match to add our import after it
        last_import_match = import_section_matches[-1]
        import_section_end = last_import_match.end()
        
        # Add our import
        updated_content = content[:import_section_end] + import_line + "\n\n" + content[import_section_end:]
        
        # Write the updated content
        with open(start_py_path, 'w', encoding='utf-8') as f:
            f.write(updated_content)
        
        logger.info("Added import for on_load_answered_questions")
        return True
    
    except Exception as e:
        logger.error(f"Error updating imports: {e}")
        return False

def main():
    """Execute the direct fix"""
    logger.info("Starting direct fix for load_answered_questions callback")
    
    # Update imports first
    if not update_imports():
        logger.error("Failed to update imports")
        return False
    
    # Update debug_callback function
    if not update_debug_callback():
        logger.error("Failed to update debug_callback function")
        return False
    
    logger.info("Direct fix completed successfully")
    return True

if __name__ == "__main__":
    success = main()
    if success:
        print("Direct fix applied successfully! Please restart the bot.")
    else:
        print("Failed to apply direct fix. Please check the logs.") 