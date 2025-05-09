"""
Team creation handlers and functionality for the bot
"""

import logging
import base64
from aiogram import types, Dispatcher, F
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.repositories import user_repo
from src.db.models import MemberRole
from src.bot.states import TeamCreation
from src.bot.utils.group_utils import create_group, add_user_to_group, generate_group_invite_link
from src.bot.handlers.start import show_welcome_menu

logger = logging.getLogger(__name__)

async def on_create_team(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Handle create team button callback."""
    await callback.answer()
    
    text = (
        "Let's create a new Team! 🚀\n\n"
        "Please enter a name for your Team:"
    )
    
    # Set user state to waiting for team name
    await state.set_state(TeamCreation.waiting_for_name)
    
    await callback.message.answer(text)


async def process_team_name(message: types.Message, state: FSMContext) -> None:
    """Process team name input from user."""
    team_name = message.text.strip()
    
    if len(team_name) < 3:
        await message.answer("Team name is too short. Please use at least 3 characters.")
        return
    
    if len(team_name) > 50:
        await message.answer("Team name is too long. Please use at most 50 characters.")
        return
    
    # Store the team name
    await state.update_data(team_name=team_name)
    
    # Ask for team description
    await message.answer(
        "Great! Now please provide a short description for your Team (optional).\n\n"
        "Or type /skip to skip this step."
    )
    
    # Update state
    await state.set_state(TeamCreation.waiting_for_description)


async def process_team_description(message: types.Message, state: FSMContext) -> None:
    """Process team description input from user."""
    # Check for skip command - handle both as command and as text
    if message.text.strip() == "/skip":
        logger.info("User skipped team description")
        description = ""
    else:
        description = message.text.strip()
        logger.info(f"User provided team description: {description[:20]}...")
    
    # Store the description
    await state.update_data(team_description=description)
    
    # Get the stored team name
    data = await state.get_data()
    team_name = data.get("team_name", "Unknown Team")
    
    # Ask for confirmation
    confirmation_text = (
        f"Please confirm your team details:\n\n"
        f"Name: {team_name}\n"
    )
    
    if description:
        confirmation_text += f"Description: {description}\n\n"
    else:
        confirmation_text += "Description: None\n\n"
    
    confirmation_text += "Is this correct?"
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="✅ Confirm", callback_data="confirm_team"),
            types.InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_team"),
        ]
    ])
    
    logger.info(f"Showing confirmation for team: {team_name}")
    await message.answer(confirmation_text, reply_markup=keyboard)
    
    # Update state
    await state.set_state(TeamCreation.confirm_creation)
    current_state_check = await state.get_state() # Add check
    logger.info(f"State set to: {current_state_check} before showing confirmation.") # Add log


async def on_confirm_team(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession = None) -> None:
    """Handle confirm team creation callback."""
    logger.info(f"User {callback.from_user.id} confirmed team creation.")
    await callback.answer("Creating your Team...")

    if not session:
        logger.error("Database session not available in on_confirm_team")
        await callback.message.edit_text("Sorry, there was a database error. Please try again.")
        await state.clear()
        return

    try:
        # Get data from state
        data = await state.get_data()
        team_name = data.get("team_name")
        team_description = data.get("team_description", "")
        user_id = callback.from_user.id

        if not team_name:
            logger.error(f"Team name not found in state for user {user_id}")
            await callback.message.edit_text("Sorry, something went wrong (missing team name). Please start over.")
            await state.clear()
            return

        # Get DB user ID
        db_user = await user_repo.get_by_telegram_id(session, user_id)
        if not db_user:
             logger.error(f"Could not find user {user_id} in database during team creation.")
             await callback.message.edit_text("Sorry, couldn't find your user record. Please try /start again.")
             await state.clear()
             return

        # Create the group
        logger.info(f"Creating group '{team_name}' by user {db_user.id}")
        try:
            new_group = await create_group(
                session=session,
                name=team_name,
                description=team_description,
                created_by=db_user.id,
                is_public=False # Teams are private by default
            )
            logger.info(f"Group created with ID: {new_group.id}")
        except Exception as group_error:
            logger.exception(f"Error creating group for user {user_id}: {str(group_error)}")
            await callback.message.edit_text("Sorry, an error occurred while creating your team. Please try again later.")
            await state.clear()
            return

        try:
            # Add the creator as the first member (Admin)
            await add_user_to_group(
                session=session,
                user_id=db_user.id,
                group_id=new_group.id,
                role=MemberRole.CREATOR
            )
            logger.info(f"Added user {db_user.id} as creator to group {new_group.id}")
        except Exception as member_error:
            logger.exception(f"Error adding creator {user_id} to group {new_group.id}: {str(member_error)}")
            await callback.message.edit_text("Team was created but there was an error adding you as a member. Please try again later.")
            await state.clear()
            return

        try:
            # Generate invite link
            invite_link = await generate_group_invite_link(callback.bot, new_group.id)

            await callback.message.edit_text(
                f"🎉 Team '<b>{team_name}</b>' created successfully!\n\n"
                f"You can invite others using this link:\n{invite_link}",
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        except Exception as invite_error:
            logger.exception(f"Error generating invite link for group {new_group.id}: {str(invite_error)}")
            await callback.message.edit_text(
                f"🎉 Team '<b>{team_name}</b>' created successfully!\n\n"
                f"You can generate an invite link by using the team settings later.",
                parse_mode="HTML"
            )

        # Clear the state now that creation is complete
        await state.clear()

    except Exception as e:
        logger.exception(f"Error during team creation confirmation for user {callback.from_user.id}: {e}")
        try:
            # Use answer for ephemeral errors, edit_text for permanent states
            await callback.answer("Sorry, an error occurred while creating the team.", show_alert=True)
            # Edit the original message to indicate failure with more details
            await callback.message.edit_text(f"Team creation failed. Please try again. Error: {str(e)[:50]}")
        except Exception as msg_error:
            logger.error(f"Failed to send error message: {msg_error}")
        await state.clear()


async def on_cancel_team_creation(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Handle cancel team creation callback."""
    logger.info(f"User {callback.from_user.id} cancelled team creation.")
    await callback.answer("Team creation cancelled.")
    await state.clear()
    # Edit the confirmation message to show cancellation
    try:
        await callback.message.edit_text("Team creation cancelled. What would you like to do next?")
    except Exception as e:
        logger.warning(f"Failed to edit cancellation message: {e}")
        # Fallback to sending a new message if edit fails
        await callback.message.answer("Team creation cancelled.")

    # Show the main welcome menu again
    await show_welcome_menu(callback.message) # Assumes show_welcome_menu is defined/imported


def register_handlers(dp: Dispatcher) -> None:
    """Register team creation handlers."""
    dp.callback_query.register(on_create_team, F.data == "create_team")
    dp.message.register(process_team_name, TeamCreation.waiting_for_name)
    dp.message.register(process_team_description, TeamCreation.waiting_for_description)
    dp.callback_query.register(on_confirm_team, F.data == "confirm_team", TeamCreation.confirm_creation)
    dp.callback_query.register(on_cancel_team_creation, F.data == "cancel_team", TeamCreation.confirm_creation) 