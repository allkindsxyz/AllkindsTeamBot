#!/usr/bin/env python3
"""
Unified Fix Script for Allkinds Telegram Bot

This script:
1. Stops all running bot instances 
2. Cleans up lock files
3. Fixes the 'load_answered_questions' callback handling
4. Properly restarts the bot
"""

import os
import re
import sys
import shutil
import signal
import logging
import subprocess
from pathlib import Path
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("unified_fix.log")
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

def stop_running_bots():
    """Find and stop all running bot instances"""
    logger.info("Stopping all running bot instances...")
    
    try:
        # Get all Python processes
        result = subprocess.run(
            ["ps", "aux"], 
            capture_output=True, 
            text=True
        )
        output = result.stdout
        
        # Find lines containing bot processes
        bot_processes = []
        for line in output.splitlines():
            if "main_bot_only.py" in line and "grep" not in line:
                parts = line.split()
                if len(parts) > 1:
                    pid = parts[1]
                    bot_processes.append(pid)
        
        logger.info(f"Found {len(bot_processes)} running bot processes: {bot_processes}")
        
        # Kill each process
        for pid in bot_processes:
            try:
                logger.info(f"Killing process {pid}...")
                os.kill(int(pid), signal.SIGKILL)
                logger.info(f"Successfully killed process {pid}")
            except ProcessLookupError:
                logger.warning(f"Process {pid} not found")
            except Exception as e:
                logger.error(f"Error killing process {pid}: {e}")
        
        # Give processes time to stop
        import time
        time.sleep(2)
        
        return True
    except Exception as e:
        logger.error(f"Error stopping running bots: {e}")
        return False

def clean_lock_files():
    """Clean up lock files"""
    logger.info("Cleaning up lock files...")
    
    try:
        # Remove lock files
        lock_files = ["bot.lock", "communicator_bot.lock"]
        removed = 0
        
        for lock_file in lock_files:
            if os.path.exists(lock_file):
                os.remove(lock_file)
                logger.info(f"Removed lock file: {lock_file}")
                removed += 1
        
        logger.info(f"Removed {removed} lock files")
        
        # Remove session files
        session_files = list(Path(".").glob("*.session*"))
        for session_file in session_files:
            session_file.unlink()
            logger.info(f"Removed session file: {session_file}")
        
        return True
    except Exception as e:
        logger.error(f"Error cleaning lock files: {e}")
        return False

def update_debug_callback():
    """Update the debug_callback function in start.py to handle load_answered_questions"""
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

def start_bot():
    """Start the main bot"""
    logger.info("Starting main bot...")
    
    try:
        # Use subprocess to start the bot in background
        subprocess.Popen(
            [sys.executable, "main_bot_only.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True
        )
        logger.info("Bot started successfully")
        return True
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        return False

def main():
    """Execute the unified fix"""
    logger.info("Starting unified fix for Allkinds Telegram Bot")
    
    # Step 1: Stop running bots
    if not stop_running_bots():
        logger.error("Failed to stop running bots")
        return False
    
    # Step 2: Clean lock files
    if not clean_lock_files():
        logger.error("Failed to clean lock files")
        return False
    
    # Step 3: Update imports
    if not update_imports():
        logger.error("Failed to update imports")
        return False
    
    # Step 4: Update debug_callback function
    if not update_debug_callback():
        logger.error("Failed to update debug_callback function")
        return False
    
    # Step 5: Start the bot
    if not start_bot():
        logger.error("Failed to start bot")
        return False
    
    logger.info("Unified fix completed successfully")
    return True

if __name__ == "__main__":
    success = main()
    if success:
        print("Unified fix applied successfully! Bot has been restarted.")
    else:
        print("Failed to apply unified fix. Please check the logs.") 