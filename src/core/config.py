from functools import lru_cache
from typing import List

from loguru import logger
from pydantic_settings import BaseSettings
from pydantic import field_validator, Field


class Settings(BaseSettings):
    """Application settings."""
    # General settings
    debug: bool = False
    app_name: str = "Allkinds"
    
    # Bot specific settings (now centralized)
    BOT_TOKEN: str
    # ADMIN_IDS should hold the final list of ints
    ADMIN_IDS: List[int] # Changed type hint to List[int]

    @field_validator('ADMIN_IDS', mode='before')
    @classmethod
    def _parse_admin_ids(cls, v: str | int | List[int]) -> List[int]: # Accept int as well
        """Parse ADMIN_IDS string or int from .env into a list of integers."""
        if isinstance(v, list):
             return v
        if isinstance(v, int):
            # Handle case where only one ID is provided as an int
            logger.info(f"Received single admin ID as int: {v}")
            return [v]
        if not isinstance(v, str):
             logger.warning(f"Unexpected type for ADMIN_IDS validation: {type(v)}")
             return []
        try:
            # Expecting comma-separated string like "123,456"
            return [int(id_str.strip()) for id_str in v.split(',') if id_str.strip().isdigit()]
        except Exception as e:
            logger.error(f"Failed to parse ADMIN_IDS string '{v}': {e}")
            return []

    # Property to easily access the parsed list (REMOVED as ADMIN_IDS is the list now)
    # @property
    # def admin_ids_list(self) -> List[int]:
    #     if isinstance(self.ADMIN_IDS, list):
    #          return self.ADMIN_IDS
    #     return []

    # Database settings
    db_url: str = Field(default="sqlite+aiosqlite:///./allkinds.db", alias='DB_URL') # Use alias
    
    # OpenAI settings
    openai_api_key: str = Field(default="", alias='OPENAI_API_KEY')
    
    # Pinecone settings
    pinecone_api_key: str = Field(default="", alias='PINECONE_API_KEY')
    pinecone_environment: str = Field(default="", alias='PINECONE_ENVIRONMENT')
    pinecone_index_name: str = Field(default="allkinds", alias='PINECONE_INDEX_NAME')
    
    class Config:
        env_file = ".env"
        extra = "ignore" # Ignore any extra fields not defined above
        # No prefix needed now, we use aliases or exact matches


@lru_cache
def get_settings() -> Settings:
    """Get application settings singleton."""
    # Clear cache if needed for testing: get_settings.cache_clear()
    return Settings() 