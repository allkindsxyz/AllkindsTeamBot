#!/usr/bin/env python3
"""
Script to delete all matches in the database.
"""
import asyncio
import os
import sys
from loguru import logger
from sqlalchemy import select, update

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.db.base import async_session_factory
from src.db.models import Match, AnonymousChatSession


async def delete_all_chats_and_matches(session) -> tuple[int, int]:
    """
    Delete all chat sessions and matches from the database.
    
    Args:
        session: Database session
        
    Returns:
        Tuple of (number of chat sessions ended, number of matches deleted)
    """
    # First end all active chat sessions
    ended_chats = 0
    query = select(AnonymousChatSession).where(AnonymousChatSession.status == "active")
    result = await session.execute(query)
    active_chats = result.scalars().all()
    
    for chat in active_chats:
        chat.status = "ended"
        chat.match_id = None  # Disassociate from match
        ended_chats += 1
    
    await session.commit()
    logger.info(f"Marked {ended_chats} chat sessions as ended and removed match references")

    # Now delete all matches
    query = select(Match)
    result = await session.execute(query)
    all_matches = result.scalars().all()
    
    deleted_matches = 0
    for match in all_matches:
        await session.delete(match)
        deleted_matches += 1
    
    await session.commit()
    logger.info(f"Deleted {deleted_matches} matches")
    
    return ended_chats, deleted_matches


async def main():
    """Delete all chat sessions and matches and display the results."""
    logger.info("Starting to delete all chat sessions and matches")
    
    async with async_session_factory() as session:
        ended_chats, deleted_matches = await delete_all_chats_and_matches(session)
        
    logger.info(f"Successfully ended {ended_chats} chat sessions and deleted {deleted_matches} matches")
    print(f"Successfully ended {ended_chats} chat sessions and deleted {deleted_matches} matches")


if __name__ == "__main__":
    asyncio.run(main()) 