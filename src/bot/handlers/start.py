"""
start.py - Bot message and callback handlers - start

Part of AllkindsTeamBot - A Telegram bot service that connects people based on shared values.

This file contains the main entry point for bot interactions, with the actual functionality 
now split across multiple specialized modules for better maintainability.
"""

import logging
import base64
import os
from aiogram import Dispatcher, F, types, Bot
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.bot.keyboards.inline import get_start_menu_keyboard
from src.bot.utils.user_utils import get_or_create_user
from src.bot.utils.group_utils import get_user_groups
from src.db.repositories import user_repo
from src.bot.states import QuestionFlow

# Forward declaration of the handle_group_invite function
# This will be properly imported when registering handlers
handle_group_invite = None

settings = get_settings()
logger = logging.getLogger(__name__)

async def cmd_start(message: types.Message, command: CommandObject = None, state: FSMContext = None, session: AsyncSession = None) -> None:
    """Handle /start command."""
    logger.info(f"========== START COMMAND TRIGGERED ==========")
    logger.info(f"From user: {message.from_user.id} ({message.from_user.username or 'no username'})")
    logger.info(f"Message text: {message.text}")
    logger.info(f"Command object: {command}")
    logger.info(f"State available: {state is not None}")
    logger.info(f"Session available: {session is not None}")
    logger.info(f"USE_WEBHOOK environment: {os.environ.get('USE_WEBHOOK', 'not set')}")
    logger.info(f"Bot running in: {os.environ.get('RAILWAY_ENVIRONMENT', 'local')} environment")
    
    try:
        # Extract potential command args
        args = None
        if message.text and message.text.startswith("/start "):
            args = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else None
            logger.info(f"Extracted args from message text: {args}")
        # Also check the command object if available
        elif command and command.args:
            args = command.args
            logger.info(f"Args from command object: {args}")
        
        # Handle group invites if args are present
        if args:
            logger.info(f"Processing start command with args: {args}")
            try:
                # Add padding back if needed
                padding_needed = len(args) % 4
                if padding_needed:
                    padded_args = args + '=' * (4 - padding_needed)
                else:
                    padded_args = args
                
                # Try to decode as base64
                try:
                    decoded_payload = base64.urlsafe_b64decode(padded_args).decode('utf-8')
                    logger.info(f"Successfully decoded base64 payload: {decoded_payload}")
                    
                    # Check if it's a group invite (g{id})
                    if decoded_payload.startswith('g') and decoded_payload[1:].isdigit():
                        group_id = int(decoded_payload[1:])
                        logger.info(f"Base64 decoded invite for group {group_id}")
                        
                        # Import the handle_group_invite function here to avoid circular import
                        from src.bot.handlers.team_joining import handle_group_invite
                        await handle_group_invite(message, group_id, state, session)
                        return
                except Exception as e:
                    logger.warning(f"Failed to decode base64 payload: {e}")
                
                # Fall back to older formats (for backward compatibility)
                if args.startswith('join_') and args[5:].isdigit():
                    group_id = int(args[5:])
                    logger.info(f"Direct 'join_X' format invite for group {group_id}")
                    
                    # Import the handle_group_invite function here to avoid circular import
                    from src.bot.handlers.team_joining import handle_group_invite
                    await handle_group_invite(message, group_id, state, session)
                    return
            except Exception as e:
                logger.error(f"Error processing start command args: {e}")
                logger.exception("Full exception details:")
        
        # Regular start command - get or create user
        user_tg = message.from_user
        logger.info(f"User {user_tg.id} started the bot")
        
        # Ensure session is available
        if not session:
            logger.error("Database session not available in cmd_start")
            await message.answer("Sorry, there was a problem connecting to the database. Please try again later.")
            return
            
        try:
            # Get or create user in DB
            user_dict = {
                "id": user_tg.id,
                "first_name": user_tg.first_name,
                "last_name": user_tg.last_name,
                "username": user_tg.username,
                "is_bot": user_tg.is_bot
            }
            
            logger.info(f"Attempting to get or create user in DB with telegram_id={user_tg.id}")
            db_user, created = await get_or_create_user(session, user_dict)
            if created:
                logger.info(f"Created new user in DB: {db_user.id} (TG: {db_user.telegram_id})")
            else:
                logger.info(f"Found existing user in DB: {db_user.id} (TG: {db_user.telegram_id})")
        except Exception as db_error:
            logger.error(f"Database error while getting/creating user: {db_error}")
            await message.answer("Sorry, there was a database error. Please try again later.")
            return

        try:
            # Check if user belongs to any groups
            logger.info(f"Checking if user {db_user.id} belongs to any groups")
            user_groups = await get_user_groups(session, db_user.id)
            logger.info(f"Found {len(user_groups) if user_groups else 0} groups for user {db_user.id}")
        except Exception as group_error:
            logger.error(f"Error retrieving user groups: {group_error}")
            await message.answer("Sorry, there was an error retrieving your groups. Please try again later.")
            return
        
        # If user is already in groups, show the group menu
        if user_groups:
            # User is already in some group
            group = user_groups[0]  # Take the first group
            logger.info(f"User is in group {group.id}, showing group menu")
            
            try:
                await show_group_menu(
                    message=message, 
                    group_id=group.id, 
                    group_name=group.name, 
                    state=state, 
                    session=session
                )
            except Exception as group_menu_error:
                logger.error(f"Error showing group menu: {group_menu_error}")
                logger.exception("Full exception details:")
                await message.answer("Sorry, there was an error displaying the group menu. Please try again later.")
        else:
            # User is not in any group yet
            logger.info(f"User {db_user.id} is not in any group, showing welcome menu")
            try:
                await show_welcome_menu(message)
            except Exception as welcome_menu_error:
                logger.error(f"Error showing welcome menu: {welcome_menu_error}")
                await message.answer("Sorry, there was an error displaying the welcome menu. Please try again.")
                return
    except Exception as e:
        logger.error(f"Unexpected error in cmd_start: {e}")
        logger.exception("Full exception traceback:")
        # Try to respond to user if possible
        try:
            await message.answer("Sorry, an unexpected error occurred. Please try again later.")
        except Exception as reply_error:
            logger.error(f"Failed to send error message to user: {reply_error}")
    
    logger.info("========== END OF START COMMAND ==========")


