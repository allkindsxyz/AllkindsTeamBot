"""
Group-related utility functions for the bot
"""

import logging
import base64
from aiogram import types, Bot
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.fsm.context import FSMContext

from src.db.repositories import group_repo
from src.db.models import MemberRole

logger = logging.getLogger(__name__)

async def can_delete_question(user_id: int, question, session: AsyncSession) -> bool:
    """
    Check if a user can delete a question.
    Returns True if the user is either the author of the question or the creator of the group.
    """
    # Check if user is the author
    if question.author_id == user_id:
        return True
        
    # Check if user is the creator of the group
    try:
        is_group_creator = await group_repo.is_group_creator(session, user_id, question.group_id)
        return is_group_creator
    except Exception as e:
        logger.error(f"Error checking if user {user_id} is group creator: {e}")
        return False

async def generate_group_invite_link(bot: Bot, group_id: int) -> str:
    """Generate an invite link for a group."""
    payload = base64.urlsafe_b64encode(f"g{group_id}".encode()).decode().rstrip('=')
    bot_info = await bot.get_me()
    invite_link = f"https://t.me/{bot_info.username}?start={payload}"
    return invite_link

async def get_user_groups(session: AsyncSession, user_id: int):
    """Get all groups that a user belongs to."""
    return await group_repo.get_user_groups(session, user_id)

async def add_user_to_group(session: AsyncSession, user_id: int, group_id: int, role: MemberRole = MemberRole.MEMBER):
    """Add a user to a group with the specified role."""
    return await group_repo.add_user_to_group(session, user_id, group_id, role)

async def create_group(session: AsyncSession, name: str, description: str, created_by: int, is_public: bool = False):
    """Create a new group."""
    return await group_repo.create_group(
        session=session,
        name=name,
        description=description,
        created_by=created_by,
        is_public=is_public
    ) 