#!/usr/bin/env python3
import asyncio
from src.core.database import get_db_session
from sqlalchemy.future import select
from sqlalchemy import update
import sys

# Try to import the chat model class
try:
    from src.models.chat import ChatSession
    MODEL_NAME = "ChatSession"
except ImportError:
    try:
        from src.models.match import Match
        MODEL_NAME = "Match"
    except ImportError:
        print("Could not find chat or match model. Please check the model name.")
        sys.exit(1)

async def clear_pending():
    """Clear all pending chat sessions in the database"""
    print(f"Clearing pending {MODEL_NAME} records...")
    
    async with get_db_session() as session:
        if MODEL_NAME == "ChatSession":
            # For ChatSession model
            stmt = select(ChatSession).where(ChatSession.status == 'pending')
            result = await session.execute(stmt)
            
            count = 0
            for chat in result.scalars():
                print(f'Clearing pending chat: {chat.id}')
                chat.status = 'ended'
                count += 1
            
            await session.commit()
            print(f'Done! Cleared {count} pending chat sessions.')
        else:
            # For Match model
            stmt = select(Match).where(Match.status == 'pending')
            result = await session.execute(stmt)
            
            count = 0
            for match in result.scalars():
                print(f'Clearing pending match: {match.id}')
                match.status = 'ended'
                count += 1
            
            await session.commit()
            print(f'Done! Cleared {count} pending matches.')

if __name__ == "__main__":
    asyncio.run(clear_pending()) 