async def show_welcome_menu(message: types.Message) -> None:
    """Show the welcome menu for the bot."""
    # Improved logging for debugging
    logger.info(f"Showing welcome menu to user {message.from_user.id}")
    
    keyboard = get_start_menu_keyboard()
    
    # Log keyboard structure to confirm it's generated correctly
    logger.info(f"Generated keyboard structure: {keyboard}")
    
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


async def show_group_menu(message: types.Message, group_id: int, group_name: str, state: FSMContext, edit: bool = False, current_section: str = None, session: AsyncSession = None, text: str = None) -> None:
    """Shows the main menu for a user within a group."""
    try:
        logger.info(f"Showing group menu for user {message.from_user.id}, group {group_id} ({group_name}), section {current_section}")
        
        # Ensure we have valid parameters
        if not group_id or not group_name:
            logger.error(f"Invalid parameters for show_group_menu: group_id={group_id}, group_name={group_name}")
            await message.answer("Error: Invalid group information. Please use /start to try again.")
            return
        
        # Update state with group info
        await state.update_data(current_group_id=group_id, current_group_name=group_name)
        logger.info(f"Updated state with group_id={group_id}, group_name={group_name}")
        
        # Set the viewing_question state to enable direct question entry
        current_state = await state.get_state()
        if current_state != QuestionFlow.creating_question and current_state != QuestionFlow.reviewing_question:
            await state.set_state(QuestionFlow.viewing_question)
            logger.info(f"Setting state to QuestionFlow.viewing_question for user {message.from_user.id}")
        
        # Get user points if session is provided
        points = 0
        points_text = ""
        if session:
            try:
                user_tg = message.from_user
                db_user = await user_repo.get_by_telegram_id(session, user_tg.id)
                if db_user:
                    points = db_user.points
                    points_text = f"Your balance: 💎 {points} points"
                    logger.info(f"Retrieved user points: {points}")
                else:
                    logger.warning(f"User {user_tg.id} not found in database when showing group menu")
            except Exception as e:
                logger.exception(f"Error retrieving user points: {e}")
        else:
            logger.warning("No session provided to show_group_menu, skipping points retrieval")
        
        # Create a simple reply keyboard with 3 buttons
        keyboard = types.ReplyKeyboardMarkup(
            keyboard=[
                [types.KeyboardButton(text="Find Match")],
                [types.KeyboardButton(text="Team"), types.KeyboardButton(text="Instructions")]
            ],
            resize_keyboard=True,
            one_time_keyboard=False
        )
        
        # Determine display text
        if text is None:
            # Default message with group name and points if available
            if current_section == "questions":
                display_text = f"📋 Questions in {group_name}"
            elif current_section == "group_info":
                display_text = f"🏠 Team information for {group_name}"
            else:
                display_text = f"Welcome to group '{group_name}'"
                if points_text:
                    display_text += f"\n\n{points_text}"
        else:
            display_text = text
            
        logger.info(f"Using display text: '{display_text}'")
        
        # Send the menu message
        menu_msg = await message.answer(display_text, reply_markup=keyboard, parse_mode="HTML")
        
        # Store message ID for potential later updates
        await state.update_data(group_menu_msg_id=menu_msg.message_id)
        logger.info(f"Group menu sent successfully, message ID: {menu_msg.message_id}")
        
        # Check for answered questions and show load button if needed
        if session:
            try:
                from src.bot.handlers.load_answered_questions import show_load_answered_questions_button
                await show_load_answered_questions_button(message, state, session)
                
                # Check if there are unanswered questions and display one if available
                user_tg = message.from_user
                db_user = await user_repo.get_by_telegram_id(session, user_tg.id)
                if db_user:
                    # Display an unanswered question if available
                    displayed = await check_and_display_next_question(message, db_user, group_id, state, session)
                    if displayed:
                        logger.info(f"Automatically displayed an unanswered question after menu for user {db_user.id}")
                    else:
                        logger.info(f"No unanswered questions available to display for user {db_user.id}")
                else:
                    logger.warning(f"User {user_tg.id} not found when trying to display questions")
            except Exception as e:
                logger.error(f"Error showing load button or questions: {e}", exc_info=True)
        else:
            logger.warning("No session provided to show_group_menu, skipping question display")
        
    except Exception as e:
        logger.error(f"Error showing group menu: {e}")
        logger.exception("Full exception traceback:")
        await message.answer("Sorry, there was an error displaying the group menu. Please try again later.")


