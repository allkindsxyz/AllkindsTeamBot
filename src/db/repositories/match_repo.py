from datetime import datetime
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.db.models import Match, User


async def create_match(
    session: AsyncSession,
    user1_id: int,
    user2_id: int,
    score: float,
    common_questions: int = 0,
) -> Match:
    """Create a new match between two users."""
    match = Match(
        user1_id=user1_id,
        user2_id=user2_id,
        score=score,
        common_questions=common_questions,
    )
    
    session.add(match)
    await session.commit()
    await session.refresh(match)
    
    return match


async def get_by_id(session: AsyncSession, match_id: int) -> Match:
    """Get a match by its ID."""
    query = select(Match).where(Match.id == match_id)
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def get_with_users(session: AsyncSession, match_id: int) -> Match:
    """Get a match with its related users."""
    query = (
        select(Match)
        .where(Match.id == match_id)
        .options(joinedload(Match.user1), joinedload(Match.user2))
    )
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def get_matches_for_user(session: AsyncSession, user_id: int) -> list[Match]:
    """Get all matches for a user."""
    query = (
        select(Match)
        .where(or_(Match.user1_id == user_id, Match.user2_id == user_id))
        .order_by(Match.created_at.desc())
    )
    result = await session.execute(query)
    return result.scalars().all()


async def get_match_between_users(session: AsyncSession, user1_id: int, user2_id: int) -> Match:
    """Check if there's already a match between two users."""
    query = (
        select(Match)
        .where(
            or_(
                (Match.user1_id == user1_id) & (Match.user2_id == user2_id),
                (Match.user1_id == user2_id) & (Match.user2_id == user1_id)
            )
        )
    )
    result = await session.execute(query)
    return result.scalar_one_or_none() 