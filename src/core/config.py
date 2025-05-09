"""
Application configuration module.
Uses Pydantic's BaseSettings for type-safe configuration with environment variable support.
"""

import os
import sys
from pydantic import Field, BaseModel
# Update import for compatibility with newer Pydantic versions
from pydantic_settings import BaseSettings
from pydantic_core import PydanticCustomError
from pydantic.fields import FieldInfo


class Settings(BaseSettings):
    """
    Application settings.
    
    These are loaded from environment variables and validated by Pydantic.
    Environment variables take precedence over the default values specified here.
    """
    BOT_TOKEN: str = Field(..., alias="BOT_TOKEN")  # No default - must be set
    WEBHOOK_HOST: str = Field("", alias="WEBHOOK_HOST")
    WEBHOOK_PATH: str = Field("/webhook", alias="WEBHOOK_PATH")
    DB_URL: str = Field("sqlite+aiosqlite:///allkinds.db", alias="DATABASE_URL")
    OPENAI_API_KEY: str = Field("", alias="OPENAI_API_KEY")
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        # Allow extra fields in case we add more later without updating the model
        extra = "ignore"


# Cache the settings instance
_settings = None

def get_settings() -> Settings:
    """
    Get the settings instance.
    
    Returns:
        Settings: The settings instance.
    """
    global _settings
    if _settings is None:
        try:
            # Try to create settings with the model
            _settings = Settings()
        except PydanticCustomError as e:
            # Handle missing environment variables
            if "BOT_TOKEN" in str(e):
                print(f"Error: BOT_TOKEN environment variable is not set. {str(e)}")
                print("Please set the BOT_TOKEN environment variable and restart the application.")
                sys.exit(1)
            else:
                # Re-raise other validation errors
                raise
    return _settings 