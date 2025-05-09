"""
Team joining handlers and functionality for the bot
"""

import logging
import base64
from aiogram import types, Dispatcher, F
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from src.db.repositories import user_repo, group_repo
from src.db.models import MemberRole, Group, GroupMember
from src.bot.states import TeamJoining
from src.bot.keyboards.inline import get_start_menu_keyboard
from src.bot.utils.user_utils import get_or_create_user

logger = logging.getLogger(__name__)

async def on_join_team(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession = None) -> None:
    """Handle join team button callback."""
    logger.info(f"User {callback.from_user.id} clicked Join Team button")
    await callback.answer()
    
    # Get current state data
    data = await state.get_data()
    current_group_id = data.get("current_group_id")
    
    # Log current state for debugging
    logger.info(f"User {callback.from_user.id} current state data: group_id={current_group_id}, all data: {data}")
    
    # Clear current group info to allow joining a new group
    if current_group_id:
        logger.info(f"User {callback.from_user.id} is currently in group {current_group_id}, clearing for join flow")
        await state.update_data(current_group_id=None, current_group_name=None)
    
    text = (
        "To join a Team, you need an invitation link or code.\n\n"
        "Please enter the invitation code or ask the Team creator for an invitation link."
    )
    
    # Set user state to waiting for team code
    await state.set_state(TeamJoining.waiting_for_code)
    current_state = await state.get_state()
    logger.info(f"Set user {callback.from_user.id} state to {current_state}")
    
    try:
        msg = await callback.message.answer(text)
        logger.info(f"Successfully sent join team prompt to user {callback.from_user.id}")
    except Exception as e:
        logger.error(f"Error sending join team prompt: {e}")
        await callback.message.answer("An error occurred. Please try again by clicking /start.")


async def on_cancel_join(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Handle cancel join button callback."""
    await callback.answer("Canceled joining the team")
    
    # Clear state and return to main menu
    await state.clear()
    await show_welcome_menu_fallback(callback.message)


async def show_welcome_menu_fallback(message: types.Message) -> None:
    """Show the welcome menu for the bot."""
    logger.info(f"Showing welcome menu to user {message.from_user.id}")
    
    keyboard = get_start_menu_keyboard()
    
    welcome_text = (
        "👋 Welcome to <b>AllKinds</b>!\n\n"
        "This bot helps you connect with people who share your values.\n\n"
        "What would you like to do?"
    )
    
    try:
        await message.answer(welcome_text, reply_markup=keyboard, parse_mode="HTML")
        logger.info(f"Welcome menu sent successfully to user {message.from_user.id}")
    except Exception as e:
        logger.error(f"Error sending welcome menu: {e}")


async def handle_group_invite(message: types.Message, group_id: int, state: FSMContext = None, session: AsyncSession = None) -> None:
    """Handle a request to join a group."""
    user_id = message.from_user.id
    logger.info(f"User {user_id} is trying to join group {group_id}")
    
    try:
        # Get the group from database
        group_query = select(Group).where(Group.id == group_id)
        result = await session.execute(group_query)
        group = result.scalar_one_or_none()
        
        if not group:
            logger.warning(f"Group {group_id} not found")
            await message.answer(f"Sorry, this group doesn't exist or has been deleted.")
            await show_welcome_menu_fallback(message)
            return
        
        # Check if user is already a member of this group
        is_member_query = select(GroupMember).where(
            (GroupMember.user_id == user_id) & 
            (GroupMember.group_id == group_id)
        )
        result = await session.execute(is_member_query)
        existing_member = result.scalar_one_or_none()
        
        if existing_member:
            logger.info(f"User {user_id} is already a member of group {group_id}")
            await message.answer(f"You're already a member of '{group.name}'!")
            # TODO: Show group menu instead of welcome menu
            await show_welcome_menu_fallback(message)
            return
            
        # Check if the group is full
        members_count_query = select(GroupMember).where(GroupMember.group_id == group_id)
        result = await session.execute(members_count_query)
        members_count = len(result.scalars().all())
        
        if members_count >= 50:  # Example limit
            logger.warning(f"Group {group_id} is full")
            await message.answer(f"Sorry, '{group.name}' is full and can't accept more members.")
            await show_welcome_menu_fallback(message)
            return
            
        # Add user to the group
        user_dict = {
            "id": message.from_user.id,
            "first_name": message.from_user.first_name,
            "last_name": message.from_user.last_name,
            "username": message.from_user.username,
            "is_bot": message.from_user.is_bot
        }
        
        # Ensure user exists in DB
        user, created = await get_or_create_user(session, user_dict)
        
        # Create group membership
        new_member = GroupMember(
            group_id=group_id,
            user_id=user.id,
            role="member"  # Default role for new members
        )
        session.add(new_member)
        await session.commit()
        
        logger.info(f"User {user_id} successfully joined group {group_id}")
        
        # Send welcome message
        await message.answer(
            f"🎉 Welcome to '{group.name}'!\n\n"
            f"{group.description}\n\n"
            f"You've successfully joined this group."
        )
        
    except Exception as e:
        logger.error(f"Error processing group invite: {e}")
        import traceback
        logger.error(traceback.format_exc())
        await message.answer("Sorry, something went wrong while trying to join the group. Please try again later.")
        await show_welcome_menu_fallback(message)


def register_handlers(dp: Dispatcher) -> None:
    """Register team joining handlers."""
    dp.callback_query.register(on_join_team, F.data == "join_team")
    dp.callback_query.register(on_cancel_join, F.data == "cancel_join")
    # Note: handle_group_invite is called directly from other handlers, not registered as a callback 