def register_handlers(dp: Dispatcher) -> None:
    """Register start command handlers."""
    dp.message.register(cmd_start, Command(commands=["start"]))
    
    # Register text button handlers
    dp.message.register(on_find_match, F.text == "Find Match")
    dp.message.register(on_team_info, F.text == "Team")
    dp.message.register(on_instructions, F.text == "Instructions")
    
    # Import and register handlers from other modules
    from src.bot.handlers.team_creation import register_handlers as register_team_creation
    from src.bot.handlers.team_joining import register_handlers as register_team_joining
    
    # Register handlers from other modules
    register_team_creation(dp)
    register_team_joining(dp)

async def on_find_match(message: types.Message, state: FSMContext, session: AsyncSession = None) -> None:
    """Handle Find Match button press."""
    # Get current group from state
    data = await state.get_data()
    group_id = data.get("current_group_id")
    group_name = data.get("current_group_name")
    
    # If group info is missing from state, try to retrieve it from database
    if not group_id or not group_name:
        try:
            # Get user from database
            db_user = await user_repo.get_by_telegram_id(session, message.from_user.id)
            if not db_user:
                await message.answer("Your user profile couldn't be found. Please restart with /start.")
                return
                
            # Get user's groups
            from src.bot.utils.group_utils import get_user_groups
            user_groups = await get_user_groups(session, db_user.id)
            
            if user_groups:
                group = user_groups[0]  # Take the first group
                group_id = group.id
                group_name = group.name
                
                # Update state with retrieved group info
                await state.update_data(current_group_id=group_id, current_group_name=group_name)
                logger.info(f"Recovered group info from database: {group_id} ({group_name})")
            else:
                await message.answer("Please select or create a group first.")
                return
        except Exception as e:
            logger.error(f"Error retrieving group info: {e}")
            await message.answer("Please select or create a group first.")
            return
    
    # Get user from database
    db_user = await user_repo.get_by_telegram_id(session, message.from_user.id)
    if not db_user:
        await message.answer("Your user profile couldn't be found. Please restart with /start.")
        return
    
    # Check if user has enough points
    points_required = 1
    if hasattr(db_user, 'points') and db_user.points < points_required:
        await message.answer(
            f"You need at least {points_required} points to find a match. "
            f"You currently have {db_user.points} points.\n\n"
            f"Answer more questions to earn points!"
        )
        return
    
    # Display finding matches message
    await message.answer(
        f"🔍 <b>Finding matches in {group_name}...</b>\n\n"
        f"This functionality will be implemented soon.\n\n"
        f"In the meantime, try answering more questions to increase your match potential!",
        parse_mode="HTML"
    )

