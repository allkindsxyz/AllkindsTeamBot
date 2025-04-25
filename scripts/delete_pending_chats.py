#!/usr/bin/env python3
import os
import sys
import asyncio
from pathlib import Path

# Add the parent directory to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import delete, select
from src.db.models import AnonymousChatSession
from src.db.base import async_session_factory

async def delete_pending_chats():
    # Get session
    async with async_session_factory() as session:
        # First, let's count them
        query = select(AnonymousChatSession).where(AnonymousChatSession.status == 'pending')
        result = await session.execute(query)
        pending_chats = result.scalars().all()
        print(f'Found {len(pending_chats)} pending chat sessions')
        
        if pending_chats:
            for chat in pending_chats:
                print(f"  - Session ID: {chat.session_id}, Initiator: {chat.initiator_id}, Recipient: {chat.recipient_id}")
        
        # Delete all pending sessions
        delete_query = delete(AnonymousChatSession).where(AnonymousChatSession.status == 'pending')
        result = await session.execute(delete_query)
        await session.commit()
        print(f'Deleted pending chat sessions')
        
        # Verify none left
        check_query = select(AnonymousChatSession).where(AnonymousChatSession.status == 'pending')
        check_result = await session.execute(check_query)
        remaining = check_result.scalars().all()
        print(f'Remaining pending sessions: {len(remaining)}')

if __name__ == "__main__":
    asyncio.run(delete_pending_chats()) 