"""
User-related utility functions for the bot
"""

import logging
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Answer, Question, User
from src.db.repositories import user_repo

logger = logging.getLogger(__name__)

async def get_answer_count(session: AsyncSession, user_id: int, group_id: int) -> int:
    """Count the number of answers for a user in a group."""
    # Get all answers from this user for questions in this group
    query = (
        select(func.count())
        .select_from(Answer)
        .join(Question, Question.id == Answer.question_id)
        .where(
            Answer.user_id == user_id,
            Question.group_id == group_id
        )
    )
    
    result = await session.execute(query)
    count = result.scalar_one_or_none() or 0
    
    logger.info(f"User {user_id} has {count} answers in group {group_id}")
    return count

async def get_unanswered_question_count(session: AsyncSession, user_id: int, group_id: int) -> int:
    """Count the number of unanswered questions for a user in a group."""
    # Get all answers from this user for questions in this group
    answered_subquery = (
        select(Answer.question_id)
        .join(Question, Question.id == Answer.question_id)
        .where(
            Answer.user_id == user_id,
            Question.group_id == group_id
        )
        .subquery()
    )
    
    # Count questions that are active, in the specified group,
    # and not in the list of questions the user has already answered
    query = (
        select(func.count())
        .select_from(Question)
        .where(
            Question.group_id == group_id,
            Question.is_active == True,
            ~Question.id.in_(select(answered_subquery.c.question_id))
        )
    )
    
    result = await session.execute(query)
    count = result.scalar_one_or_none() or 0
    
    logger.info(f"User {user_id} has {count} unanswered questions in group {group_id}")
    return count

# For backward compatibility
async def count_unanswered_questions(session: AsyncSession, user_id: int, group_id: int) -> int:
    """Alias for get_unanswered_question_count for backward compatibility."""
    return await get_unanswered_question_count(session, user_id, group_id)

async def get_user_from_telegram_id(session: AsyncSession, telegram_id: int) -> User:
    """Get a user from the database by Telegram ID."""
    return await user_repo.get_by_telegram_id(session, telegram_id)

async def get_or_create_user(session: AsyncSession, user_dict: dict) -> tuple[User, bool]:
    """Get or create a user in the database."""
    user, created = await user_repo.get_or_create_user(session, user_dict)
    return user, created 