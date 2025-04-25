#!/usr/bin/env python3
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select
from src.core.config import get_settings
from src.db.models import AnonymousChatSession

async def delete_pending_invites():
    settings = get_settings()
    engine = create_async_engine(settings.db_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Find all pending chat sessions
        query = select(AnonymousChatSession).where(AnonymousChatSession.status == 'pending')
        result = await session.execute(query)
        pending_sessions = result.scalars().all()
        
        # Delete or update them
        count = 0
        for session_obj in pending_sessions:
            await session.delete(session_obj)
            count += 1
        
        # Commit changes
        await session.commit()
        print(f'Successfully deleted {count} pending chat invites')

if __name__ == "__main__":
    asyncio.run(delete_pending_invites()) 