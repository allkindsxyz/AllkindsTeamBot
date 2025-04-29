#!/usr/bin/env python3
"""
Verify code integrity before deployment.

This script checks for common issues and potential problems in the codebase
to reduce the likelihood of deploying broken code.
"""

import os
import re
import sys
import importlib
import importlib.util
from pathlib import Path
from typing import List, Dict, Any, Tuple, Set

# Configuration
CRITICAL_MODULES = [
    "src.bot.handlers.start",
    "src.bot.utils.matching",
    "src.db.repositories.match_repo",
    "src.db.base",
    "src.communicator_bot.handlers.chat"
]

REQUIRED_FUNCTIONS = {
    "src.bot.handlers.start": [
        "register_handlers",
        "handle_find_match_message",
        "on_start_anon_chat"
    ],
    "src.db.repositories.match_repo": [
        "find_matches",
        "get_match",
        "create_match"
    ]
}

# Patterns to check
PROBLEMATIC_PATTERNS = [
    (r"session\.commit\(\).*?db_user\.points\s*-=", 
     "Points deduction before session commit (potential data loss if commit fails)"),
    (r"except\s*:", 
     "Bare except clause (catches all exceptions including KeyboardInterrupt)"),
    (r"except\s+Exception\s+as\s+e\s*:\s*?(?!logger)(?!.*log)", 
     "Exception caught but not logged"),
    (r"await\s+message\.answer.*?await\s+session\.commit", 
     "User notification before database commit (might notify user of success before it's confirmed)"),
]

CRITICAL_CONFIG_VARS = [
    "TELEGRAM_BOT_TOKEN",
    "COMMUNICATOR_BOT_TOKEN",
    "DATABASE_URL",
    "WEBHOOK_DOMAIN"
]

results = {
    "errors": [],
    "warnings": [],
    "passed": []
}

def log_error(message: str) -> None:
    """Log an error message."""
    results["errors"].append(message)
    print(f"❌ ERROR: {message}")

def log_warning(message: str) -> None:
    """Log a warning message."""
    results["warnings"].append(message)
    print(f"⚠️ WARNING: {message}")

def log_success(message: str) -> None:
    """Log a success message."""
    results["passed"].append(message)
    print(f"✅ {message}")

def check_critical_modules_importable() -> None:
    """Check if all critical modules can be imported without errors."""
    print("\n🔍 Checking critical modules can be imported...")
    
    for module_name in CRITICAL_MODULES:
        try:
            module = importlib.import_module(module_name)
            log_success(f"Module {module_name} imported successfully")
        except Exception as e:
            log_error(f"Failed to import {module_name}: {str(e)}")

def check_required_functions() -> None:
    """Check if required functions exist in specified modules."""
    print("\n🔍 Checking required functions...")
    
    for module_name, functions in REQUIRED_FUNCTIONS.items():
        try:
            module = importlib.import_module(module_name)
            
            for func_name in functions:
                if hasattr(module, func_name):
                    log_success(f"Function {func_name} found in {module_name}")
                else:
                    log_error(f"Required function {func_name} not found in {module_name}")
        
        except Exception as e:
            log_error(f"Error checking functions in {module_name}: {str(e)}")

def check_syntax_errors() -> None:
    """Check Python files for syntax errors."""
    print("\n🔍 Checking for syntax errors...")
    
    for root, _, files in os.walk("src"):
        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    compile(content, file_path, 'exec')
                    # If we get here, there's no syntax error
                except Exception as e:
                    log_error(f"Syntax error in {file_path}: {str(e)}")

def check_problematic_patterns() -> None:
    """Check for problematic code patterns."""
    print("\n🔍 Checking for problematic code patterns...")
    
    for root, _, files in os.walk("src"):
        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    for pattern, description in PROBLEMATIC_PATTERNS:
                        matches = re.finditer(pattern, content, re.MULTILINE | re.DOTALL)
                        
                        for match in matches:
                            line_number = content[:match.start()].count('\n') + 1
                            log_warning(f"{description} in {file_path}:{line_number}")
                
                except Exception as e:
                    log_error(f"Error checking patterns in {file_path}: {str(e)}")

