"""
Secure credential handling utility.
This module provides safe methods for accessing credentials and sensitive configuration.
"""

import os
import sys
from typing import Optional, Dict, Any
from loguru import logger

def get_required_env(key: str) -> str:
    """
    Get a required environment variable or exit if not found.
    
    Args:
        key: The environment variable name
        
    Returns:
        The environment variable value
        
    Raises:
        SystemExit: If the environment variable is not set
    """
    value = os.environ.get(key)
    if not value:
        logger.error(f"Required environment variable {key} is not set")
        sys.exit(1)
    return value

def get_optional_env(key: str, default: Optional[str] = None) -> Optional[str]:
    """
    Get an optional environment variable with a default fallback.
    
    Args:
        key: The environment variable name
        default: The default value if not found
        
    Returns:
        The environment variable value or default
    """
    return os.environ.get(key, default)

def get_database_url() -> str:
    """
    Get the database URL from environment variables.
    
    Returns:
        The database connection URL
        
    Raises:
        SystemExit: If DATABASE_URL is not set
    """
    return get_required_env("DATABASE_URL")

def get_api_credentials(service: str) -> Dict[str, str]:
    """
    Get API credentials for a specific service.
    
    Args:
        service: Service name (e.g., "openai", "telegram")
        
    Returns:
        Dictionary with API credentials
        
    Raises:
        SystemExit: If required credentials are missing
    """
    credentials = {}
    
    if service.lower() == "openai":
        credentials["api_key"] = get_required_env("OPENAI_API_KEY")
        credentials["organization"] = get_optional_env("OPENAI_ORGANIZATION")
    
    elif service.lower() == "telegram":
        credentials["bot_token"] = get_required_env("BOT_TOKEN")
    
    elif service.lower() == "pinecone":
        credentials["api_key"] = get_required_env("PINECONE_API_KEY")
        credentials["environment"] = get_required_env("PINECONE_ENVIRONMENT")
    
    return credentials

def mask_sensitive_data(data: str) -> str:
    """
    Mask sensitive data for safe logging.
    
    Args:
        data: String potentially containing sensitive data
        
    Returns:
        String with sensitive data masked
    """
    # Add masking patterns for sensitive data
    sensitive_patterns = [
        ("api_key", r'"api_key"\s*:\s*"[^"]*"', '"api_key":"***"'),
        ("key", r'"key"\s*:\s*"[^"]*"', '"key":"***"'),
        ("token", r'"token"\s*:\s*"[^"]*"', '"token":"***"'),
        ("password", r'"password"\s*:\s*"[^"]*"', '"password":"***"'),
        ("secret", r'"secret"\s*:\s*"[^"]*"', '"secret":"***"'),
    ]
    
    result = data
    for _, pattern, replacement in sensitive_patterns:
        import re
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    
    return result 