#!/usr/bin/env python3
"""
Script to delete all chat sessions and matches in the database.
"""
import asyncio
import os
import sys
from datetime import datetime
from loguru import logger
from sqlalchemy import select, text, delete

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.db.base import async_session_factory
from src.db.models import AnonymousChatSession, ChatMessage, Match


async def clean_database(session) -> tuple[int, int, int]:
    """
    Delete all chat messages, chat sessions, and matches from the database.
    
    Args:
        session: Database session
        
    Returns:
        Tuple of (number of messages deleted, number of chat sessions deleted, number of matches deleted)
    """
    # First delete all chat messages
    chat_message_count = 0
    try:
        # Raw SQL to delete all messages
        result = await session.execute(delete(ChatMessage))
        chat_message_count = result.rowcount
        await session.commit()
        logger.info(f"Deleted {chat_message_count} chat messages")
    except Exception as e:
        await session.rollback()
        logger.error(f"Error deleting chat messages: {e}")
    
    # Then delete all chat sessions
    chat_session_count = 0
    try:
        # Raw SQL to delete all chat sessions
        result = await session.execute(delete(AnonymousChatSession))
        chat_session_count = result.rowcount
        await session.commit()
        logger.info(f"Deleted {chat_session_count} anonymous chat sessions")
    except Exception as e:
        await session.rollback()
        logger.error(f"Error deleting chat sessions: {e}")
    
    # Finally delete all matches
    match_count = 0
    try:
        # Raw SQL to delete all matches
        result = await session.execute(delete(Match))
        match_count = result.rowcount
        await session.commit()
        logger.info(f"Deleted {match_count} matches")
    except Exception as e:
        await session.rollback()
        logger.error(f"Error deleting matches: {e}")
    
    return chat_message_count, chat_session_count, match_count


async def main():
    """Delete all chat messages, sessions, and matches and display the results."""
    logger.info("Starting database cleanup")
    
    async with async_session_factory() as session:
        messages, sessions, matches = await clean_database(session)
        
    logger.info(f"Successfully deleted {messages} messages, {sessions} chat sessions, and {matches} matches")
    print(f"Successfully deleted {messages} messages, {sessions} chat sessions, and {matches} matches")


if __name__ == "__main__":
    asyncio.run(main()) 