def check_environment_variables() -> None:
    """Check for critical environment variables."""
    print("\n🔍 Checking environment variables...")
    
    # Check for .env file
    env_file = Path(".env")
    if not env_file.exists():
        log_warning("No .env file found")
        return
    
    # Read .env file
    env_vars = {}
    try:
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()
    except Exception as e:
        log_error(f"Error reading .env file: {str(e)}")
        return
    
    # Check for critical variables
    for var in CRITICAL_CONFIG_VARS:
        if var not in env_vars:
            log_warning(f"Critical environment variable {var} not found in .env file")
        elif not env_vars[var]:
            log_warning(f"Critical environment variable {var} is empty")
        else:
            log_success(f"Environment variable {var} is properly configured")

def check_database_access() -> None:
    """Check database access."""
    print("\n🔍 Checking database access...")
    
    try:
        # Try to import required modules
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.sql import text
        import asyncio
        
        # Get database URL from environment
        import os
        from dotenv import load_dotenv
        
        load_dotenv()
        db_url = os.getenv("DATABASE_URL", "").replace("postgres://", "postgresql://")
        
        if not db_url:
            log_warning("DATABASE_URL environment variable not set")
            return
        
        # Define an async function to test the connection
        async def test_db_connection():
            try:
                engine = create_async_engine(db_url, echo=False)
                async with engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
                    log_success("Successfully connected to the database")
            except Exception as e:
                log_error(f"Failed to connect to the database: {str(e)}")
        
        # Run the async function
        asyncio.run(test_db_connection())
    
    except ImportError:
        log_warning("SQLAlchemy not installed, skipping database check")
    except Exception as e:
        log_error(f"Error during database check: {str(e)}")

def check_webhook_configuration() -> None:
    """Check webhook configuration."""
    print("\n🔍 Checking webhook configuration...")
    
    try:
        # Try to import required modules
        import os
        from dotenv import load_dotenv
        import aiohttp
        import asyncio
        
        load_dotenv()
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        webhook_domain = os.getenv("WEBHOOK_DOMAIN", "")
        
        if not bot_token:
            log_warning("TELEGRAM_BOT_TOKEN environment variable not set")
            return
        
        if not webhook_domain:
            log_warning("WEBHOOK_DOMAIN environment variable not set")
            return
        
        # Define an async function to check webhook
        async def check_webhook():
            try:
                async with aiohttp.ClientSession() as session:
                    url = f"https://api.telegram.org/bot{bot_token}/getWebhookInfo"
                    async with session.get(url) as response:
                        if response.status != 200:
                            log_error(f"Failed to get webhook info: HTTP {response.status}")
                            return
                        
                        data = await response.json()
                        if not data.get("ok"):
                            log_error(f"Telegram API error: {data.get('description')}")
                            return
                        
                        webhook_url = data.get("result", {}).get("url", "")
                        if not webhook_url:
                            log_warning("No webhook URL configured")
                        elif webhook_domain not in webhook_url:
                            log_warning(f"Webhook domain mismatch: {webhook_url} vs {webhook_domain}")
                        else:
                            log_success(f"Webhook correctly configured: {webhook_url}")
            except Exception as e:
                log_error(f"Error checking webhook: {str(e)}")
        
        # Run the async function
        asyncio.run(check_webhook())
    
    except ImportError:
        log_warning("aiohttp not installed, skipping webhook check")
    except Exception as e:
        log_error(f"Error during webhook check: {str(e)}")

def main() -> None:
    """Run all integrity checks."""
    print("🔍 Starting code integrity verification...")
    
    checks = [
        check_critical_modules_importable,
        check_required_functions,
        check_syntax_errors,
        check_problematic_patterns,
        check_environment_variables,
        check_database_access,
        check_webhook_configuration
    ]
    
    for check in checks:
        check()
    
    # Print summary
    print("\n" + "="*50)
    print("INTEGRITY CHECK SUMMARY")
    print("="*50)
    print(f"🚨 Errors: {len(results['errors'])}")
    print(f"⚠️ Warnings: {len(results['warnings'])}")
    print(f"✅ Passed: {len(results['passed'])}")
    
    if results["errors"]:
        print("\nCRITICAL ERRORS FOUND! Please fix before deploying.")
        sys.exit(1)
    elif results["warnings"]:
        print("\nWarnings found. Review before deploying.")
        sys.exit(0)
    else:
        print("\nAll checks passed! Ready for deployment.")
        sys.exit(0)

if __name__ == "__main__":
    main() 