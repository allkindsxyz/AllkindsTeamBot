from loguru import logger
import asyncio
import sqlalchemy.ext.asyncio
from src.communicator_bot.repositories import get_active_chats_for_user
from src.db.models import AnonymousChatSession, Chat
from sqlalchemy import select, or_, and_

logger.add('logs/debug_chats.log')

async def main():
    logger.info("Starting debug script")
    
    try:
        # Create engine and session
        engine = sqlalchemy.ext.asyncio.create_async_engine('sqlite+aiosqlite:///allkinds.db')
        async with engine.begin() as conn:
            session_maker = sqlalchemy.ext.asyncio.async_sessionmaker(bind=engine)
            async with session_maker() as session:
                # Check for any anonymous chat sessions regardless of status
                logger.info("Querying for all AnonymousChatSession records...")
                anon_query = select(AnonymousChatSession)
                anon_result = await session.execute(anon_query)
                anon_chats = anon_result.scalars().all()
                logger.info(f"Direct query found {len(anon_chats)} total AnonymousChatSession records")
                
                for i, chat in enumerate(anon_chats):
                    logger.info(f"Anonymous chat {i+1}: id={chat.id}, initiator={chat.initiator_id}, recipient={chat.recipient_id}, status={chat.status}")
                
                # Check for regular Chat records
                logger.info("Querying for all Chat records...")
                chat_query = select(Chat)
                chat_result = await session.execute(chat_query)
                regular_chats = chat_result.scalars().all()
                logger.info(f"Direct query found {len(regular_chats)} total Chat records")
                
                for i, chat in enumerate(regular_chats):
                    logger.info(f"Regular chat {i+1}: id={chat.id}, initiator={chat.initiator_id}, recipient={chat.recipient_id}, status={chat.status}")
                
                # Test our repository function for user 1
                logger.info("Testing get_active_chats_for_user for user ID 1")
                chats = await get_active_chats_for_user(session, 1)
                logger.info(f"Found {len(chats)} chats for user 1")
                
                for chat in chats:
                    logger.info(f"Chat: id={chat.id}, initiator={chat.initiator_id}, recipient={chat.recipient_id}")
    
    except Exception as e:
        logger.exception(f"Error in test script: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 