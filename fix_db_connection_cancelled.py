#!/usr/bin/env python3
"""
Fix for asyncio.exceptions.CancelledError during database initialization
by implementing proper timeout handling and connection retry logic.
"""

import os
import re
import shutil
from datetime import datetime

DB_BASE_FILE = "src/db/base.py"

def create_backup(file_path):
    """Create a backup of the file before modifying it"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{file_path}.db_fix_{timestamp}"
    try:
        shutil.copy2(file_path, backup_path)
        print(f"Created backup at {backup_path}")
        return True
    except Exception as e:
        print(f"Error creating backup of {file_path}: {e}")
        return False

def fix_db_connection_cancellation():
    """Fix the database connection cancellation error in base.py"""
    
    if not os.path.exists(DB_BASE_FILE):
        print(f"Error: {DB_BASE_FILE} not found!")
        return False
    
    # Create backup
    if not create_backup(DB_BASE_FILE):
        print("Failed to create backup, aborting to be safe.")
        return False
    
    try:
        # Read the file
        with open(DB_BASE_FILE, 'r') as file:
            content = file.read()
        
        # Check if we have already fixed the file
        if "asyncio.exceptions.CancelledError" in content and "connection_timeout" in content:
            print("The file appears to already have the fix for CancelledError")
            return True
        
        # Look for get_async_engine function
        engine_func_pattern = r"(def get_async_engine\([^)]*\):.*?return engine)"
        engine_func_match = re.search(engine_func_pattern, content, re.DOTALL)
        
        if not engine_func_match:
            print("Could not find get_async_engine function!")
            return False
        
        engine_func = engine_func_match.group(1)
        
        # Modify the function to handle CancelledError and add timeout parameters
        modified_engine_func = engine_func.replace(
            "def get_async_engine(url=None, echo=False):",
            "def get_async_engine(url=None, echo=False, connection_timeout=10.0, command_timeout=30.0):"
        )
        
        # Find where engine is created
        engine_creation_pattern = r"(engine = create_async_engine\([^)]*\))"
        engine_creation_match = re.search(engine_creation_pattern, modified_engine_func)
        
        if not engine_creation_match:
            print("Could not find engine creation in get_async_engine function!")
            return False
        
        engine_creation = engine_creation_match.group(1)
        
        # Add timeout parameters to engine creation
        modified_engine_creation = engine_creation.replace(
            "engine = create_async_engine(",
            "engine = create_async_engine("
        )
        
        # Add connect_args parameter if not already present
        if "connect_args" not in modified_engine_creation:
            modified_engine_creation = modified_engine_creation.replace(
                ")",
                ", connect_args={\"timeout\": connection_timeout, \"command_timeout\": command_timeout})"
            )
        
        # Replace the engine creation
        modified_engine_func = modified_engine_func.replace(
            engine_creation,
            modified_engine_creation
        )
        
        # Replace the function in content
        content = content.replace(engine_func, modified_engine_func)
        
        # Look for init_models function to enhance error handling
        init_models_pattern = r"(async def init_models\([^)]*\):.*?# End of init_models)"
        init_models_match = re.search(init_models_pattern, content, re.DOTALL)
        
        if not init_models_match:
            print("Could not find init_models function! Looking for alternative pattern...")
            # Try with a shorter pattern
            init_models_pattern = r"(async def init_models\([^)]*\):.*?except Exception as e:.*?raise e)"
            init_models_match = re.search(init_models_pattern, content, re.DOTALL)
            
            if not init_models_match:
                print("Could not find init_models function with alternative pattern!")
                return False
        
        init_models_func = init_models_match.group(1)
        
        # Check if we need to add handling for CancelledError
        if "asyncio.exceptions.CancelledError" not in init_models_func:
            # Add import for asyncio if not present
            if "import asyncio" not in content and "from asyncio import" not in content:
                content = "import asyncio\n" + content
            
            # Add specific handling for CancelledError
            modified_init_models = init_models_func.replace(
                "except Exception as e:",
                "except asyncio.exceptions.CancelledError as e:\n"
                "        logger.error(f\"Database connection cancelled (attempt {attempt}/{max_attempts}): {e}\")\n"
                "        # Specific handling for CancelledError\n"
                "        if attempt < max_attempts:\n"
                "            logger.info(f\"Waiting longer before retry: {backoff * 2} seconds\")\n"
                "            await asyncio.sleep(backoff * 2)  # Wait longer for connection issues\n"
                "        else:\n"
                "            logger.critical(\"Database connection repeatedly cancelled. Check database server and network.\")\n"
                "            raise\n"
                "    except Exception as e:"
            )
            
            # Replace the init_models function
            content = content.replace(init_models_func, modified_init_models)
        
        # Update backoff strategy for retries in init_models
        if "backoff = attempt * 2" in content:
            content = content.replace(
                "backoff = attempt * 2",
                "backoff = attempt * 3"  # Increase backoff time
            )
        
        # Write the updated content back
        with open(DB_BASE_FILE, 'w') as file:
            file.write(content)
        
        print(f"Successfully updated {DB_BASE_FILE} with fixes for CancelledError")
        return True
        
    except Exception as e:
        print(f"Error updating {DB_BASE_FILE}: {e}")
        return False

if __name__ == "__main__":
    print("Applying fixes for database connection cancellation errors...")
    
    success = fix_db_connection_cancellation()
    
    if success:
        print("✅ Database connection cancellation fixes applied successfully!")
        print("Please commit and deploy these changes to fix the connection issues.")
    else:
        print("❌ Failed to apply fixes. Please check the errors above.") 