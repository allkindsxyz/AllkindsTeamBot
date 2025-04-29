#!/usr/bin/env python3
"""
Check if all required dependencies are available.
"""
import sys
import importlib.util
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# List of critical dependencies
CRITICAL_DEPS = [
    "aiogram", 
    "sqlalchemy", 
    "aiohttp", 
    "pydantic",
    "asyncpg"
]

# List of web server dependencies
WEB_DEPS = [
    "fastapi",
    "uvicorn"
]

# List of optional dependencies
OPTIONAL_DEPS = [
    "openai",
    "pinecone",
    "redis"
]

def check_dependency(name):
    """Check if a dependency is installed."""
    spec = importlib.util.find_spec(name)
    if spec is None:
        return False
    
    # Try to import it to verify it works
    try:
        module = importlib.import_module(name)
        version = getattr(module, "__version__", "unknown")
        return version
    except ImportError:
        return False
    except Exception as e:
        logger.warning(f"Error importing {name}: {e}")
        return "error"

def main():
    """Run the dependency checks."""
    logger.info("Checking dependencies...")
    
    print("=" * 50)
    print("DEPENDENCY CHECK")
    print("=" * 50)
    
    # Check Python version
    py_version = sys.version.split()[0]
    print(f"Python version: {py_version}")
    
    # Check critical dependencies
    critical_failures = 0
    print("\nCritical dependencies:")
    for dep in CRITICAL_DEPS:
        version = check_dependency(dep)
        if version:
            print(f"  ✅ {dep}: {version}")
        else:
            print(f"  ❌ {dep}: NOT INSTALLED")
            critical_failures += 1
    
    # Check web server dependencies
    web_failures = 0
    print("\nWeb server dependencies:")
    for dep in WEB_DEPS:
        version = check_dependency(dep)
        if version:
            print(f"  ✅ {dep}: {version}")
        else:
            print(f"  ❌ {dep}: NOT INSTALLED")
            web_failures += 1
    
    # Check optional dependencies
    optional_failures = 0
    print("\nOptional dependencies:")
    for dep in OPTIONAL_DEPS:
        version = check_dependency(dep)
        if version:
            print(f"  ✅ {dep}: {version}")
        else:
            print(f"  ⚠️ {dep}: NOT INSTALLED")
            optional_failures += 1
    
    print("\n" + "=" * 50)
    if critical_failures > 0:
        print(f"❌ {critical_failures} critical dependencies missing!")
        print("The application will not function correctly without these.")
    else:
        print("✅ All critical dependencies installed.")
    
    if web_failures > 0:
        print(f"⚠️ {web_failures} web server dependencies missing!")
        print("Fallback HTTP server will be used instead.")
    else:
        print("✅ All web server dependencies installed.")
    
    if optional_failures > 0:
        print(f"ℹ️ {optional_failures} optional dependencies missing.")
        print("Some features may be limited.")
    else:
        print("✅ All optional dependencies installed.")
    
    print("=" * 50)
    
    return critical_failures

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code) 