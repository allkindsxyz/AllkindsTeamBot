#!/usr/bin/env python3
"""
Script to delete all active chat sessions in the communicator bot.
"""
import asyncio
import os
import sys
from datetime import datetime
from loguru import logger
from sqlalchemy import select, update

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.db.base import async_session_factory
from src.db.models import AnonymousChatSession


async def end_all_chats(session) -> int:
    """
    Mark all active chat sessions as ended.
    
    Args:
        session: Database session
        
    Returns:
        Number of chats ended
    """
    # Find all active chats
    query = select(AnonymousChatSession).where(AnonymousChatSession.status == "active")
    result = await session.execute(query)
    active_chats = result.scalars().all()
    
    count = 0
    for chat in active_chats:
        # Update the chat status to ended
        chat.status = "ended"
        chat.ended_at = datetime.utcnow()
        count += 1
    
    await session.commit()
    logger.info(f"Marked {count} chat sessions as ended")
    return count


async def main():
    """End all active chats and display the results."""
    logger.info("Starting to end all active chats")
    
    async with async_session_factory() as session:
        ended_count = await end_all_chats(session)
        
    logger.info(f"Successfully ended {ended_count} chat sessions")
    print(f"Successfully ended {ended_count} chat sessions")


if __name__ == "__main__":
    asyncio.run(main()) 