async def on_team_info(message: types.Message, state: FSMContext, session: AsyncSession = None) -> None:
    """Handle Team button press."""
    logger.info(f"Team button pressed by user {message.from_user.id}")
    
    # Get current group from state
    data = await state.get_data()
    group_id = data.get("current_group_id")
    group_name = data.get("current_group_name")
    
    # If group info is missing from state, try to retrieve it from database
    if not group_id or not group_name:
        try:
            # Get user from database
            db_user = await user_repo.get_by_telegram_id(session, message.from_user.id)
            if not db_user:
                await message.answer("Your user profile couldn't be found. Please restart with /start.")
                return
                
            # Get user's groups
            from src.bot.utils.group_utils import get_user_groups
            user_groups = await get_user_groups(session, db_user.id)
            
            if user_groups:
                group = user_groups[0]  # Take the first group
                group_id = group.id
                group_name = group.name
                
                # Update state with retrieved group info
                await state.update_data(current_group_id=group_id, current_group_name=group_name)
                logger.info(f"Recovered group info from database: {group_id} ({group_name})")
            else:
                await message.answer("Please select or create a group first.")
                return
        except Exception as e:
            logger.error(f"Error retrieving group info: {e}")
            await message.answer("Please select or create a group first.")
            return
    
    # Get additional group info from database
    try:
        from src.db.repositories import group_repo
        group = await group_repo.get(session, group_id)
        
        if not group:
            logger.error(f"Group with ID {group_id} not found in database.")
            await message.answer(f"Group with ID {group_id} not found. Please restart with /start.")
            return
            
        # Get member count
        member_count = await group_repo.get_member_count(session, group_id)
        
        # Get question count
        question_count = await group_repo.get_question_count(session, group_id)
        
        # Check if user is creator
        is_creator = await group_repo.is_group_creator(session, message.from_user.id, group_id)
        
        # Format group info message with consistent styling
        info_text = (
            f"🏠 <b>{group.name}</b>\n\n"
            f"<i>{group.description or 'No description'}</i>\n\n"
            f"👥 Members: {member_count}\n"
            f"❓ Questions: {question_count}\n"
            f"🆔 Group ID: {group.id}\n"
        )
        
        # Add creator-only information if the user is the creator
        if is_creator:
            info_text += f"\n<b>⚙️ You are the creator of this team.</b>\n"
            
            # Add any creator-specific actions here
            
        await message.answer(info_text, parse_mode="HTML")
        logger.info(f"Displayed team info for group {group_id} to user {message.from_user.id}")
        
    except Exception as e:
        logger.error(f"Error retrieving group details: {e}")
        # Provide a simple fallback response
        await message.answer(f"Team Info for '{group_name}'\n\nID: {group_id}")
        logger.info(f"Displayed fallback team info for group {group_id} to user {message.from_user.id}")

async def on_instructions(message: types.Message, state: FSMContext) -> None:
    """Handle Instructions button press."""
    instructions_text = (
        "📝 <b>Instructions</b>\n\n"
        "• <b>Answer questions</b> to earn points\n"
        "• <b>Earn points</b> by creating quality questions\n" 
        "• <b>Use points</b> to find matches with people who share your values\n"
        "• <b>Chat anonymously</b> with your matches\n"
        "• <b>Exchange contacts</b> if you both agree\n\n"
        "💡 <i>Type a question anytime to add it to your group!</i>"
    )
    
    await message.answer(instructions_text, parse_mode="HTML")

async def check_and_display_next_question(message: types.Message, user, group_id: int, state: FSMContext, session: AsyncSession) -> bool:
    """Check if there are unanswered questions and display one."""
    logger.info(f"Checking for unanswered questions for user {user.id} in group {group_id}")
    
    try:
        from src.db.repositories import question_repo, answer_repo
        from src.bot.keyboards.inline import get_answer_keyboard_with_skip
        
        # Ensure a clean state by committing any pending transactions
        try:
            await session.commit()
        except Exception as e:
            logger.error(f"Error committing session in check_and_display_next_question: {e}")
            # Continue anyway - we'll get a fresh transaction
        
        # Get user's answers for this group
        try:
            answers = await answer_repo.get_answers_for_user_in_group(session, user.id, group_id)
            
            # Create a map of question_id -> answer for quick lookup
            answer_map = {answer.question_id: answer for answer in answers}
            logger.info(f"User has {len(answers)} answers in group {group_id}")
        except Exception as e:
            logger.error(f"Error getting user answers in check_and_display_next_question: {e}")
            return False
        
        # Get all questions for the group
        try:
            all_questions = await question_repo.get_group_questions(session, group_id)
            
            # Filter to only show questions the user hasn't answered yet
            unanswered_questions = [
                q for q in all_questions if q.id not in answer_map
            ]
            
            logger.info(f"Found {len(unanswered_questions)} unanswered questions for user {user.id}")
            
            if not unanswered_questions:
                logger.info(f"No unanswered questions for user {user.id}")
                return False
                
            # Get the first unanswered question
            question = unanswered_questions[0]
        except Exception as e:
            logger.error(f"Error getting all questions in check_and_display_next_question: {e}")
            return False
        
        # Create keyboard with answer options
        keyboard = get_answer_keyboard_with_skip(question.id)
        
        # Send the question with the keyboard
        question_message = await message.answer(f"{question.text}", reply_markup=keyboard)
        
        # Store the current question ID in state
        await state.update_data(current_question_id=question.id)
        
        logger.info(f"Displayed question {question.id} to user {user.id}")
        return True
        
    except Exception as e:
        logger.error(f"Unexpected error in check_and_display_next_question for user {user.id}: {e}", exc_info=True)
        return False

async def can_delete_question(user_id: int, question, session: AsyncSession) -> bool:
    """Check if user can delete a question."""
    from src.db.repositories import group_repo
    
    # If user is the question author, they can delete it
    if user_id == question.author_id:
        return True
    
    # If user is the group creator, they can delete any question in their group
    try:
        is_creator = await group_repo.is_group_creator(session, user_id, question.group_id)
        return is_creator
    except Exception as e:
        logger.error(f"Error checking if user {user_id} is group creator: {e}")
        return False 