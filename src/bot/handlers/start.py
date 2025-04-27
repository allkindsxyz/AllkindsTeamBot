from aiogram import Dispatcher, F, types, Bot
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.utils.deep_linking import decode_payload, create_start_link
from loguru import logger
import base64
import asyncio
import time
from datetime import datetime
import re
import logging
import os

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete, update, and_

# from src.bot.config import bot_settings # No longer needed
from src.core.config import get_settings # Import main settings
from src.bot.keyboards.inline import (
    get_start_menu_keyboard, 
    get_group_menu_keyboard, 
    get_answer_keyboard_with_skip,
    get_group_menu_reply_keyboard,
    get_match_confirmation_keyboard # Import keyboard function (will create next)
)
from src.bot.states import TeamCreation, TeamJoining, QuestionFlow, MatchingStates, GroupOnboarding, GroupFlow
from src.core.openai_service import is_yes_no_question, check_duplicate_question, check_spelling
from src.db import get_session
from src.db.repositories import (
    user_repo, question_repo, answer_repo, group_repo,
    create_match, get_match_between_users, 
    create_chat_session, get_by_session_id, get_by_match_id, update_status
)
from src.db.models import Answer, User, AnswerType, MemberRole, Question, Match, GroupMember, Chat
from src.bot.utils.matching import find_best_match
from src.db.repositories.match_repo import get_match_between_users, create_match, find_matches, get_match
from src.db.repositories.chat_session_repo import create_chat_session, get_by_match_id, update_status
from src.db.repositories.chat_repo import get_chat_by_participants
from src.core.diagnostics import get_diagnostics_report, IS_RAILWAY

settings = get_settings() # Get settings from config

# Constants
FIND_MATCH_COST = 10  # Cost in points to find a match
MIN_QUESTIONS_FOR_MATCH = 3  # Minimum number of answered questions needed to find a match

# Define the mapping for answer values
ANSWER_VALUES = {
    "strong_no": -2,
    "no": -1,
    "skip": 0, # Special case for skip
    "yes": 1,
    "strong_yes": 2,
}

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


async def cmd_start(message: types.Message, command: CommandObject = None, state: FSMContext = None, session: AsyncSession = None) -> None:
    """Handle /start command."""
    import base64
    
    # EXTENSIVE DEBUG LOGGING
    logger.info(f"========== START COMMAND TRIGGERED ==========")
    logger.info(f"From user: {message.from_user.id} ({message.from_user.username or 'no username'})")
    logger.info(f"Message text: {message.text}")
    logger.info(f"Command object: {command}")
    logger.info(f"State available: {state is not None}")
    logger.info(f"Session available: {session is not None}")
    logger.info(f"USE_WEBHOOK environment: {os.environ.get('USE_WEBHOOK', 'not set')}")
    logger.info(f"Bot running in: {os.environ.get('RAILWAY_ENVIRONMENT', 'local')} environment")
    
    try:
        # Basic logging
        logger.info(f"Start command triggered from user {message.from_user.id}")
        
        # Extract potential command args from the message text directly
        args = None
        if message.text and message.text.startswith("/start "):
            args = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else None
            logger.info(f"DEBUG: Extracted args from message text: {args}")
        # Also check the command object if available
        elif command and command.args:
            args = command.args
            logger.info(f"DEBUG: Args from command object: {args}")
        
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
                        await handle_group_invite(message, group_id, state, session)
                        return
                except Exception as e:
                    logger.warning(f"Failed to decode base64 payload: {e}")
                
                # Fall back to older formats (for backward compatibility)
                if args.startswith('join_') and args[5:].isdigit():
                    group_id = int(args[5:])
                    logger.info(f"Direct 'join_X' format invite for group {group_id}")
                    await handle_group_invite(message, group_id, state, session)
                    return
            except Exception as e:
                logger.error(f"Error processing start command args: {e}")
                logger.exception("Full exception details:")
        
        user_tg = message.from_user
        logger.info(f"User {user_tg.id} started the bot")
        
        # Ensure session is available (dependency injection handles this)
        if not session:
            logger.error("Database session not available in cmd_start")
            await message.answer("Sorry, there was a problem connecting to the database. Please try again later.")
            return
            
        try:
            # Get or create user in DB - Convert Telegram user to dict manually
            user_dict = {
                "id": user_tg.id,
                "first_name": user_tg.first_name,
                "last_name": user_tg.last_name,
                "username": user_tg.username,
                "is_bot": user_tg.is_bot
            }
            
            logger.info(f"Attempting to get or create user in DB with telegram_id={user_tg.id}")
            db_user, created = await user_repo.get_or_create_user(session, user_dict)
            if created:
                logger.info(f"Created new user in DB: {db_user.id} (TG: {db_user.telegram_id})")
            else:
                logger.info(f"Found existing user in DB: {db_user.id} (TG: {db_user.telegram_id})")
        except Exception as db_error:
            logger.error(f"Database error while getting/creating user: {db_error}")
            logger.exception("Database operation traceback:")
            await message.answer("Sorry, there was a database error. Please try again later.")
            return

        try:
            # Check if user belongs to any groups
            logger.info(f"Checking if user {db_user.id} belongs to any groups")
            user_groups = await group_repo.get_user_groups(session, db_user.id)
            logger.info(f"Found {len(user_groups) if user_groups else 0} groups for user {db_user.id}")
        except Exception as group_error:
            logger.error(f"Error retrieving user groups: {group_error}")
            logger.exception("Group retrieval traceback:")
            await message.answer("Sorry, there was an error retrieving your groups. Please try again later.")
            return
        
        # Create state if it doesn't exist
        if not state:
            logger.info("State not provided, creating a new one")
            try:
                # Replace the attempt to create state manually (which doesn't work in this context)
                # Instead, we'll just log a warning and continue without state
                logger.warning("Cannot create state context dynamically in cmd_start, continuing without state")
                
                # REMOVE THIS PROBLEMATIC CODE:
                # state = Dispatcher.get_current().fsm_storage.get_context(bot=message.bot, chat_id=message.chat.id, user_id=message.from_user.id)
                # logger.info("Successfully created state context")
            except Exception as state_error:
                logger.error(f"Failed to create state context: {state_error}")
                logger.exception("State creation traceback:")
                # Continue without state
        
        # If user is already in groups, show the group menu
        if user_groups:
            # User is already in some group
            # For now, consider that a user has just one group
            group = user_groups[0]  # Take the first group
            logger.info(f"User is in group {group.id}, showing group menu")
            
            try:
                # Verify the group still exists
                if not await group_repo.get(session, group.id):
                    logger.warning(f"Group {group.id} no longer exists for user {user_tg.id}")
                    await message.answer("This group was deleted.")
                    await show_welcome_menu(message)
                    return
            
                # Show the group menu
                await show_group_menu(
                    message=message,
                    group_id=group.id,
                    group_name=group.name,
                    state=state,
                    session=session
                )
            except Exception as group_menu_error:
                logger.error(f"Error showing group menu: {group_menu_error}")
                logger.exception("Group menu traceback:")
                await message.answer("Sorry, there was an error displaying your group menu. Please try again.")
                return
        else:
            # User is not in any group yet
            logger.info(f"User {db_user.id} is not in any group, showing welcome menu")
            try:
                await show_welcome_menu(message)
            except Exception as welcome_menu_error:
                logger.error(f"Error showing welcome menu: {welcome_menu_error}")
                logger.exception("Welcome menu traceback:")
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


async def display_single_question(message: types.Message, question, db_user, session: AsyncSession, state: FSMContext = None) -> None:
    """Display a single question to the user."""
    question_text = question.text
    
    # Check if the user can delete this question
    can_delete = await can_delete_question(db_user.id, question, session)
    
    # Create keyboard with answer options
    answer_buttons = [
        types.InlineKeyboardButton(
            text="👎👎",
            callback_data=f"answer:{question.id}:{AnswerType.STRONG_NO.value}"
        ),
        types.InlineKeyboardButton(
            text="👎",
            callback_data=f"answer:{question.id}:{AnswerType.NO.value}"
        ),
        types.InlineKeyboardButton(
            text="⏭️",
            callback_data=f"skip_question:{question.id}"
        ),
        types.InlineKeyboardButton(
            text="👍",
            callback_data=f"answer:{question.id}:{AnswerType.YES.value}"
        ),
        types.InlineKeyboardButton(
            text="👍👍",
            callback_data=f"answer:{question.id}:{AnswerType.STRONG_YES.value}"
        )
    ]
    
    # Create a row for actions
    action_buttons = []
    
    # Delete button (for authors or group creators)
    if can_delete:
        action_buttons.append(
            types.InlineKeyboardButton(
                text="🗑️ Delete",
                callback_data=f"delete_question:{question.id}"
            )
        )
    
    # Create keyboard with answer options in first row and actions in second row
    keyboard_rows = [answer_buttons]
    if action_buttons:
        keyboard_rows.append(action_buttons)
        
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    
    try:
        # Send the question and get the sent message object
        sent_msg = await message.answer(question_text, reply_markup=keyboard)
        logger.info(f"Successfully displayed question {question.id} for user {db_user.id}, message ID: {sent_msg.message_id}")
        
        # Store the message ID in state for future reference
        if state:
            await state.update_data(
                last_question_message_id=sent_msg.message_id,
                current_displayed_question_id=question.id
            )
        
        return sent_msg
    except Exception as e:
        logger.error(f"Error displaying question {question.id} to user {db_user.id}: {e}", exc_info=True)
        return None


async def cleanup_previous_questions(message: types.Message, state: FSMContext) -> None:
    """Clean up previously displayed unanswered question messages from the chat."""
    data = await state.get_data()
    last_question_message_id = data.get("last_question_message_id")
    last_answered_msg_id = data.get("last_answered_msg_id")  # We don't want to delete this
    
    # Only delete if it exists and is not the most recently answered question
    if last_question_message_id and last_question_message_id != last_answered_msg_id:
        try:
            await message.bot.delete_message(
                chat_id=message.chat.id,
                message_id=last_question_message_id
            )
            logger.info(f"Deleted previous unanswered question message {last_question_message_id}")
        except Exception as e:
            logger.warning(f"Failed to delete message {last_question_message_id}: {e}")


async def check_and_display_next_question(message: types.Message, db_user, group_id: int, state: FSMContext, session: AsyncSession) -> bool:
    """
    Check if there are unanswered questions for the user and display the next one.
    Returns True if a question was displayed, False otherwise.
    """
    try:
        # Get user state data
        data = await state.get_data()
        last_displayed_question_id = data.get("last_displayed_question_id")
        recently_shown_questions = data.get("recently_shown_questions", [])
        no_questions_shown = data.get("no_questions_shown", False)
        session_id = data.get("session_id", f"{db_user.id}_{group_id}_{int(time.time())}")
        
        # Ensure we have a session ID for tracking purposes
        if "session_id" not in data:
            await state.update_data(session_id=session_id)
            logger.info(f"Created new session ID {session_id} for user {db_user.id}")
        
        # Log the current session state for debugging
        logger.info(f"Session {session_id}: User {db_user.id} in group {group_id}")
        logger.info(f"Session {session_id}: Last displayed question: {last_displayed_question_id}")
        logger.info(f"Session {session_id}: Recently shown questions: {recently_shown_questions}")
        
        # Ensure any pending changes are committed to avoid inconsistent state
        try:
            await session.commit()
            await session.flush()  # Extra flush to ensure all pending changes are processed
        except Exception as e:
            logger.error(f"Error committing session in check_and_display_next_question: {e}")
            
        # Get user's current answers to make sure we have up-to-date data
        # This is critical for PostgreSQL to avoid caching issues
        try:
            current_answers = await answer_repo.get_answers_for_user_in_group(session, db_user.id, group_id)
            answered_ids = [a.question_id for a in current_answers]
        except Exception as e:
            logger.error(f"Error getting user answers in check_and_display_next_question: {e}")
            answered_ids = []
        
        logger.info(f"Session {session_id}: User has answered {len(answered_ids)} questions in group {group_id}")
        logger.info(f"Session {session_id}: Answered question IDs: {answered_ids}")
        
        # Get the total number of available questions for user in this group
        try:
            all_questions_query = select(Question).where(
                Question.group_id == group_id,
                Question.is_active == True
            )
            all_questions_result = await session.execute(all_questions_query)
            all_questions = all_questions_result.scalars().all()
            all_question_ids = [q.id for q in all_questions]
            
            total_questions = len(all_questions)
            total_available = len([q for q in all_questions if q.id not in answered_ids])
            
            logger.info(f"Session {session_id}: Total active questions: {total_questions}")
            logger.info(f"Session {session_id}: Total unanswered questions: {total_available}")
            logger.info(f"Session {session_id}: All active question IDs: {all_question_ids}")
        except Exception as e:
            logger.error(f"Error getting all questions in check_and_display_next_question: {e}")
            total_available = 1  # Assume there are questions to avoid resetting the recently shown list
        
        # If we've shown all questions or our list is getting too long, reset it
        if (len(recently_shown_questions) >= total_available) or (len(recently_shown_questions) > 100):
            recently_shown_questions = []
            if last_displayed_question_id is not None:
                recently_shown_questions = [last_displayed_question_id]  # Keep only the most recent one
            logger.info(f"Session {session_id}: Reset recently shown questions list, new list: {recently_shown_questions}")
        
        # Add any already answered questions to our exclusion list to be super safe
        exclusion_list = list(set(recently_shown_questions + answered_ids))
        if last_displayed_question_id is not None and last_displayed_question_id not in exclusion_list:
            exclusion_list.append(last_displayed_question_id)
            
        logger.info(f"Session {session_id}: Using exclusion list: {exclusion_list}")
        
        # Get the next unanswered question, excluding recently shown ones
        try:
            next_question = await question_repo.get_next_question_for_user(
                session,
                db_user.id,
                group_id,
                excluded_ids=exclusion_list
            )
        except Exception as e:
            logger.error(f"Error in get_next_question_for_user: {e}", exc_info=True)
            next_question = None
        
        # If no questions available when excluding recently shown ones,
        # but there are unanswered questions, try again with minimal exclusions
        if not next_question and total_available > 0:
            logger.info(f"Session {session_id}: No new questions with current exclusions, trying with minimal exclusions")
            # Only exclude questions we know for sure are answered
            try:
                next_question = await question_repo.get_next_question_for_user(
                    session,
                    db_user.id,
                    group_id,
                    excluded_ids=answered_ids
                )
            except Exception as e:
                logger.error(f"Error in fallback get_next_question_for_user: {e}", exc_info=True)
                next_question = None
        
        # If we found a question, display it
        if next_question:
            # Double check it's not already answered (extreme caution)
            if next_question.id in answered_ids:
                logger.error(f"Session {session_id}: CRITICAL: Question {next_question.id} was already answered but was selected for display. Skipping it.")
                # Try to recover by updating our state and returning False
                await state.update_data(
                    recently_shown_questions=exclusion_list + [next_question.id]
                )
                return False
                
            # Reset the "no questions shown" flag since we have a question to show
            if no_questions_shown:
                await state.update_data(no_questions_shown=False)
                
            # Clean up previous unanswered question messages to avoid having multiple unanswered questions
            await cleanup_previous_questions(message, state)
                
            try:
                await display_single_question(message, next_question, db_user, session, state)
                logger.info(f"Session {session_id}: Successfully displayed question {next_question.id} for user {db_user.id}")
            except Exception as e:
                logger.error(f"Error displaying question {next_question.id}: {e}", exc_info=True)
                await message.answer("An error occurred while displaying the question. Please try again.")
                return False
            
            # Update recently shown questions
            if next_question.id not in recently_shown_questions:
                recently_shown_questions.append(next_question.id)
            
            # Update state with the question we just displayed and update recently shown
            await state.update_data(
                last_displayed_question_id=next_question.id,
                recently_shown_questions=recently_shown_questions,
                current_question_id=next_question.id  # Explicit tracking of current question
            )
            
            return True
        else:
            # No more questions to answer
            # Only show the message if we haven't shown it before
            if not no_questions_shown:
                try:
                    no_questions_msg = await message.answer("No more questions from people at the moment")
                    # Store the message ID so we can delete it later if needed
                    await state.update_data(
                        no_questions_msg_id=no_questions_msg.message_id,
                        no_questions_shown=True
                    )
                    logger.info(f"Session {session_id}: No more questions available, displayed 'no questions' message")
                except Exception as e:
                    logger.error(f"Error sending 'no questions' message: {e}")
            else:
                logger.info(f"Session {session_id}: No more questions available, 'no questions' message already shown")
            
            return False
    except Exception as e:
        logger.error(f"Unexpected error in check_and_display_next_question for user {db_user.id}: {e}", exc_info=True)
        try:
            await message.answer("An error occurred while loading questions. Please try again.")
        except Exception as send_error:
            logger.error(f"Could not send error message: {send_error}")
        return False


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


async def on_load_answered_questions(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Handle the 'Load answered questions' button click."""
    await callback.answer("Loading your answered questions...")
    
    # Get user from DB
    user_tg = callback.from_user
    db_user = await user_repo.get_by_telegram_id(session, user_tg.id)
    if not db_user:
        logger.error(f"User {user_tg.id} not found in DB when loading answered questions")
        await callback.message.answer("Error: Could not find your user account. Please try /start again.")
        return
    
    # Get current group from state
    data = await state.get_data()
    group_id = data.get("current_group_id")
    if not group_id:
        logger.error(f"No group_id found in state for user {user_tg.id}")
        await callback.message.answer("Error: Could not determine your current group.")
        return
    
    # Get group info
    group = await group_repo.get(session, group_id)
    if not group:
        logger.error(f"Group {group_id} not found in DB")
        await callback.message.answer("Error: Your team no longer exists.")
        return
    
    # Get user's answers for this group
    answers = await answer_repo.get_answers_for_user_in_group(session, db_user.id, group_id)
    if not answers:
        await callback.message.answer("You haven't answered any questions in this team yet.")
        return
    
    # Get the questions for these answers
    question_ids = [a.question_id for a in answers]
    questions = await question_repo.get_questions_by_ids(session, question_ids)
    
    # Create a map of question_id -> question for quick lookup
    question_map = {q.id: q for q in questions}
    
    # Create a map of question_id -> answer for quick lookup
    answer_map = {a.question_id: a for a in answers}
    
    # Send a message for each answered question
    sent_count = 0
    for question_id, answer in answer_map.items():
        # Skip if question no longer exists (was deleted)
        if question_id not in question_map:
            continue
            
        question = question_map[question_id]
        
        # Check if user can delete this question
        can_delete = await can_delete_question(db_user.id, question, session)
        
        # User has answered this question
        answer_display = "Unknown"
        if answer.answer_type == "skip":
            answer_display = "⏭️"
        else:
            emoji_map = {
                "strong_no": "👎👎", 
                "no": "👎", 
                "yes": "👍", 
                "strong_yes": "👍👍"
            }
            answer_display = emoji_map.get(answer.answer_type, answer.answer_type)
        
        # Question text
        question_text = question.text
        
        # Add action buttons
        keyboard_buttons = []
        # Answer button
        keyboard_buttons.append(
            types.InlineKeyboardButton(
                text=answer_display,
                callback_data=f"answer:{question.id}:toggle"
            )
        )
        
        # Delete button (for authors or group creators)
        if can_delete:
            keyboard_buttons.append(
                types.InlineKeyboardButton(
                    text="🗑️ Delete",
                    callback_data=f"delete_question:{question.id}"
                )
            )
        
        # Create the keyboard with the appropriate buttons
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[keyboard_buttons])
        
        # Send directly and get the sent message object
        await callback.message.answer(question_text, reply_markup=keyboard)
        sent_count += 1
        
        # Add a delay to avoid flood control
        if sent_count % 5 == 0:
            await asyncio.sleep(0.5)
    
    logger.info(f"Displayed {sent_count} answered questions for user {db_user.id}")
    
    # Check for unanswered questions and show the first one if available
    await check_and_display_next_question(callback.message, db_user, group_id, state, session)


async def handle_group_invite(message: types.Message, group_id: int, state: FSMContext = None, session: AsyncSession = None) -> None:
    """Handle when user is invited to a specific group."""
    user = message.from_user
    
    # Fetch group details from database
    group = await group_repo.get(session, group_id)
    if not group:
        logger.error(f"Group {group_id} not found in database")
        await message.answer("Sorry, this group no longer exists.")
        return
        
    group_name = group.name
    
    logger.info(f"User {user.id} received invite to group {group_id} ({group_name})")
    
    welcome_text = (
        f"👋 Welcome to Allkinds, {user.first_name}!\n\n"
        f"You've been invited to join <b>{group_name}</b>.\n\n"
        "Would you like to join this Team?"
    )
    
    # Create keyboard with join/cancel options
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="✅ Join Team", callback_data=f"join_group:{group_id}"),
            types.InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_join"),
        ]
    ])
    
    # Store group_id in state
    if state:
        await state.update_data(invited_group_id=group_id)
    
    await message.answer(welcome_text, reply_markup=keyboard, parse_mode="HTML")


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
    await show_welcome_menu(callback.message)


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


async def on_team_confirm(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Handle team creation confirmation."""
    logger.info("--- Entered on_team_confirm handler (Restored) ---") # Restore log
    current_state = await state.get_state()
    logger.info(f"Current state inside on_team_confirm: {current_state}") # Check state
    await callback.answer() # Acknowledge

    # --- Restore the original function body ---
    logger.info(f"User {callback.from_user.id} confirmed team creation.")
    data = await state.get_data()
    team_name = data.get("team_name")
    team_description = data.get("team_description", "")

    if not team_name:
        logger.error("Team name not found in state during confirmation.")
        await callback.message.answer("Error: Team details were lost. Please start over.")
        await state.clear()
        return

    logger.debug(f"Attempting to create team: Name='{team_name}', Desc='{team_description}'")

    user_tg = callback.from_user
    db_user = await user_repo.get_by_telegram_id(session, user_tg.id)

    if not db_user:
        logger.error(f"User {user_tg.id} not found in database during team confirmation.")
        await callback.message.answer("Error creating team: User not found. Please try /start again.")
        await state.clear()
        return

    try:
        logger.debug("Calling group_repo.create...")
        # Store the creator_id in a separate variable to ensure consistency
        creator_id = db_user.id
        
        new_group = await group_repo.create(session, {
            "creator_id": creator_id,  # Use the variable here
            "name": team_name,
            "description": team_description,
            "is_active": True,
            "is_private": False
        })
        logger.info(f"Group created with ID: {new_group.id}")

        logger.debug(f"Adding creator {creator_id} to group {new_group.id}...")
        # Use the same creator_id variable here to ensure consistency
        await group_repo.add_user_to_group(
            session,
            creator_id,  # Use the same variable to ensure consistency
            new_group.id,
            role=MemberRole.CREATOR
        )
        logger.info(f"Added creator {creator_id} as member of group {new_group.id} with CREATOR role")

        logger.debug("Generating invite link...")
        bot = callback.bot
        payload = f"g{new_group.id}"
        from aiogram.utils.deep_linking import create_start_link
        invite_link = await create_start_link(bot, payload, encode=True)
        logger.info(f"Generated invite link: {invite_link}")

        success_text = (
            f"🎉 Your Team '{team_name}' has been created successfully!\n\n"
            f"Share this link to invite others to your team:\n{invite_link}\n\n"
            f"Click the button below to go to your team:"
        )

        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🚀 Go to the group", callback_data=f"go_to_group:{new_group.id}")]
        ])

        logger.info(f"Created team '{team_name}' with ID {new_group.id}, invite link: {invite_link}")

        logger.debug("Sending success message...")
        await callback.message.edit_text(success_text, reply_markup=keyboard)
        logger.info("Success message sent.")

        # Explicitly commit the session before clearing state
        await session.commit()
        logger.info("Session committed after successful team creation.")

        # Instead of state.clear(), update state with essential info
        await state.update_data(
            team_name=None, # Clear specific temp data
            team_description=None, # Clear specific temp data
            current_group_id=new_group.id, # Keep group ID
            current_group_name=new_group.name, # Keep group name
            current_db_user_id=creator_id # <<< Store the creator_id (same as db_user.id)
        )
        await state.set_state(None) # Reset FSM state to default
        logger.info(f"State updated after team creation: group={new_group.id}, user={creator_id}")

    except Exception as e:
        logger.exception(f"Error creating team for user {user_tg.id}")
        # Add rollback here in case of error
        await session.rollback()
        logger.warning("Session rolled back due to error in team creation.")
        try:
            await callback.message.edit_text("Error creating team. Please try again or contact support.")
        except Exception as send_err:
            logger.error(f"Failed to send error message to user {user_tg.id}: {send_err}")


async def on_team_cancel(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Handle team creation cancellation."""
    await callback.answer("Team creation canceled")
    
    # Clear state and show welcome menu
    await state.clear()
    await show_welcome_menu(callback.message)


async def process_join_code(message: types.Message, state: FSMContext, session: AsyncSession) -> None:
    """Process team join code input from user."""
    code = message.text.strip()
    
    # Try to extract a group ID from the code (format should be g{ID})
    group_id = None
    if code.startswith('g') and code[1:].isdigit():
        group_id = int(code[1:])
    else:
        await message.answer("Invalid code format. Please enter a valid team code.")
        return
    
    # Check if the group exists in the database
    group = await group_repo.get(session, group_id)
    if not group:
        logger.error(f"User {message.from_user.id} tried to join nonexistent group {group_id}")
        await message.answer("Sorry, this team doesn't exist. Please check the code and try again.")
        return
    
    # Store the team info
    await state.update_data(joining_team_id=group_id, joining_team_name=group.name)
    
    # Send confirmation
    confirmation_text = (
        f"You're about to join the team '{group.name}'.\n\n"
        f"Is this correct?"
    )
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="✅ Join", callback_data=f"confirm_join:{group_id}"),
            types.InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_join"),
        ]
    ])
    
    await message.answer(confirmation_text, reply_markup=keyboard)


async def on_join_confirm(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Handle team join confirmation."""
    await callback.answer()
    
    # Get team ID from callback data
    group_id = int(callback.data.split(":")[1])
    
    # Get the group from database
    group = await group_repo.get(session, group_id)
    if not group:
        logger.error(f"Group {group_id} not found in database during join confirmation")
        await callback.message.answer("Sorry, this group no longer exists.")
        await state.clear()
        return
    
    # Get user from DB
    user_tg = callback.from_user
    db_user, _ = await user_repo.get_or_create_user(session, {
        "id": user_tg.id,
        "first_name": user_tg.first_name,
        "last_name": user_tg.last_name,
        "username": user_tg.username
    })
    
    # Add user to the group as a member
    try:
        await group_repo.add_user_to_group(session, db_user.id, group_id)
        logger.info(f"Added user {db_user.id} to group {group_id} as a member")
    except Exception as e:
        logger.error(f"Error adding user to group: {e}")
        await callback.message.answer("Error joining the team. Please try again.")
        return
    
    success_text = (
        f"🎉 You've successfully joined the team '{group.name}'!\n\n"
        f"Use /questions to start answering questions in this team."
    )
    
    logger.info(f"User {db_user.id} joined group {group_id} ({group.name})")
    await callback.message.answer(success_text)
    
    # Update state data without showing redundant menu text
    await state.update_data(current_group_id=group_id, current_group_name=group.name)
    await state.set_state(QuestionFlow.viewing_question)
    
    # Show only the menu buttons without the redundant text
    await show_group_menu(callback.message, group_id, group.name, state, current_section="questions", session=session)


async def show_group_menu(message: types.Message, group_id: int, group_name: str, state: FSMContext, edit: bool = False, current_section: str = None, session: AsyncSession = None, text: str = None) -> None:
    """Shows the main menu for a user within a group.
    If text is None, will use a welcome message instead of trying to use invisible characters.
    """
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
        
        # Get the reply keyboard with points balance
        try:
            keyboard = get_group_menu_reply_keyboard(current_section, balance=points)
            logger.debug(f"Created keyboard for section {current_section} with points {points}")
        except Exception as keyboard_error:
            logger.error(f"Error creating keyboard: {keyboard_error}")
            # Fallback to a simple keyboard
            keyboard = types.ReplyKeyboardMarkup(
                keyboard=[
                    [types.KeyboardButton(text="💬 Questions"), types.KeyboardButton(text="💞 Find Match")],
                    [types.KeyboardButton(text="➕ Add Question"), types.KeyboardButton(text="ℹ️ Group Info")],
                    [types.KeyboardButton(text="🏠 Start Menu")]
                ],
                resize_keyboard=True
            )
            logger.info("Using fallback keyboard due to error")
        
        # Always use visible text - no more invisible characters
        if text is None:
            if current_section == "questions":
                display_text = f"📋 Questions in {group_name}"
            elif current_section == "matches":
                display_text = f"💞 Find matches in {group_name}"
            elif current_section == "add_question":
                display_text = f"➕ Add new question to {group_name}"
            elif current_section == "group_info":
                display_text = f"ℹ️ Information about {group_name}"
            else:
                # Default section - just show points, no welcome message
                if points_text:
                    display_text = points_text
                else:
                    display_text = "・" # Minimal text character that Telegram accepts
        else:
            display_text = text
            
        logger.info(f"Using display text: '{display_text}'")

        # Try editing the previous menu message if possible
        data = await state.get_data()
        prev_menu_msg_id = data.get("group_menu_msg_id")
        is_callback = isinstance(message, types.CallbackQuery)
        
        if prev_menu_msg_id and is_callback: # Only edit on callbacks
            try:
                logger.info(f"Attempting to edit previous menu message {prev_menu_msg_id}")
                await message.message.edit_text(display_text, reply_markup=keyboard, parse_mode="HTML")
                await state.update_data(group_menu_msg_id=message.message.message_id) # Update stored ID
                logger.info(f"Successfully edited menu message {prev_menu_msg_id}")
                return # Edited successfully, no need to send new message
            except Exception as edit_err:
                logger.warning(f"Could not edit previous menu message {prev_menu_msg_id}: {edit_err}")
                # Proceed to send a new message

        # If editing failed or not applicable, send a new message
        try:
            logger.info("Sending new menu message")
            menu_msg = await message.answer(display_text, reply_markup=keyboard, parse_mode="HTML")
            await state.update_data(group_menu_msg_id=menu_msg.message_id)
            logger.info(f"Sent new menu message with ID: {menu_msg.message_id}")
        except Exception as answer_error:
            logger.error(f"Error sending menu message: {answer_error}")
            # Last resort fallback - just show a plain text message
            await message.answer(f"Welcome to {group_name}. Use the commands to navigate.")
            logger.info("Sent fallback plain text message")
    except Exception as e:
        logger.error(f"Error in show_group_menu: {e}")
        logger.exception("Full traceback for group menu error:")
        # Send a fallback message even if there's an error
        try:
            await message.answer(f"Error showing menu for {group_name}. Please try /start to restart.")
        except:
            pass


async def on_join_group_callback(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Handle when user clicks the Join Team button from invite."""
    await callback.answer()
    
    # Extract group ID from callback data
    group_id = int(callback.data.split(":")[1])
    
    # Fetch group details from database
    group = await group_repo.get(session, group_id)
    if not group:
        logger.error(f"Group {group_id} not found in database")
        await callback.answer("Sorry, this group no longer exists.", show_alert=True)
        return
        
    group_name = group.name
    
    # Get user from DB
    user_tg = callback.from_user
    db_user, _ = await user_repo.get_or_create_user(session, {
        "id": user_tg.id,
        "first_name": user_tg.first_name,
        "last_name": user_tg.last_name,
        "username": user_tg.username
    })
    
    # Check if the user was previously in this group
    was_member = await group_repo.is_user_in_group(session, db_user.id, group_id)
    
    # Add user to the group as a member (or update if already exists)
    try:
        await group_repo.add_user_to_group(session, db_user.id, group_id)
        logger.info(f"Added user {db_user.id} to group {group_id} as a member")
        
        # If user is rejoining, make sure their profile data is cleared
        if was_member:
            logger.info(f"User {db_user.id} is rejoining group {group_id} - checking profile data")
            
            member = await group_repo.get_group_member(session, db_user.id, group_id)
            if member and (getattr(member, "nickname", None) or getattr(member, "photo_file_id", None)):
                logger.info(f"Clearing existing profile data for rejoining user {db_user.id}")
                stmt = update(GroupMember).where(
                    (GroupMember.user_id == db_user.id) & 
                    (GroupMember.group_id == group_id)
                ).values(
                    nickname=None,
                    photo_file_id=None
                )
                await session.execute(stmt)
                await session.commit()
    except Exception as e:
        logger.error(f"Error adding user to group: {e}")
        await callback.message.answer("Error joining the team. Please try again.")
        return
    
    await state.update_data(
        current_group_id=group_id,
        current_group_name=group_name
    )
    
    success_text = f"🎉 You've successfully joined <b>{group_name}</b>!"
    logger.info(f"User {callback.from_user.id} joined group {group_id} ({group_name})")
    
    # Edit the original message to show success
    await callback.message.edit_text(success_text, parse_mode="HTML")
    
    # Always force onboarding process when joining a group, since profile data may be cleared or never set
    logger.info(f"Starting onboarding process for user {db_user.id} in group {group_id}")
    await state.set_state(GroupOnboarding.waiting_for_nickname)
    await callback.message.answer("To complete your profile, please enter your nickname for this group (2-32 characters, must be unique in this group):")
    return


# --- Placeholder handlers for group menu buttons ---

async def on_show_questions(message: types.Message, state: FSMContext, session: AsyncSession) -> None:
    """Fetches and displays all questions for the user's group as a feed, with each question as a separate message."""
    user_tg = message.from_user
    data = await state.get_data() # Get state data first
    db_user_id_from_state = data.get("current_db_user_id") # Check for passed DB ID

    db_user = None
    if db_user_id_from_state:
        logger.info(f"Attempting to fetch user by DB ID {db_user_id_from_state} from state.")
        db_user = await user_repo.get(session, db_user_id_from_state) # Fetch by DB ID
        if db_user:
             logger.info(f"Successfully fetched user by DB ID from state.")
        else:
             logger.warning(f"Failed to fetch user by DB ID {db_user_id_from_state} from state. Falling back to TG ID.")
             # Clear the potentially invalid ID from state?
             # await state.update_data(current_db_user_id=None)

    if not db_user: # If fetch by DB ID failed or ID wasn't in state
        logger.info(f"Fetching user by Telegram ID {user_tg.id}.")
        db_user = await user_repo.get_by_telegram_id(session, user_tg.id) # Fallback fetch by TG ID

    if not db_user: # Final check
        logger.error(f"User {user_tg.id} not found in DB when showing questions (checked state ID and TG ID)")
        await message.answer("Error: Could not find your user account. Please try /start again.")
        return

    data = await state.get_data()
    group_id = data.get("current_group_id")
    if not group_id:
        logger.error(f"No group_id found in state for user {user_tg.id}")
        await message.answer("Error: Could not determine your current group. Please go back to the main menu.")
        return
        
    # Fetch group to get name
    group = await group_repo.get(session, group_id)
    if not group:
        logger.error(f"Group {group_id} not found in DB")
        await message.answer("Error: Your team no longer exists. Please try /start again.")
        return
    
    # Verify user is a member of this group
    user_groups = await group_repo.get_user_groups(session, db_user.id)
    is_member = any(g.id == group_id for g in user_groups)
    if not is_member:
        logger.warning(f"User {db_user.id} attempted to view questions for group {group_id} but is not a member")
        await message.answer("You are not a member of this team. Please join first.")
        return
    
    # Show the group menu with "Questions" section marked as current
    await show_group_menu(message, group_id, group.name, state, current_section="questions", session=session)
    
    # Log the group membership 
    logger.info(f"User {db_user.id} (TG: {user_tg.id}) viewing questions for group {group_id} ({group.name})")
    
    # Clear any previous question-message mappings to avoid stale data
    await state.update_data(message_question_map={})
    
    # Set state to answering questions
    await state.set_state(QuestionFlow.answering)
    logger.info(f"Setting state to QuestionFlow.answering for question feed")
    
    # Get fresh list of ALL questions for the group - force a database refresh
    # Clear any SQLAlchemy cache by using a new transaction
    await session.commit()  # Commit any pending changes
    questions = await question_repo.get_group_questions(session, group_id)
    
    # Log the number of questions found to help with debugging
    logger.info(f"Found {len(questions)} active questions for group {group_id} for user {db_user.id}")
    
    # Get user's answers for this group - fresh query
    answers = await answer_repo.get_answers_for_user_in_group(session, db_user.id, group_id)
    
    # Create a map of question_id -> answer for quick lookup
    answer_map = {answer.question_id: answer for answer in answers}
    
    # Check if chat is private (DM) or group
    chat_id = message.chat.id
    
    # Send welcome message
    welcome_text = f"Questions for {group.name}:"
    welcome_msg = await message.answer(welcome_text)
    
    # First, delete any existing question messages to avoid duplicates
    try:
        # Send a temporary message to indicate refreshing
        status_msg = await message.answer("Refreshing questions...")
        
        # Track if user has any unanswered questions
        has_unanswered = False
        
        # Dictionary to track which message_id corresponds to which question_id
        message_question_map = {}
        
        # Separate questions into answered and unanswered
        answered_questions = []
        unanswered_questions = []
        
        for question in questions:
            if question.id in answer_map:
                answered_questions.append(question)
            else:
                unanswered_questions.append(question)
                has_unanswered = True
        
        # Try to delete the status message
        await status_msg.delete()
    except Exception as e:
        logger.error(f"Error preparing question display: {e}")
        # Continue anyway
    
    # Display all answered questions first
    for question in answered_questions:
        answer = answer_map.get(question.id)
        is_author = question.author_id == db_user.id
        
        # User has answered this question
        answer_display = "Unknown"
        if answer.answer_type == "skip":
            answer_display = "⏭️"
        else:
            emoji_map = {
                "strong_no": "👎👎", 
                "no": "👎", 
                "yes": "👍", 
                "strong_yes": "👍👍"
            }
            answer_display = emoji_map.get(answer.answer_type, answer.answer_type)
        
        # Just the question text without quotation marks
        question_text = question.text
        
        # Add action buttons
        keyboard_buttons = []
        # Answer button
        keyboard_buttons.append(
            types.InlineKeyboardButton(
                text=answer_display,
                callback_data=f"answer:{question.id}:toggle"
            )
        )
        
        # Delete button (only for authors)
        if is_author:
            keyboard_buttons.append(
                types.InlineKeyboardButton(
                    text="🗑️ Delete",
                    callback_data=f"delete_question:{question.id}"
                )
            )
            
        # Create the keyboard with the appropriate buttons
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[keyboard_buttons])
        
        # Send directly using bot.send_message and get the sent message object
        sent_message = await message.bot.send_message(chat_id, question_text, reply_markup=keyboard)
        
        # Store the mapping between message_id and question_id
        message_question_map[sent_message.message_id] = question.id
        
        # Add a delay to ensure separation and avoid flood control
        await asyncio.sleep(0.3)
    
    # Then display all unanswered questions
    for question in unanswered_questions:
        is_author = question.author_id == db_user.id
        
        # Just the question text without quotation marks
        question_text = question.text
        
        # Create keyboard with answer options
        answer_buttons = [
            types.InlineKeyboardButton(
                text="👎👎",
                callback_data=f"answer:{question.id}:{AnswerType.STRONG_NO.value}"
            ),
            types.InlineKeyboardButton(
                text="👎",
                callback_data=f"answer:{question.id}:{AnswerType.NO.value}"
            ),
            types.InlineKeyboardButton(
                text="⏭️",
                callback_data=f"skip_question:{question.id}"
            ),
            types.InlineKeyboardButton(
                text="👍",
                callback_data=f"answer:{question.id}:{AnswerType.YES.value}"
            ),
            types.InlineKeyboardButton(
                text="👍👍",
                callback_data=f"answer:{question.id}:{AnswerType.STRONG_YES.value}"
            )
        ]
        
        # Create a row for actions
        action_buttons = []
        
        # Delete button (only for authors)
        if is_author:
            action_buttons.append(
                types.InlineKeyboardButton(
                    text="🗑️ Delete",
                    callback_data=f"delete_question:{question.id}"
                )
            )
        
        # Create keyboard with answer options in first row and actions in second row
        keyboard_rows = [answer_buttons]
        if action_buttons:
            keyboard_rows.append(action_buttons)
            
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
        
        # Send the question and get the sent message object
        sent_message = await message.bot.send_message(chat_id, question_text, reply_markup=keyboard)
        
        # Store the mapping between message_id and question_id
        message_question_map[sent_message.message_id] = question.id
        
        # Add a delay to ensure separation and avoid flood control
        await asyncio.sleep(0.3)
    
    # Store the message_question_map in state for later reference
    await state.update_data(message_question_map=message_question_map)
    
    # Check if no questions were found
    if not answered_questions and not unanswered_questions:
        await message.answer("No questions found for this group yet. Add the first question!")


async def on_skip_question(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Handle when user skips a question via the skip button."""
    await callback.answer("Question skipped")
    
    # Clean up any instruction or group info messages
    data = await state.get_data()
    group_info_msg_id = data.get("group_info_msg_id")
    instructions_msg_id = data.get("instructions_msg_id")
    find_match_message_id = data.get("find_match_message_id")
    pending_match_message_id = data.get("pending_match_message_id")
    
    if group_info_msg_id:
        try:
            await callback.bot.delete_message(callback.message.chat.id, group_info_msg_id)
            await state.update_data(group_info_msg_id=None)
        except Exception as e:
            logger.warning(f"Failed to delete group info message: {e}")
    
    if instructions_msg_id:
        try:
            await callback.bot.delete_message(callback.message.chat.id, instructions_msg_id)
            await state.update_data(instructions_msg_id=None)
        except Exception as e:
            logger.warning(f"Failed to delete instructions message: {e}")
    
    if find_match_message_id:
        try:
            await callback.bot.delete_message(callback.message.chat.id, find_match_message_id)
            await state.update_data(find_match_message_id=None)
        except Exception as e:
            logger.warning(f"Failed to delete find match message: {e}")
            
    if pending_match_message_id:
        try:
            await callback.bot.delete_message(callback.message.chat.id, pending_match_message_id)
            await state.update_data(pending_match_message_id=None, has_pending_match=False)
        except Exception as e:
            logger.warning(f"Failed to delete pending match message: {e}")
    
    # Extract question ID from callback data
    question_id = int(callback.data.split(":")[1])
    
    # Get user from DB
    user_tg = callback.from_user
    db_user = await user_repo.get_by_telegram_id(session, user_tg.id)
    if not db_user:
        logger.error(f"User {user_tg.id} not found in DB for skipping.")
        await callback.answer("Error: Could not find your user account.", show_alert=True)
        return
    
    # Get the question to check authorship
    question = await question_repo.get(session, question_id)
    if not question:
        await callback.answer("This question no longer exists.", show_alert=True)
        return
    
    # Save skip answer
    try:
        await answer_repo.save_answer(
            session=session,
            user_id=db_user.id,
            question_id=question_id,
            answer_type="skip",
            value=0
        )
        
        logger.info(f"User {db_user.id} skipped question {question_id}")
        
        # Check if user can delete this question
        can_delete = await can_delete_question(db_user.id, question, session)
        
        # Create keyboard buttons
        keyboard_buttons = [
            types.InlineKeyboardButton(
                text="⏭️",
                callback_data=f"answer:{question_id}:toggle"
            )
        ]
        
        # Add delete button if user can delete the question
        if can_delete:
            keyboard_buttons.append(
                types.InlineKeyboardButton(
                    text="🗑️ Delete",
                    callback_data=f"delete_question:{question.id}"
                )
            )
        
        # Create the keyboard with the appropriate buttons
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[keyboard_buttons])
        
        # Edit the message to show the skipped status with delete button if author
        await callback.message.edit_reply_markup(reply_markup=keyboard)
        
        # Explicitly commit the session to make sure the skip is saved to the database
        # before we query for the next question
        await session.commit()
        
        # For PostgreSQL in Railway environment, ensure the transaction is complete
        try:
            await session.flush()
            logger.info(f"Session flushed after skipping question {question_id} by user {db_user.id}")
        except Exception as e:
            logger.warning(f"Error flushing session after skip: {e}")
        
        # Get the next question for the user to answer
        # Use the question's group_id directly instead of fetching from state
        group_id = question.group_id
        if group_id:
            # Use our helper function to check and display the next question
            await check_and_display_next_question(callback.message, db_user, group_id, state, session)
    except Exception as e:
        logger.error(f"Error skipping question {question_id}: {e}")
        await callback.answer("Error skipping question. Please try again.", show_alert=True)


async def on_delete_question(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Handle when user wants to delete a question."""
    await callback.answer("Delete this question?")
    
    # Parse question ID from callback data
    question_id = int(callback.data.split(":")[1])
    
    # Set state to confirming_delete
    await state.set_state(QuestionFlow.confirming_delete)
    await state.update_data(delete_question_id=question_id)
    
    # Get the question from the database
    question = await question_repo.get(session, question_id)
    if not question:
        await callback.message.edit_text("This question no longer exists.")
        return
    
    # Create keyboard with confirm/cancel buttons
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(
                text="✅ Delete",
                callback_data=f"confirm_delete_question:{question_id}"
            ),
            types.InlineKeyboardButton(
                text="❌ Cancel",
                callback_data=f"cancel_delete_question:{question_id}"
            ),
        ]
    ])
    
    # Show confirmation
    await callback.message.edit_text(
        text=f"Are you sure you want to delete this question?\n\n{question.text}",
        reply_markup=keyboard
    )


async def on_confirm_delete_question(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Handle confirmation of question deletion."""
    await callback.answer("Deleting question...")
    
    # Extract question ID from callback data
    question_id = int(callback.data.split(":")[1])
    
    # Get user from DB
    user_tg = callback.from_user
    db_user = await user_repo.get_by_telegram_id(session, user_tg.id)
    if not db_user:
        await callback.message.edit_text("Error: Could not find your user account.")
        return
    
    # Get the question
    question = await question_repo.get(session, question_id)
    if not question:
        await callback.message.edit_text("This question no longer exists.")
        return
    
    # Check if user can delete this question
    can_delete = await can_delete_question(db_user.id, question, session)
    if not can_delete:
        await callback.message.edit_text("You can only delete questions you created or as a team creator.")
        return
    
    # Delete the question
    await question_repo.delete(session, question_id)
    await session.commit()
        
    # Log the deletion
    is_author = question.author_id == db_user.id
    if is_author:
        logger.info(f"User {db_user.id} deleted their own question {question_id}")
    else:
        logger.info(f"User {db_user.id} as group creator deleted question {question_id} created by user {question.author_id}")
        
    # Delete the message instead of showing "Question deleted"
    try:
        await callback.message.delete()
    except Exception as e:
        logger.warning(f"Failed to delete message after question deletion: {e}")
    
    # Clear state
    await state.clear()
    
    # Get group ID and name from state data
    data = await state.get_data()
    group_id = data.get("current_group_id")
    group_name = data.get("current_group_name")
    
    # Set state back to viewing_question
    if group_id and group_name:
        await state.update_data(current_group_id=group_id, current_group_name=group_name)
        await state.set_state(QuestionFlow.viewing_question)


async def on_cancel_delete_question(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """
    Handle cancellation of question deletion.
    Simply dismisses the confirmation dialog by deleting the message.
    """
    await callback.answer("Cancelled")
    
    # Delete the confirmation message
    try:
        await callback.message.delete()
    except Exception as e:
        logger.warning(f"Failed to delete confirmation message: {e}")
    
    # Clear confirmation state and return to viewing questions
    await state.set_state(QuestionFlow.viewing_question)


async def send_question_notification(bot: Bot, question_id: int, group_id: int, session: AsyncSession) -> None:
    """Send a notification about a new question to all group members."""
    question = await question_repo.get(session, question_id)
    if not question:
        logger.error(f"Question {question_id} not found for notification")
        return
        
    group = await group_repo.get(session, group_id)
    if not group:
        logger.error(f"Group {group_id} not found for notification")
        return
    
    # Get all group members
    group_members = await group_repo.get_group_members(session, group_id)
    logger.info(f"Sending notification about question {question_id} to {len(group_members)} group members")
    
    # Format the notification message with just the question text, no header
    notification_text = question.text
    
    # Add answer buttons
    keyboard = get_answer_keyboard_with_skip(question_id)
    
    # Send to each member except the author
    notify_count = 0
    for member in group_members:
        if member.user_id != question.author_id:
            try:
                # Get user's Telegram ID
                user = await user_repo.get(session, member.user_id)
                if user and user.telegram_id:
                    logger.debug(f"Sending notification for question {question_id} to user {user.telegram_id} (ID: {user.id})")
                    sent_message = await bot.send_message(
                        chat_id=user.telegram_id,
                        text=notification_text,
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
                    if sent_message:
                        notify_count += 1
                        logger.info(f"Successfully sent question notification to user {user.telegram_id}")
                    else:
                        logger.warning(f"Failed to send notification to user {user.telegram_id} - message not returned")
            except Exception as e:
                logger.error(f"Failed to send question notification to user {member.user_id}: {e}")
    
    logger.info(f"Completed sending notifications: {notify_count} of {len(group_members)-1} users notified about question {question_id}")


# --- Placeholder handlers for question confirmation ---

async def process_new_question_text(message: types.Message, state: FSMContext, session: AsyncSession) -> None:
    """Handle the text entered by the user for a new question."""
    question_text = message.text.strip()
    user_id = message.from_user.id
    data = await state.get_data()
    group_id = data.get("current_group_id")
    
    # Clean up any instruction or group info messages
    group_info_msg_id = data.get("group_info_msg_id")
    instructions_msg_id = data.get("instructions_msg_id")
    
    if group_info_msg_id:
        try:
            await message.bot.delete_message(message.chat.id, group_info_msg_id)
            await state.update_data(group_info_msg_id=None)
        except Exception as e:
            logger.warning(f"Failed to delete group info message: {e}")
    
    if instructions_msg_id:
        try:
            await message.bot.delete_message(message.chat.id, instructions_msg_id)
            await state.update_data(instructions_msg_id=None)
        except Exception as e:
            logger.warning(f"Failed to delete instructions message: {e}")
    
    # Get message IDs for cleanup
    question_prompt_msg_id = data.get("question_prompt_msg_id")
    add_question_user_msg_id = data.get("add_question_user_msg_id")
    menu_msg_id = data.get("menu_msg_id")
    
    if not group_id:
        logger.error(f"User {user_id} submitted question but no group_id found in state.")
        await message.answer("Error: Could not determine your current group. Please go back to the main menu.")
        await state.clear()
        return
        
    logger.info(f"User {user_id} submitted question text for group {group_id}: '{question_text[:50]}...'")
    
    # Basic validation
    if len(question_text) < 10:
        validation_msg = await message.answer("Your question seems a bit short. Please provide more detail.")
        await state.update_data(validation_msg_id=validation_msg.message_id)
        return
    if len(question_text) > 500:
        validation_msg = await message.answer("Your question is too long (max 500 characters). Please shorten it.")
        await state.update_data(validation_msg_id=validation_msg.message_id)
        return
    
    # Delete the "Please ask your yes/no question:" prompt message
    if question_prompt_msg_id:
        try:
            await message.bot.delete_message(message.chat.id, question_prompt_msg_id)
        except Exception as e:
            logger.warning(f"Failed to delete question prompt message: {e}")
    
    # Delete the user's "➕ Add Question" message if it exists
    if add_question_user_msg_id:
        try:
            await message.bot.delete_message(message.chat.id, add_question_user_msg_id)
        except Exception as e:
            logger.warning(f"Failed to delete add question user message: {e}")
    
    # Delete menu message if it exists (from callback path)
    if menu_msg_id:
        try:
            await message.bot.delete_message(message.chat.id, menu_msg_id)
        except Exception as e:
            logger.warning(f"Failed to delete menu message: {e}")
    
    # Show waiting message while checking with OpenAI
    waiting_msg = await message.answer("Checking your question, please wait...")
    await state.update_data(waiting_msg_id=waiting_msg.message_id)
    
    # Check for spelling errors
    has_spelling_errors, corrected_text = await check_spelling(question_text)
    if has_spelling_errors:
        # Delete waiting message
        try:
            await message.bot.delete_message(message.chat.id, waiting_msg.message_id)
        except Exception as e:
            logger.warning(f"Failed to delete waiting message: {e}")
            
        # Store both versions of the text
        await state.update_data(
            original_question_text=question_text,
            corrected_question_text=corrected_text
        )
        
        # Show the correction suggestion with inline buttons
        correction_text = f"Did you mean:\n\n<b>{corrected_text}</b>"
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [
                types.InlineKeyboardButton(text="✅ Yes, use this", callback_data="use_corrected_text"),
                types.InlineKeyboardButton(text="❌ No, use original", callback_data="use_original_text"),
            ]
        ])
        
        correction_msg = await message.answer(correction_text, reply_markup=keyboard, parse_mode="HTML")
        await state.update_data(
            correction_msg_id=correction_msg.message_id,
            original_question_message_id=message.message_id
        )
        await state.set_state(QuestionFlow.choosing_correction)
        return
    
    # Check if it's a yes/no question using OpenAI
    is_yes_no, yes_no_reason = await is_yes_no_question(question_text)
    if not is_yes_no:
        # Delete waiting message
        try:
            await message.bot.delete_message(message.chat.id, waiting_msg.message_id)
        except Exception as e:
            logger.warning(f"Failed to delete waiting message: {e}")
            
        validation_msg = await message.answer("🙋‍♂️ Please ask a question that can be answered with Agree/Disagree.")
        await state.update_data(validation_msg_id=validation_msg.message_id)
        return
    
    # Check for duplicate questions
    is_duplicate, duplicate_text, duplicate_id = await check_duplicate_question(question_text, group_id, session)
    if is_duplicate:
        # Delete waiting message
        try:
            await message.bot.delete_message(message.chat.id, waiting_msg.message_id)
        except Exception as e:
            logger.warning(f"Failed to delete waiting message: {e}")
            
        duplicate_msg = await message.answer(f"🔄 This seems similar to an existing question. Please try a different question.")
        await state.update_data(validation_msg_id=duplicate_msg.message_id)
        return
    
    # Delete waiting message before showing confirmation
    try:
        await message.bot.delete_message(message.chat.id, waiting_msg.message_id)
    except Exception as e:
        logger.warning(f"Failed to delete waiting message: {e}")
        
    # Store the question text, user's message ID, and ask for confirmation
    await state.update_data(
        new_question_text=question_text,
        original_question_message_id=message.message_id
    )
    confirmation_text = f"Your question:\n\n{question_text}\n\nIs this correct and ready to be added?"
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="✅ Yes", callback_data="confirm_add_question"),
            types.InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_add_question"),
        ]
    ])
    confirmation_message = await message.answer(confirmation_text, reply_markup=keyboard)
    await state.update_data(confirmation_message_id=confirmation_message.message_id)
    await state.set_state(QuestionFlow.reviewing_question)


async def on_confirm_add_question(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Handle confirmation of adding a new question."""
    user_data = await state.get_data()
    question_text = user_data.get("new_question_text", "")
    group_id = user_data.get("current_group_id")
    group_name = user_data.get("current_group_name", f"Team {group_id}")
    original_question_message_id = user_data.get("original_question_message_id")
    confirmation_message_id = user_data.get("confirmation_message_id")
    validation_msg_id = user_data.get("validation_msg_id")
    last_question_message_id = user_data.get("last_question_message_id")
    last_answered_msg_id = user_data.get("last_answered_msg_id")  # We don't want to delete this
    
    if not question_text or not group_id:
        await callback.answer("Error: Missing question text or group ID", show_alert=True)
        return
    
    # Clean up any existing unanswered question messages to avoid multiple unanswered questions
    if last_question_message_id and last_question_message_id != last_answered_msg_id:
        try:
            await callback.bot.delete_message(
                chat_id=callback.message.chat.id,
                message_id=last_question_message_id
            )
            logger.info(f"Deleted previous unanswered question message {last_question_message_id}")
        except Exception as e:
            logger.warning(f"Failed to delete previous unanswered question message: {e}")
    
    # Get user from DB
    user_tg = callback.from_user
    db_user, _ = await user_repo.get_or_create_user(session, {
        "id": user_tg.id,
        "first_name": user_tg.first_name,
        "last_name": user_tg.last_name,
        "username": user_tg.username
    })
    
    # Create and save the question
    try:
        new_question = await question_repo.create_question(
            session=session, 
            author_id=db_user.id, 
            group_id=group_id, 
            text=question_text
        )
        logger.info(f"User {db_user.id} added question (ID: {new_question.id}) to group {group_id}: '{question_text[:20]}...'")
        
        # Award points for creating a question
        updated_user = await user_repo.add_points(session, db_user.id, 5)
        logger.info(f"Awarded 5 points to user {db_user.id} for creating a question. New balance: {updated_user.points}💎")
        
        # Delete the validation message if it exists
        if validation_msg_id:
            try:
                await callback.bot.delete_message(
                    chat_id=callback.message.chat.id,
                    message_id=validation_msg_id
                )
            except Exception as e:
                logger.warning(f"Failed to delete validation message: {e}")
        
        # Delete the confirmation message (the message with the inline buttons)
        try:
            if callback.message and callback.message.message_id:
                await callback.message.delete()
                logger.info(f"Deleted confirmation message with ID {callback.message.message_id}")
        except Exception as e:
            logger.warning(f"Failed to delete confirmation message: {e}")
            
        # Delete the original question message if it exists
        if original_question_message_id:
            try:
                await callback.bot.delete_message(
                    chat_id=callback.message.chat.id,
                    message_id=original_question_message_id
                )
                logger.info(f"Deleted original question message with ID {original_question_message_id}")
            except Exception as e:
                logger.warning(f"Failed to delete original question message: {e}")
        
        # Final success message - shorter and showing the balance
        success_text = f"✅ Question added and 5 💎 points awarded.\nYour balance is: {updated_user.points} 💎 points."
        success_msg = await callback.message.answer(success_text)
        
        # Store success message ID in state to delete it later when user answers
        await state.update_data(question_added_success_msg_id=success_msg.message_id)
        
        # Send notification to other group members
        try:
            await send_question_notification(callback.bot, new_question.id, group_id, session)
        except Exception as e:
            logger.error(f"Failed to send question notifications: {e}")
            # Continue execution - this is not a fatal error
        
        # Send the new question with answer buttons
        keyboard = get_answer_keyboard_with_skip(new_question.id)
        
        # Add delete button for the author
        # Get the current keyboard rows
        current_rows = keyboard.inline_keyboard
        # Add a second row with the delete button
        delete_button = [
            types.InlineKeyboardButton(
                text="🗑️ Delete",
                callback_data=f"delete_question:{new_question.id}"
            )
        ]
        current_rows.append(delete_button)
        # Create new keyboard with the additional row
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=current_rows)
        
        # Send the new question - just the text without quotes
        question_msg = await callback.bot.send_message(
            chat_id=callback.message.chat.id,
            text=new_question.text,
            reply_markup=keyboard
        )
        
        # Get current recently shown questions
        data = await state.get_data()
        recently_shown_questions = data.get("recently_shown_questions", [])
        
        # Add the new question to recently shown list
        if new_question.id not in recently_shown_questions:
            recently_shown_questions.append(new_question.id)
            # Keep the list at a reasonable size
            if len(recently_shown_questions) > 50:
                recently_shown_questions = recently_shown_questions[-50:]
        
        # Store the question ID in state to prevent showing it again
        await state.update_data(
            last_displayed_question_id=new_question.id,
            last_displayed_question_message_id=question_msg.message_id,
            recently_shown_questions=recently_shown_questions
        )
        
        # Set state back to viewing question
        await state.set_state(QuestionFlow.viewing_question)
        
    except Exception as e:
        logger.error(f"Error saving question: {str(e)}", exc_info=True)
        # Try to provide a more useful error message
        error_message = f"Failed to save your question. Error: {str(e)[:50]}"
        try:
            await callback.answer(error_message, show_alert=True)
        except Exception:
            # Fallback if callback answer fails
            try:
                await callback.message.reply(error_message)
            except Exception as reply_error:
                logger.error(f"Could not notify user of error: {reply_error}")
        
        # Try to rollback the transaction
        try:
            await session.rollback()
        except Exception as rollback_error:
            logger.error(f"Error rolling back transaction: {rollback_error}")


async def on_cancel_add_question(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Handle cancellation of adding a new question."""
    # Get message IDs for cleanup
    data = await state.get_data()
    original_question_message_id = data.get("original_question_message_id")
    confirmation_message_id = data.get("confirmation_message_id")
    validation_msg_id = data.get("validation_msg_id")
    
    # Set state back to viewing_question
    await state.set_state(QuestionFlow.viewing_question)
    
    # Delete user's original message with the question text
    if original_question_message_id:
        try:
            await callback.bot.delete_message(
                chat_id=callback.message.chat.id,
                message_id=original_question_message_id
            )
        except Exception as e:
            logger.warning(f"Failed to delete user's original question message: {e}")
    
    # Delete the confirmation message
    if callback.message and callback.message.message_id:
        try:
            await callback.message.delete()
            logger.info(f"Deleted confirmation message with ID {callback.message.message_id}")
        except Exception as e:
            logger.warning(f"Failed to delete confirmation message: {e}")
    
    # Delete any validation messages
    if validation_msg_id:
        try:
            await callback.bot.delete_message(
                chat_id=callback.message.chat.id,
                message_id=validation_msg_id
            )
        except Exception as e:
            logger.warning(f"Failed to delete validation message: {e}")
    
    # Acknowledge with a small popup
    await callback.answer("Question cancelled")


# --- Placeholder handlers for answering --- 
async def process_answer_callback(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Handles callback when user answers a question, saves to DB, shows selected answer."""
    
    try:
        # Parse the callback data
        callback_data = callback.data
        logger.info(f"Processing answer callback: {callback_data}")
        
        # Clean up any instruction or group info messages
        data = await state.get_data()
        group_info_msg_id = data.get("group_info_msg_id")
        instructions_msg_id = data.get("instructions_msg_id")
        find_match_message_id = data.get("find_match_message_id")
        pending_match_message_id = data.get("pending_match_message_id")
        
        if group_info_msg_id:
            try:
                await callback.bot.delete_message(callback.message.chat.id, group_info_msg_id)
                await state.update_data(group_info_msg_id=None)
            except Exception as e:
                logger.warning(f"Failed to delete group info message: {e}")
        
        if instructions_msg_id:
            try:
                await callback.bot.delete_message(callback.message.chat.id, instructions_msg_id)
                await state.update_data(instructions_msg_id=None)
            except Exception as e:
                logger.warning(f"Failed to delete instructions message: {e}")
                
        if find_match_message_id:
            try:
                await callback.bot.delete_message(callback.message.chat.id, find_match_message_id)
                await state.update_data(find_match_message_id=None)
            except Exception as e:
                logger.warning(f"Failed to delete find match message: {e}")
                
        if pending_match_message_id:
            try:
                await callback.bot.delete_message(callback.message.chat.id, pending_match_message_id)
                await state.update_data(pending_match_message_id=None, has_pending_match=False)
            except Exception as e:
                logger.warning(f"Failed to delete pending match message: {e}")
        
        # Split by : to get parts
        parts = callback_data.split(":")
        if len(parts) < 3:
            logger.error(f"Invalid callback data format: {callback_data}")
            await callback.answer("Invalid callback data", show_alert=True)
            return
            
        _, question_id_str, answer_type_str = parts
        question_id = int(question_id_str)
        
        # Check if the question exists right away, before any processing
        question = await question_repo.get(session, question_id)
        if not question:
            logger.info(f"User {callback.from_user.id} tried to answer a deleted question {question_id}")
            await callback.answer("This question has been deleted.", show_alert=True)
            
            # Update the message to indicate the question is deleted
            deleted_text = "❌ This question has been deleted."
            try:
                await callback.message.edit_text(deleted_text, reply_markup=None)
                logger.info(f"Updated message to show question {question_id} was deleted")
            except Exception as e:
                logger.warning(f"Failed to update message for deleted question: {e}")
            
            return
        
        # Check if user is toggling the answer (clicked on the answer button)
        if answer_type_str == "toggle":
            logger.info(f"User {callback.from_user.id} toggling answer for question {question_id}")
            # We've already checked the question exists at the beginning of the function
                
            # Show all answer options
            full_keyboard = get_answer_keyboard_with_skip(question_id)
            
            # Add delete button if user is the author
            user_tg = callback.from_user
            db_user = await user_repo.get_by_telegram_id(session, user_tg.id)
            if db_user and question.author_id == db_user.id:
                # Add a second row with the delete button
                delete_button = [
                    types.InlineKeyboardButton(
                        text="🗑️ Delete",
                        callback_data=f"delete_question:{question.id}"
                    )
                ]
                
                # Get the current keyboard rows
                current_rows = full_keyboard.inline_keyboard
                # Add the delete button row
                current_rows.append(delete_button)
                # Create new keyboard with the additional row
                full_keyboard = types.InlineKeyboardMarkup(inline_keyboard=current_rows)
                
            await callback.message.edit_reply_markup(reply_markup=full_keyboard)
            await state.update_data(is_showing_single_answer=False)
            await callback.answer("Choose a new answer")
            return

        # Process a new answer
        telegram_user_id = callback.from_user.id
        db_user = await user_repo.get_by_telegram_id(session, telegram_user_id)
        if not db_user:
            logger.error(f"User {telegram_user_id} not found in DB for answering.")
            await callback.answer("Error: Could not find your user account.", show_alert=True)
            return
             
        logger.info(f"User {db_user.id} processing answer for question {question_id} with '{answer_type_str}'")
        
        # Get the correct answer type value
        actual_answer_type = answer_type_str
        
        answer_value = ANSWER_VALUES.get(actual_answer_type)
        if answer_value is None:
            logger.error(f"Invalid answer_type '{answer_type_str}' received for question {question_id}")
            await callback.answer("Invalid answer selected.", show_alert=True)
            return
             
        # Check if the user has already answered this question
        existing_answer = await answer_repo.get_answer(session, db_user.id, question_id)
        is_new_answer = existing_answer is None
             
        # Save the answer to the database
        try:
            saved_answer = await answer_repo.save_answer(
                session=session,
                user_id=db_user.id,
                question_id=question_id,
                answer_type=actual_answer_type,
                value=answer_value
            )
            
            # Award points only for new answers that are not skips
            if is_new_answer and actual_answer_type != "skip":
                updated_user = await user_repo.add_points(session, db_user.id, 1)
                logger.info(f"Awarded 1 point to user {db_user.id} for answering a question. New balance: {updated_user.points}💎")
                await callback.answer(f"Answer saved! +1💎 (Balance: {updated_user.points}💎)")
            else:
                await callback.answer("Answer updated! ✅")
            
            # Delete success message if this is a newly created question being answered
            user_data = await state.get_data()
            success_msg_id = user_data.get("question_added_success_msg_id")
            if success_msg_id:
                try:
                    await callback.bot.delete_message(
                        chat_id=callback.message.chat.id,
                        message_id=success_msg_id
                    )
                    logger.info(f"Deleted question success message with ID {success_msg_id}")
                    # Remove the message ID from state
                    await state.update_data(question_added_success_msg_id=None)
                except Exception as e:
                    logger.warning(f"Failed to delete question success message: {e}")
            
            # Get the question data for buttons and display
            question = await question_repo.get(session, question_id)
            if not question:
                await callback.answer("Cannot find this question anymore.", show_alert=True)
                return
                
            # Get the emoji for the selected answer
            selected_button_display_text = "Unknown"
            if actual_answer_type == "skip":
                selected_button_display_text = "⏭️"
            else:
                answer_map = {
                    "strong_no": "👎👎", 
                    "no": "👎", 
                    "yes": "👍", 
                    "strong_yes": "👍👍"
                }
                selected_button_display_text = answer_map.get(actual_answer_type, actual_answer_type)
                
            # Create keyboard buttons for answer
            keyboard_buttons = [
                types.InlineKeyboardButton(
                    text=selected_button_display_text,
                    callback_data=f"answer:{question.id}:toggle"
                )
            ]
            
            # Add delete button if user is the author
            if question.author_id == db_user.id:
                keyboard_buttons.append(
                    types.InlineKeyboardButton(
                        text="🗑️ Delete",
                        callback_data=f"delete_question:{question.id}"
                    )
                )
            
            # Create the keyboard with the appropriate buttons
            single_button_keyboard = types.InlineKeyboardMarkup(inline_keyboard=[keyboard_buttons])
            
            # Check if the message is a notification - keep question but remove the header
            if callback.message and callback.message.text and callback.message.text.startswith("<b>📝 New Question in"):
                # Extract just the question text (everything after the notification header)
                question_text = question.text
                
                # Edit the message to show only the question text with the answer button
                await callback.message.edit_text(
                    text=question_text,
                    reply_markup=single_button_keyboard
                )
                logger.info(f"Removed notification header for question {question_id} to keep chat clean")
            else:
                # Update the existing message with just the answer button
                await callback.message.edit_reply_markup(reply_markup=single_button_keyboard)
                logger.debug(f"Answer processed. Updated message with answer button for question {question_id}")
            
            # Store the message ID and question ID to handle toggling later
            await state.update_data(
                last_answered_msg_id=callback.message.message_id,
                last_answered_q_id=question_id,
                is_showing_single_answer=True
            )
            
            # Explicitly commit the session to make sure the answer is saved to the database
            # before we query for the next question
            await session.commit()
            
            # For PostgreSQL in Railway, it's important to ensure the transaction is fully completed
            # by explicitly refreshing the answer record and flushing the session
            try:
                # Flush any pending operations to ensure they're sent to the database
                await session.flush()
                
                # Refresh the saved answer to ensure it's properly synchronized
                if saved_answer:
                    await session.refresh(saved_answer)
                
                logger.info(f"Session flushed and answer refreshed for question {question_id} by user {db_user.id}")
            except Exception as e:
                logger.warning(f"Error refreshing session state: {e}")
            
            logger.info(f"Session committed after saving answer for question {question_id} by user {db_user.id}")
            
            # Remove the scheduled deletion - we want to keep answered questions visible
            # asyncio.create_task(delayed_message_deletion(callback.message, 2))
            
            # Get the next question for the user to answer using our helper function
            # Use the question's group_id directly instead of fetching from state
            group_id = question.group_id
            logger.info(f"Fetching next question for user {db_user.id} in group {group_id}")
            
            if group_id:
                # Reuse our centralized helper function to check and display the next question
                await check_and_display_next_question(callback.message, db_user, group_id, state, session)
        except Exception as e:
            logger.error(f"Error saving answer: {e}")
            await callback.answer("Error saving answer. Please try again.", show_alert=True)
                
    except ValueError as e:
        logger.error(f"Error parsing answer callback data: '{callback.data}', error: {e}")
        await callback.answer("Error processing answer.", show_alert=True)
    except Exception as e:
        logger.exception(f"Error processing answer callback '{callback.data}': {e}")
        try:
            await callback.answer("Sorry, there was an error processing your answer.", show_alert=True)
        except Exception:
            chat_id = callback.message.chat.id
            await callback.bot.send_message(chat_id, "Sorry, there was an error processing your answer.")
            logger.error("Failed to send error message to user")

async def delayed_message_deletion(message, delay_seconds=2):
    """Delete a message after a specified delay"""
    try:
        await asyncio.sleep(delay_seconds)
        await message.delete()
        logger.info(f"Deleted message {message.message_id} after {delay_seconds} seconds")
    except Exception as e:
        logger.warning(f"Failed to delete message {message.message_id}: {e}")


async def show_beta_message(message: types.Message) -> None:
    """Function removed - no longer in use."""
    # This function has been removed from active use
    pass


async def on_message_deleted(event, bot: Bot, state: FSMContext, session: AsyncSession) -> None:
    """
    NOTE: This function is currently not in use as Telegram Bot API doesn't support direct message deletion events.
    
    In the future, we could implement an alternative approach to track deleted messages, such as:
    1. Periodically checking if messages still exist
    2. Storing message IDs and timestamps, and inferring deletion
    3. Using application-specific buttons for deletion instead of relying on Telegram's deletion
    """
    logger.warning("Message deletion detection attempted...")
    logger.info("Consider implementing an alternative approach...")


# --- Add New Handlers Here ---
async def handle_start_anon_chat(query: types.CallbackQuery, state: FSMContext, bot: Bot, session: AsyncSession) -> None:
    """Handles the 'Start Anonymous Chat' button click."""
    await query.answer()
    user_id = query.from_user.id
    
    # Enhanced debug logging
    try:
        data = await state.get_data()
        
        logger.info(f"[START_ANON_CHAT] User {user_id} clicked Start Anonymous Chat button")
        logger.info(f"[START_ANON_CHAT] Callback data: {query.data}")
        logger.info(f"[START_ANON_CHAT] State data keys: {list(data.keys())}")
        
        # Dump all relevant state data for debugging
        logger.info(f"[START_ANON_CHAT] has_pending_match: {data.get('has_pending_match')}")
        logger.info(f"[START_ANON_CHAT] pending_match_user_id: {data.get('pending_match_user_id')}")
        logger.info(f"[START_ANON_CHAT] current_group_id: {data.get('current_group_id')}")
        logger.info(f"[START_ANON_CHAT] pending_match_nickname: {data.get('pending_match_nickname')}")
        logger.info(f"[START_ANON_CHAT] pending_match_photo: {data.get('pending_match_photo') is not None}")
        
        # Check if the user has a pending match
        if not data.get("has_pending_match", False):
            logger.warning(f"[START_ANON_CHAT] User {user_id} clicked start_anon_chat but has no pending match in state data.")
            await query.message.edit_text("No active match found. Please try finding a match again.")
            return
        
        matched_user_id = data.get("pending_match_user_id")
        score = data.get("pending_match_score")
        common_questions = data.get("pending_match_common_questions", 0)
        category_scores = data.get("pending_match_category_scores", {})
        category_counts = data.get("pending_match_category_counts", {})
        matched_user_nickname = data.get("pending_match_nickname")
        matched_user_photo = data.get("pending_match_photo")

        if not matched_user_id:
            logger.warning(f"[START_ANON_CHAT] User {user_id} clicked start_anon_chat but no matched_user_id found in state.")
            await query.message.edit_text("Something went wrong, match data lost. Please try finding a match again.")
            return

        logger.info(f"[START_ANON_CHAT] User {user_id} confirmed chat with {matched_user_id}")
        logger.info(f"[START_ANON_CHAT] Match details - Score: {score}, Common Questions: {common_questions}")
        logger.info(f"[START_ANON_CHAT] Match has nickname: {matched_user_nickname is not None}, has photo: {matched_user_photo is not None}")
    except Exception as e:
        import traceback
        logger.error(f"[START_ANON_CHAT] Error in initial data processing: {e}")
        logger.error(f"[START_ANON_CHAT] Traceback: {traceback.format_exc()}")
        try:
            await query.message.edit_text("An error occurred while processing your request. Please try again.")
        except Exception:
            pass
        return
    
    # Get users from database
    logger.debug(f"[START_ANON_CHAT] Getting users from database: {user_id} and {matched_user_id}")
    db_user = await user_repo.get_by_telegram_id(session, user_id)
    matched_db_user = await user_repo.get_by_telegram_id(session, matched_user_id)
    
    if not db_user or not matched_db_user:
        logger.error(f"[START_ANON_CHAT] Could not find users in database: {user_id} or {matched_user_id}")
        await query.message.edit_text("Error: Could not find user data. Please try again.")
        return
    
    logger.debug(f"[START_ANON_CHAT] Found users in DB: user={db_user.id}, matched_user={matched_db_user.id}")
    
    try:
        # Check if there's already a match between these users
        logger.debug(f"[START_ANON_CHAT] Checking for existing match between {db_user.id} and {matched_db_user.id}")
        existing_match = await get_match_between_users(session, db_user.id, matched_db_user.id)
        if not existing_match:
            # Create a new match record
            logger.debug(f"[START_ANON_CHAT] No existing match found, creating new match")
            existing_match = await create_match(
                session=session,
                user1_id=db_user.id,
                user2_id=matched_db_user.id,
                score=score,
                common_questions=common_questions
            )
            logger.debug(f"[START_ANON_CHAT] Created new match with ID {existing_match.id}")
        else:
            logger.debug(f"[START_ANON_CHAT] Using existing match with ID {existing_match.id}")
        
        # Check if there's already an active chat session
        logger.debug(f"[START_ANON_CHAT] Checking for existing chat session for match ID {existing_match.id}")
        existing_chat = await get_by_match_id(session, existing_match.id)
        
        logger.debug(f"[START_ANON_CHAT] Existing chat result: {existing_chat is not None}")
        if existing_chat:
            logger.debug(f"[START_ANON_CHAT] Existing chat status: {existing_chat.status}, ID: {existing_chat.id}, session_id: {existing_chat.session_id}")
        
        # Create a new chat session if none exists or if the existing one is not active
        if not existing_chat or existing_chat.status != "active":
            # Create a new chat session
            logger.debug(f"[START_ANON_CHAT] Creating new chat session")
            chat_session = await create_chat_session(
                session=session,
                initiator_id=db_user.id,
                recipient_id=matched_db_user.id,
                match_id=existing_match.id
            )
            # Set status to active
            logger.debug(f"[START_ANON_CHAT] Setting chat session status to active")
            await update_status(session, chat_session.id, "active")
            logger.debug(f"[START_ANON_CHAT] Created new chat session with ID {chat_session.id} and session_id {chat_session.session_id}")
        else:
            # Use existing chat session
            chat_session = existing_chat
            logger.debug(f"[START_ANON_CHAT] Using existing chat session with ID {chat_session.id} and session_id {chat_session.session_id}")
        
        # Format the cohesion score for display
        cohesion_percentage = int(score * 100)
        
        # Create message with match details and category breakdown
        match_text = (
            f"🎉 <b>Connected with your most resonating team member!</b>\n\n"
            f"<b>Cohesion Score: {cohesion_percentage}%</b>\n"
            f"You share perspectives on <b>{common_questions} questions</b>.\n\n"
        )
        
        # Add category breakdown if available
        if category_scores:
            match_text += "<b>Category Breakdown:</b>\n"
            for category, cat_score in category_scores.items():
                cat_percentage = int(cat_score * 100)  # Convert cohesion score to percentage
                question_count = category_counts.get(category, 0)
                match_text += f"• <b>{category.title()}</b>: {cat_percentage}% ({question_count} questions)\n"
            match_text += "\n"
        
        # Create deep link to communicator bot
        logger.debug(f"[START_ANON_CHAT] Creating deep link to communicator bot")
        bot_username = settings.COMMUNICATOR_BOT_USERNAME
        if not bot_username:
            logger.error("[START_ANON_CHAT] COMMUNICATOR_BOT_USERNAME is not set in environment or settings!")
            bot_username = "AllkindsCommunicatorBot"  # Fallback
            
        # Ensure session_id is valid
        session_id = getattr(chat_session, "session_id", None)
        if not session_id:
            logger.error(f"[START_ANON_CHAT] Chat session {chat_session.id} has no session_id!")
            # Generate a simple session ID as fallback
            import uuid
            session_id = str(uuid.uuid4())
            logger.debug(f"[START_ANON_CHAT] Generated fallback session_id: {session_id}")
            # Try to update the session
            chat_session.session_id = session_id
            await session.commit()
            
        deep_link = f"https://t.me/{bot_username}?start=chat_{session_id}"
        logger.debug(f"[START_ANON_CHAT] Generated deep link: {deep_link}")
        
        # Create inline button for the deeplink
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="Start Anonymous Chat", url=deep_link)]
        ])
        
        # Update the message with the deeplink
        match_text += "Click the button below to start an anonymous chat with your match. Your identity will remain hidden until you choose to reveal it."
        
        # If the original message was a photo message, edit the caption, otherwise edit text
        logger.debug(f"[START_ANON_CHAT] Updating message with deep link button")
        if query.message.photo and len(query.message.photo) > 0:
            logger.debug(f"[START_ANON_CHAT] Editing photo caption for message {query.message.message_id}")
            await query.message.edit_caption(caption=match_text, reply_markup=keyboard, parse_mode="HTML")
        else:
            logger.debug(f"[START_ANON_CHAT] Editing text for message {query.message.message_id}")
            await query.message.edit_text(match_text, reply_markup=keyboard, parse_mode="HTML")
    
        try:
            # Create notification for the matched user
            logger.debug(f"[START_ANON_CHAT] Creating notification for matched user {matched_user_id}")
            
            # Make sure we have the Telegram ID, not the database ID
            if not matched_db_user:
                logger.error(f"[START_ANON_CHAT] No matched_db_user found, cannot send notification")
                return
                
            matched_telegram_id = matched_db_user.telegram_id
            logger.info(f"[START_ANON_CHAT] Using Telegram ID {matched_telegram_id} for notification")
            
            if not matched_telegram_id:
                logger.error(f"[START_ANON_CHAT] No Telegram ID found for matched user {matched_user_id}")
                return
            
            notification_text = (
                f"🎉 <b>You have a new match with a team member!</b>\n\n"
                f"<b>Cohesion Score: {cohesion_percentage}%</b>\n"
                f"You share perspectives on <b>{common_questions} questions</b>.\n\n"
            )
            
            # Add category breakdown if available
            if category_scores:
                notification_text += "<b>Category Breakdown:</b>\n"
                for category, cat_score in category_scores.items():
                    cat_percentage = int(cat_score * 100)  # Convert cohesion score to percentage
                    question_count = category_counts.get(category, 0)
                    notification_text += f"• <b>{category.title()}</b>: {cat_percentage}% ({question_count} questions)\n"
                notification_text += "\n"
                
            notification_text += "Your match wants to chat anonymously! Click the button below to join the conversation. Your identity will remain hidden until you choose to reveal it."
            
            # Create keyboard for the matched user
            recipient_keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="Join Anonymous Chat", url=deep_link)]
            ])
            
            # Get initiator's nickname and photo if available
            logger.debug(f"[START_ANON_CHAT] Getting initiator's nickname and photo")
            try:
                initiator_nickname = None
                initiator_photo = None
                recipient_nickname = None
                
                # Get the current group
                group_id = data.get("current_group_id")
                if group_id:
                    # Get the group member record for the initiator
                    logger.debug(f"[START_ANON_CHAT] Getting group member data for user {db_user.id} in group {group_id}")
                    group_member = await group_repo.get_group_member(session, db_user.id, int(group_id))
                    if group_member:
                        initiator_nickname = getattr(group_member, "nickname", None)
                        initiator_photo = getattr(group_member, "photo_file_id", None)
                        logger.info(f"[START_ANON_CHAT] Found nickname '{initiator_nickname}' and photo '{initiator_photo}' for initiator {db_user.id}")
                    
                    # Get group member record for the recipient (matched user)
                    recipient_member = await group_repo.get_group_member(session, matched_db_user.id, int(group_id))
                    if recipient_member:
                        recipient_nickname = getattr(recipient_member, "nickname", None)
                        logger.info(f"[START_ANON_CHAT] Found nickname '{recipient_nickname}' for recipient {matched_db_user.id}")
                        
                        # Personalize the notification if recipient has a nickname
                        if recipient_nickname:
                            notification_text = notification_text.replace("You have a new match", f"Hey {recipient_nickname}, you have a new match")
            except Exception as e:
                logger.warning(f"[START_ANON_CHAT] Error retrieving nickname/photo for users: {e}")
                # Continue without nickname/photo
            
            # Add match timestamp
            notification_text += f"\n\n<i>Match created at {datetime.now().strftime('%Y-%m-%d %H:%M')}</i>"
            
            # Store the message ID to avoid duplicating notifications
            notification_key = f"match_notification_{matched_db_user.id}_{db_user.id}"
            existing_notification = data.get(notification_key)
            
            if existing_notification:
                logger.info(f"[START_ANON_CHAT] Notification already sent to user {matched_telegram_id}")
            else:
                # Send notification to the matched user including initiator's photo if available
                logger.debug(f"[START_ANON_CHAT] Sending notification to matched user Telegram ID {matched_telegram_id}")
                sent_message = None
                
                try:
                    if initiator_photo:
                        try:
                            logger.debug(f"[START_ANON_CHAT] Sending photo notification with initiator's photo")
                            sent_message = await bot.send_photo(
                                chat_id=matched_telegram_id,
                                photo=initiator_photo,
                                caption=notification_text,
                                reply_markup=recipient_keyboard,
                                parse_mode="HTML"
                            )
                        except Exception as photo_error:
                            logger.warning(f"[START_ANON_CHAT] Error sending initiator photo: {photo_error}. Falling back to text-only notification.")
                            sent_message = await bot.send_message(
                                chat_id=matched_telegram_id,
                                text=notification_text,
                                reply_markup=recipient_keyboard,
                                parse_mode="HTML"
                            )
                    else:
                        logger.debug(f"[START_ANON_CHAT] Sending text-only notification")
                        sent_message = await bot.send_message(
                            chat_id=matched_telegram_id,
                            text=notification_text,
                            reply_markup=recipient_keyboard,
                            parse_mode="HTML"
                        )
                    
                    # Store the notification ID to avoid duplicates
                    if sent_message:
                        await state.update_data({notification_key: sent_message.message_id})
                        
                    logger.info(f"[START_ANON_CHAT] Sent match notification to matched user {matched_telegram_id}")
                except Exception as e:
                    logger.error(f"[START_ANON_CHAT] Failed to send match notification to matched user {matched_telegram_id}: {e}")
                    
                    # Check if this is a "bot was blocked by the user" error
                    if "bot was blocked by the user" in str(e):
                        await query.message.reply("Cannot send a notification to your matched user. They may have blocked the bot.")
                    else:
                        await query.message.reply("Could not notify your match due to an error. They'll still be able to join the chat with the link if you share it.")
                
                # Send a confirmation to initiator that match notification was sent
                try:
                    confirmation = f"✅ Your match has been notified and invited to join the chat."
                    await query.message.reply(confirmation)
                except Exception as e:
                    logger.warning(f"[START_ANON_CHAT] Failed to send confirmation to initiator: {e}")
        except Exception as e:
            logger.error(f"[START_ANON_CHAT] Failed to send match notification to matched user {matched_user_id}: {e}")
    
        # Remove the pending match flag from state data
        logger.debug(f"[START_ANON_CHAT] Clearing pending match flag from state")
        await state.update_data(has_pending_match=False)
        logger.info(f"[START_ANON_CHAT] Successfully completed setup for user {user_id} with matched user {matched_user_id}")
    except Exception as e:
        import traceback
        logger.error(f"[START_ANON_CHAT] Error in handle_start_anon_chat: {e}")
        logger.error(f"[START_ANON_CHAT] Traceback: {traceback.format_exc()}")
        await query.message.edit_text("An error occurred while setting up the chat. Please try again later.")
        return


async def handle_cancel_match(callback: types.CallbackQuery, state: FSMContext) -> None:
    """
    Handle cancellation of a match confirmation.
    Deletes match confirmation message and updates keyboard with current balance.
    """
    # Answer callback to close loading indicator
    await callback.answer()
    
    # Get current state data
    data = await state.get_data()
    group_id = data.get("current_group_id")
    group_name = data.get("current_group_name")
    
    # Check if there's a pending match to cancel
    if not data.get("has_pending_match"):
        logger.warning(f"User {callback.from_user.id} clicked cancel but has no pending match")
        await callback.message.answer("You don't have an active match to cancel.")
        return
    
    # Get the match confirmation message ID to delete it
    match_message_id = data.get("pending_match_message_id")
    
    # Send cancellation message
    cancel_message = await callback.message.answer("Match request cancelled.")
    
    # Update state to remove pending match data
    await state.update_data(
        has_pending_match=None,
        pending_match_user_id=None,
        pending_match_score=None,
        pending_match_common_questions=None,
        pending_match_category_scores=None,
        pending_match_category_counts=None,
        pending_match_message_id=None
    )
    
    # Try to delete the match confirmation message
    if match_message_id:
        try:
            await callback.bot.delete_message(
                chat_id=callback.message.chat.id,
                message_id=match_message_id
            )
            logger.debug(f"Deleted match confirmation message {match_message_id}")
        except Exception as e:
            logger.warning(f"Failed to delete match confirmation message: {e}")
    
    # Try to delete the "Find a match" message that triggered this flow
    find_match_message_id = data.get("find_match_message_id")
    if find_match_message_id:
        try:
            await callback.bot.delete_message(
                chat_id=callback.message.chat.id,
                message_id=find_match_message_id
            )
            logger.debug(f"Deleted 'Find a match' message {find_match_message_id}")
        except Exception as e:
            logger.warning(f"Failed to delete 'Find a match' message: {e}")
    
    # We no longer delete the group menu message - we keep it visible
    
    # Delete the cancellation message after a short delay
    async def delete_cancel_message():
        await asyncio.sleep(2)
        try:
            await cancel_message.delete()
        except Exception as e:
            logger.warning(f"Failed to delete cancellation message: {e}")
        
        # Just update the state without modifying the UI
        await state.set_state(QuestionFlow.viewing_question)
        await state.update_data(current_section="questions")
    
    # Start task to delete cancellation message
    asyncio.create_task(delete_cancel_message())


async def on_add_question(message: types.Message, state: FSMContext, session: AsyncSession) -> None:
    """Handle add question button press."""
    data = await state.get_data()
    group_id = data.get("current_group_id")
    group_name = data.get("current_group_name")
    
    if not group_id or not group_name:
        logger.error(f"User {message.from_user.id} clicked Add Question but no group_id found in state.")
        await message.answer("Error: Could not determine your current group. Please go back to the main menu.")
        return
    
    # Set state to creating question
    await state.set_state(QuestionFlow.creating_question)
    
    # Show group menu with add_question section highlighted
    await show_group_menu(message, group_id, group_name, state, current_section="add_question", session=session) 
    
    # Store the original user message ID to delete later
    await state.update_data(add_question_user_msg_id=message.message_id)
    
    # Send prompt and store its message ID
    prompt_msg = await message.answer("Please ask your yes/no question:")
    await state.update_data(question_prompt_msg_id=prompt_msg.message_id)


async def on_find_match(message: types.Message, state: FSMContext, session: AsyncSession) -> None:
    """Handle the 'Find Match' button click."""
    data = await state.get_data()
    
    # Get the current group info
    group_id = data.get("current_group_id")
    group_name = data.get("current_group_name")
    
    if not group_id or not group_name:
        await message.reply("❌ Group information is missing. Please restart by clicking on the group link.")
        return
    
    # Clean up previous messages
    group_info_message_id = data.get("group_info_message_id")
    if group_info_message_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=group_info_message_id)
        except Exception as e:
            logger.warning(f"Error deleting group info message: {e}")
    
    instructions_message_id = data.get("instructions_message_id")
    if instructions_message_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=instructions_message_id)
        except Exception as e:
            logger.warning(f"Error deleting instructions message: {e}")
    
    # Retrieve the user from the database
    db_user = await user_repo.get_by_telegram_id(session, message.from_user.id)
    if not db_user:
        await message.reply("❌ Your user profile couldn't be found. Please restart by clicking /start.")
        return
    
    # Check if user has enough points (1 point required)
    if db_user.points < FIND_MATCH_COST:
        logger.info(f"User {db_user.id} tried to find match but has insufficient points ({db_user.points})")
        await message.reply(
            f"❌ You need at least {FIND_MATCH_COST} points to find a match. You currently have {db_user.points} points.\n\n"
            "To earn more points, answer more questions in your group!"
        )
        return
    
    # Check if user has answered enough questions
    answer_count = await get_answer_count(session, db_user.id, int(group_id))
    if answer_count < MIN_QUESTIONS_FOR_MATCH:
        logger.info(f"User {db_user.id} tried to find match but has only answered {answer_count} questions")
        await message.reply(
            f"❌ You need to answer at least {MIN_QUESTIONS_FOR_MATCH} questions to find a match.\n"
            f"You've currently answered {answer_count} questions."
        )
        return
    
    # Get the group from the database
    group = await group_repo.get(session, int(group_id))
    if not group:
        await message.reply("❌ Group not found. Please restart by clicking on the group link.")
        return
    
    try:
        # Find matches for the user in this group
        # Note: Only the initiating user (User A) gets charged points, not the matched user (User B)
        logger.info(f"Finding matches for user {db_user.id} in group {group_id}")
        
        # Deduct points from the initiating user
        db_user.points -= FIND_MATCH_COST
        session.add(db_user)
        await session.commit()
        logger.info(f"Deducted {FIND_MATCH_COST} points from user {db_user.id}, new balance: {db_user.points}")
        
        # Find matches
        match_results = await find_matches(session, db_user.id, int(group_id))
        
        if not match_results or len(match_results) == 0:
            # No matches found
            await message.reply(
                "😔 No matches found at this time. Please try again later when more group members have answered questions."
            )
            return
        
        # Get the top match
        matched_user_id, cohesion_score, common_questions, category_scores, category_counts = match_results[0]
        logger.info(f"Found match: user {matched_user_id} with cohesion score {cohesion_score:.2f}, {common_questions} common questions")
        
        # Get the matched user from the database
        matched_db_user = await user_repo.get(session, matched_user_id)
        if not matched_db_user:
            await message.reply("❌ An error occurred while retrieving your match information.")
            return
        
        # Format the cohesion score as a percentage
        cohesion_percentage = int(cohesion_score * 100)
        
        # Prepare the match confirmation message
        confirmation_text = (
            f"🎉 <b>We found you a match with a team member!</b>\n\n"
            f"<b>Cohesion Score: {cohesion_percentage}%</b>\n"
            f"You share perspectives on <b>{common_questions} questions</b>.\n\n"
        )
        
        # Add category breakdown if available
        if category_scores:
            confirmation_text += "<b>Category Breakdown:</b>\n"
            for category, cat_score in category_scores.items():
                cat_percentage = int(cat_score * 100)  # Convert cohesion score to percentage
                question_count = category_counts.get(category, 0)
                confirmation_text += f"• <b>{category.title()}</b>: {cat_percentage}% ({question_count} questions)\n"
            confirmation_text += "\n"
        
        # Try to get the nickname and photo for the matched user
        matched_user_nickname = None
        matched_user_photo = None
        
        try:
            # Get the group member record for the matched user
            matched_group_member = await group_repo.get_group_member(session, matched_user_id, int(group_id))
            if matched_group_member:
                matched_user_nickname = getattr(matched_group_member, "nickname", None)
                matched_user_photo = getattr(matched_group_member, "photo_file_id", None)
                logger.info(f"Found nickname '{matched_user_nickname}' and photo '{matched_user_photo}' for matched user {matched_user_id}")
                
                # Add the nickname to the confirmation text if available
                if matched_user_nickname:
                    confirmation_text = confirmation_text.replace("with a team member", f"with <b>{matched_user_nickname}</b>")
        except Exception as e:
            logger.warning(f"Error retrieving nickname/photo for matched user: {e}")
            # Continue without nickname/photo
        
        # Check if there is an existing match record
        existing_match = await get_match(session, db_user.id, matched_user_id, int(group_id))
        
        # Check if there is an existing chat session
        existing_chat = await get_chat_by_participants(
            session, db_user.id, matched_user_id, int(group_id)
        )
        
        # If no existing match or chat, create a new match record
        if not existing_match:
            match_record = Match(
                user1_id=db_user.id,
                user2_id=matched_user_id,
                group_id=int(group_id),
                score=cohesion_score,
                common_questions=common_questions,
                created_at=datetime.now()
            )
            session.add(match_record)
            await session.commit()
            logger.info(f"Created new match record for users {db_user.id} and {matched_user_id} in group {group_id}")
        
        # Create keyboard with the Start Chat button
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(
                text="🗣 Start Anonymous Chat",
                callback_data=f"start_anon_chat:{matched_user_id}"
            )],
            [types.InlineKeyboardButton(
                text="❌ Cancel",
                callback_data="cancel_match"
            )]
        ])
        
        # Add notice about points being deducted
        confirmation_text += f"👉 <b>{FIND_MATCH_COST} points</b> have been deducted from your account for this match.\n\n"
        confirmation_text += "Click the button below to start an anonymous chat with your match. Your identity will remain hidden until you choose to reveal it."
        
        # Send the message with the matched user's photo if available
        if matched_user_photo:
            try:
                await message.answer_photo(
                    photo=matched_user_photo,
                    caption=confirmation_text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.warning(f"Error sending matched user photo: {e}")
                # Fall back to text-only message
                await message.answer(
                    text=confirmation_text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
        else:
            # Send text-only message if no photo is available
            await message.answer(
                text=confirmation_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        
        # Update state to include the matched user ID
        await state.update_data({
            "matched_user_id": matched_user_id,
            "cohesion_score": cohesion_score,
            "common_questions": common_questions,
            "category_scores": category_scores,
            "category_counts": category_counts
        })
        
        logger.info(f"Match confirmation sent to user {db_user.id} for match with user {matched_user_id}")
        
    except Exception as e:
        logger.error(f"Error in on_find_match: {e}")
        await message.reply("❌ An error occurred while finding a match. Please try again.")
        
        # If we failed after deducting points, refund them
        try:
            db_user.points += FIND_MATCH_COST
            session.add(db_user)
            await session.commit()
            logger.info(f"Refunded {FIND_MATCH_COST} points to user {db_user.id} due to error, new balance: {db_user.points}")
        except Exception as refund_error:
            logger.error(f"Failed to refund points to user {db_user.id}: {refund_error}")


async def on_show_start_menu(message: types.Message, state: FSMContext) -> None:
    """Handle Main Menu button click."""
    # Clear the current group from state
    await state.update_data(current_group_id=None, current_group_name=None)
    
    # Reset the state
    await state.clear()
    
    # Show the welcome menu
    await show_welcome_menu(message)


async def on_add_question_callback(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession = None) -> None:
    """Handle add question button from group menu."""
    logger.info(f"User {callback.from_user.id} clicked Add Question button")
    
    try:
        # Extract current group info from state
        data = await state.get_data()
        group_id = data.get("current_group_id")
        group_name = data.get("current_group_name")
        
        if not group_id:
            await callback.answer("No group selected", show_alert=True)
            return
            
        # Tell user we're processing
        await callback.answer("Starting question creation...")
        
        # First respond to the callback to avoid timeouts
        prompt_text = "Please enter your yes/no question below:"
        await callback.message.answer(prompt_text)
        
        # Set state for the next message
        await state.set_state(QuestionFlow.creating_question)
        
        logger.info(f"User {callback.from_user.id} set to state {QuestionFlow.creating_question} for adding question to group {group_id}")
    except Exception as e:
        logger.error(f"Error processing add_question callback: {e}")
        await callback.answer("Error starting question creation", show_alert=True)


async def on_show_questions_callback(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Handle show questions callback button."""
    await callback.answer()
    
    data = await state.get_data()
    group_id = data.get("current_group_id")
    
    if not group_id:
        await callback.message.answer("Error: Could not determine your current group.")
        return
    
    # Get user from DB
    user_tg = callback.from_user
    db_user = await user_repo.get_by_telegram_id(session, user_tg.id)
    if not db_user:
        logger.error(f"User {user_tg.id} not found in DB when showing questions")
        await callback.message.answer("Error: Could not find your user account. Please try /start again.")
        return
    
    # Use the message from the callback
    await on_show_questions(callback.message, state, session)


async def on_find_match_callback(
    callback: types.CallbackQuery, state: FSMContext, session: AsyncSession = None
) -> None:
    """Handle find match button from menu."""
    logger.info(f"User {callback.from_user.id} clicked Find Match button with data '{callback.data}'")
    
    try:
        # Get user data from state
        data = await state.get_data()
        group_id = data.get("current_group_id")
        
        if not group_id:
            await callback.answer("Please select a group first", show_alert=True)
            return
        
        # Get user from DB using callback sender's info
        if not session:
            await callback.answer("Database connection unavailable", show_alert=True)
            return
        
        # Acknowledge the callback
        await callback.answer("Finding matches...")
        
        # Get current user
        user_data = {
            "id": callback.from_user.id,
            "first_name": callback.from_user.first_name,
            "last_name": callback.from_user.last_name,
            "username": callback.from_user.username
        }
        db_user, _ = await user_repo.get_or_create_user(session, user_data)
        
        # Delegate to the message handler implementation
        await on_find_match(callback.message, state, session)
    except Exception as e:
        logger.error(f"Error in find_match callback: {e}")
        await callback.answer("Error finding matches", show_alert=True)


async def on_show_start_menu_callback(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Handle show start menu callback button."""
    await callback.answer()
    
    # Clear the current group from state
    await state.update_data(current_group_id=None, current_group_name=None)
    
    # Reset the state
    await state.clear()
    
    # Show the welcome menu
    await show_welcome_menu(callback.message)


async def cmd_cancel(message: types.Message, state: FSMContext) -> None:
    """Handle /cancel command to cancel current action and return to viewing questions."""
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Nothing to cancel.")
        return
    
    logger.info(f"User {message.from_user.id} cancelling action from state {current_state}")
    
    # Get data before clearing state
    data = await state.get_data()
    group_id = data.get("current_group_id")
    group_name = data.get("current_group_name")
    
    # Clear state
    await state.clear()
    
    # If user was in a group, return to viewing questions
    if group_id and group_name:
        await state.update_data(current_group_id=group_id, current_group_name=group_name)
        await state.set_state(QuestionFlow.viewing_question)
        await message.answer(f"Action cancelled. Returning to {group_name}.")
        await show_group_menu(message, group_id, group_name, state, session=session)
    else:
        # User wasn't in a group, show welcome menu
        await show_welcome_menu(message)


def register_handlers(dp: Dispatcher) -> None:
    """Register all handlers for the bot."""
    # Basic commands
    dp.message.register(cmd_start, Command("start"))
    dp.message.register(cmd_clear_profile, Command("clear_profile"))
    dp.message.register(cmd_cancel, Command("cancel"))
    
    # Question flow
    dp.message.register(on_show_questions, Command("show_questions"))
    dp.callback_query.register(process_answer_callback, F.data.startswith("answer:"))
    dp.callback_query.register(on_skip_question, F.data.startswith("skip_question"))
    dp.callback_query.register(on_delete_question, F.data.startswith("delete_question"))
    dp.callback_query.register(on_confirm_delete_question, F.data.startswith("confirm_delete_question"))
    dp.callback_query.register(on_cancel_delete_question, F.data.startswith("cancel_delete_question"))
    
    # Add Question
    dp.message.register(on_add_question, Command("add_question"))
    dp.message.register(process_new_question_text, QuestionFlow.creating_question)
    dp.message.register(process_new_question_text, QuestionFlow.reviewing_question)
    dp.callback_query.register(on_confirm_add_question, F.data.startswith("confirm_add_question"))
    dp.callback_query.register(on_cancel_add_question, F.data.startswith("cancel_add_question"))
    dp.callback_query.register(on_use_corrected_text, F.data.startswith("use_corrected_text"))
    dp.callback_query.register(on_use_original_text, F.data.startswith("use_original_text"))
    
    # Add handlers for reply keyboard buttons
    dp.message.register(handle_find_match_message, F.text == "Find Match")
    dp.message.register(handle_group_info_message, F.text == "Group Info")
    dp.message.register(handle_instructions_message, F.text == "Instructions")
    dp.message.register(handle_add_question_message, F.text == "Add Question")
    
    # Register the callback handlers for inline keyboard buttons
    dp.callback_query.register(on_add_question_callback, F.data == "add_question")
    dp.callback_query.register(on_find_match_callback, F.data == "find_match")
    dp.callback_query.register(on_show_questions_callback, F.data == "show_questions")
    
    # Answered Questions
    dp.callback_query.register(on_load_answered_questions, F.data.startswith("load_answered_questions"))
    
    # Delete Question
    dp.callback_query.register(on_delete_question_callback, F.data.startswith("delete_question_callback"))
    
    # Create Team
    dp.callback_query.register(on_create_team, F.data == "create_team")
    dp.message.register(process_team_name, TeamCreation.waiting_for_name)
    dp.message.register(process_team_description, TeamCreation.waiting_for_description)
    # Add state filter as positional argument (Aiogram v3 style)
    dp.callback_query.register(on_team_confirm, F.data == "confirm_team", TeamCreation.confirm_creation)
    dp.callback_query.register(on_team_cancel, F.data == "team_cancel")
    
    # Join Team
    # Use explicit filter to ensure it catches the exact callback data 'join_team'
    dp.callback_query.register(on_join_team, lambda c: c.data == 'join_team')
    # Add backup registration with normal filter 
    dp.callback_query.register(on_join_team, F.data == "join_team")
    dp.message.register(process_join_code, TeamJoining.waiting_for_code)
    dp.callback_query.register(on_join_confirm, F.data == "join_confirm")
    dp.callback_query.register(on_cancel_join, F.data == "join_cancel")
    
    # Group Onboarding
    logger.info("Registering group onboarding handlers")
    dp.message.register(process_group_nickname, GroupOnboarding.waiting_for_nickname)
    dp.message.register(process_group_photo, GroupOnboarding.waiting_for_photo)
    dp.message.register(handle_invalid_photo_input, ~F.photo & ~F.text.startswith("/skip"), GroupOnboarding.waiting_for_photo)
    
    # Group Menu - Additional variant registrations to handle potential inconsistencies
    dp.callback_query.register(on_show_start_menu_callback, F.data == "show_start_menu")
    dp.callback_query.register(on_show_questions_callback, F.data == "show_questions")
    dp.callback_query.register(on_add_question_callback, F.data == "add_question")
    
    # Enhanced registration for find_match
    dp.callback_query.register(on_find_match_callback, F.data == "find_match")
    # Also register with exact string matching for robustness
    dp.callback_query.register(on_find_match_callback, lambda c: c.data == "find_match")
    
    # Fix for join_group button - handle both the plain and parameterized versions
    dp.callback_query.register(on_join_group_callback, F.data.startswith("join_group:"))
    dp.callback_query.register(on_join_group_callback, F.data == "join_group")
    
    # Ensure go_to_group is registered with high priority
    logger.info("Registering go_to_group handler")
    dp.callback_query.register(on_go_to_group, F.data.startswith("go_to_group:"))
    
    # Chat handlers
    dp.callback_query.register(on_start_anon_chat, F.data.startswith("start_anon_chat:"))
    dp.callback_query.register(handle_cancel_match, F.data == "cancel_match")
    
    # Group Management - log each handler registration
    logger.info("Registering leave_group handler")
    dp.callback_query.register(on_leave_group_callback, F.data.startswith("leave_group:"))
    
    logger.info("Registering confirm_leave handler")
    dp.callback_query.register(on_confirm_leave_group, F.data.startswith("confirm_leave:"))
    
    logger.info("Registering cancel_leave handler")
    # Updated to provide session parameter to on_cancel_leave_group handler
    logger.info("Registering on_cancel_leave_group with session parameter")
    dp.callback_query.register(on_cancel_leave_group, F.data == "cancel_leave")
    
    logger.info("Registering manage_group handler")
    dp.callback_query.register(on_manage_group_callback, F.data.startswith("manage_group:"))
    
    logger.info("Registering group_rename handler")
    dp.callback_query.register(on_group_rename, F.data.startswith("group_rename:"))
    
    logger.info("Registering group_edit_description handler")
    dp.callback_query.register(on_group_edit_description, F.data.startswith("group_edit_desc:"))
    
    logger.info("Registering group_delete handler")
    dp.callback_query.register(on_group_delete, F.data.startswith("group_delete:"))
    
    logger.info("Registering confirm_group_delete handler")
    dp.callback_query.register(on_confirm_group_delete, F.data.startswith("confirm_group_delete:"))
    
    # Message handlers for group management
    dp.message.register(process_group_rename, GroupFlow.waiting_for_rename)
    dp.message.register(process_group_description_edit, GroupFlow.waiting_for_description_edit)
    
    # Debugging catch-all - register this LAST to catch any unhandled callbacks
    dp.callback_query.register(debug_callback)
    
    # Direct question entry - recognize messages that end with ? and are in a group context
    dp.message.register(handle_direct_question_entry, lambda m: m.text and m.text.strip().endswith("?"))
    
    # Also allow direct question entry when in the viewing_question state (to match previous behavior)
    dp.message.register(handle_direct_question_entry, F.text, QuestionFlow.viewing_question)
    
    # Catch-all for text messages (register last for text handlers)
    # Only enable in development mode
    is_dev = not os.environ.get("RAILWAY_ENVIRONMENT")
    if is_dev:
        dp.message.register(echo_debug_handler, F.text)


async def on_start_anon_chat(callback_query: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Handle the 'Start Anonymous Chat' button click."""
    try:
        # Extract matched user ID from the callback data
        match = re.match(r"start_anon_chat:(\d+)", callback_query.data)
        if not match:
            await callback_query.answer("Invalid match data", show_alert=True)
            return

        # Parse the matched user ID (this is the database ID, not Telegram ID)
        matched_user_id = int(match.group(1))
        logger.info(f"User {callback_query.from_user.id} starting anonymous chat with user {matched_user_id}")

        # Get the current user from database
        db_user = await user_repo.get_by_telegram_id(session, callback_query.from_user.id)
        if not db_user:
            logger.error(f"Current user with Telegram ID {callback_query.from_user.id} not found in database")
            await callback_query.answer("Your user profile couldn't be found", show_alert=True)
            return

        # Get the matched user from database
        matched_db_user = await user_repo.get(session, matched_user_id)
        if not matched_db_user:
            logger.error(f"Matched user {matched_user_id} not found in database")
            await callback_query.answer("The matched user couldn't be found", show_alert=True)
            return

        # Get matched user's Telegram ID
        matched_telegram_id = matched_db_user.telegram_id
        if not matched_telegram_id:
            logger.error(f"Matched user {matched_user_id} doesn't have a Telegram ID")
            await callback_query.answer("Cannot start chat: matched user has no Telegram ID", show_alert=True)
            return

        logger.info(f"Found matched user with Telegram ID {matched_telegram_id}")

        # Get data from state
        data = await state.get_data()
        logger.info(f"State data: {data}")
        
        group_id = data.get("current_group_id")
        
        # If data from state is missing, try to extract it
        if not group_id:
            logger.warning("Group ID missing from state, checking message context")
            
            # Try to get the current group ID from the message if possible
            if hasattr(callback_query, 'message') and callback_query.message:
                # Look for group ID in the message text if possible
                msg_text = callback_query.message.text or callback_query.message.caption or ""
                group_match = re.search(r"group_id:(\d+)", msg_text)
                if group_match:
                    group_id = int(group_match.group(1))
                    logger.info(f"Extracted group_id {group_id} from message text")
            
            if not group_id:
                logger.error("Could not determine group ID")
                await callback_query.answer("Group information is missing", show_alert=True)
                return

        logger.info(f"Using group_id: {group_id}")

        # Check if a chat session already exists
        existing_chat = await get_chat_by_participants(
            session, db_user.id, matched_user_id, int(group_id)
        )

        # Create new chat session if none exists
        if not existing_chat:
            chat_session = Chat(
                initiator_id=db_user.id,
                recipient_id=matched_user_id,
                group_id=int(group_id),
                status="active",
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            session.add(chat_session)
            await session.commit()
            chat_id = chat_session.id
            logger.info(f"Created new chat session {chat_id} between users {db_user.id} and {matched_user_id}")
        else:
            chat_id = existing_chat.id
            logger.info(f"Using existing chat session {chat_id} between users {db_user.id} and {matched_user_id}")

        # Generate a deep link to the communicator bot
        communicator_bot_username = settings.COMMUNICATOR_BOT_USERNAME
        deep_link = f"https://t.me/{communicator_bot_username}?start=chat_{chat_id}"

        # Send confirmation to the initiating user (User A)
        confirmation_text = f"✅ Chat session created! Click the button below to start chatting anonymously."
        confirmation_markup = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="Open Chat", url=deep_link)]
        ])
        
        try:
            # Check if the message is a photo message or text message
            if callback_query.message.photo:
                # For photo messages, edit the caption
                await callback_query.message.edit_caption(
                    caption=confirmation_text,
                    reply_markup=confirmation_markup,
                    parse_mode="HTML"
                )
            else:
                # For text messages, edit the text
                await callback_query.message.edit_text(
                    text=confirmation_text,
                    reply_markup=confirmation_markup,
                    parse_mode="HTML"
                )
            
            logger.info(f"Successfully edited message to show chat link for user {db_user.id}")
        except Exception as e:
            logger.error(f"Error editing message: {e}")
            # If editing fails, send a new message
            try:
                await callback_query.message.answer(
                    text=confirmation_text,
                    reply_markup=confirmation_markup,
                    parse_mode="HTML"
                )
                logger.info(f"Sent new message with chat link for user {db_user.id}")
            except Exception as e2:
                logger.error(f"Failed to send new message: {e2}")
                await callback_query.answer("Error starting chat. Please try again.", show_alert=True)
    except Exception as e:
        logger.error(f"Unexpected error in on_start_anon_chat: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        await callback_query.answer("An error occurred. Please try again later.", show_alert=True)


async def cmd_diagnostics(message: types.Message) -> None:
    """Special diagnostic command for Railway."""
    # Only available for admin users and only in Railway
    user_id = message.from_user.id
    admin_ids_str = os.environ.get("ADMIN_IDS", "")
    admin_ids = [int(id_str.strip()) for id_str in admin_ids_str.split(',') if id_str.strip()]
    
    if not IS_RAILWAY:
        await message.answer("This command is only available in Railway deployment.")
        return
        
    if user_id not in admin_ids:
        await message.answer("This command is only available for admin users.")
        return
        
    # Get the diagnostic report
    report = get_diagnostics_report()
    
    # Send the report
    await message.answer(f"Railway Diagnostics Report:\n\n```\n{report}\n```", parse_mode="MarkdownV2")


async def handle_invalid_photo_input(message: types.Message, state: FSMContext) -> None:
    """Handle invalid input when a photo is expected."""
    logger.warning(f"Invalid input during photo upload: User {message.from_user.id}, Content type: {message.content_type}")
    
    try:
        current_state = await state.get_state()
        logger.warning(f"Current state: {current_state}")
        
        # Only respond if we're actually in the waiting_for_photo state
        if current_state == GroupOnboarding.waiting_for_photo.state:
            logger.info("Sending help message for photo upload")
            await message.answer("Please send a photo for your profile, or type /skip to use the default avatar.")
        else:
            logger.warning(f"Received invalid photo input but not in photo state, current state: {current_state}")
    except Exception as e:
        logger.exception(f"Error handling invalid photo input: {e}")
        # Don't send error message here to avoid confusion if this handler was triggered incorrectly


async def delete_user_answers_in_group(session: AsyncSession, user_id: int, group_id: int) -> int:
    """Delete all answers for a user in a specific group.
    
    Returns the number of answers deleted.
    """
    from sqlalchemy import delete, select
    
    # First, get all question IDs for this group
    questions_query = select(Question.id).where(Question.group_id == group_id)
    result = await session.execute(questions_query)
    question_ids = result.scalars().all()
    
    if not question_ids:
        return 0
    
    # Delete all answers for these questions
    delete_stmt = delete(Answer).where(
        Answer.user_id == user_id,
        Answer.question_id.in_(question_ids)
    )
    result = await session.execute(delete_stmt)
    return result.rowcount


async def on_go_to_group(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Handle go to group button click."""
    logger.info(f"Entering on_go_to_group handler for user {callback.from_user.id}")
    
    try:
        await callback.answer()
        
        # Extract group ID from callback data
        try:
            callback_data = callback.data
            parts = callback_data.split(":")
            if len(parts) < 2:
                logger.error(f"Invalid callback data format: {callback_data}")
                await callback.message.answer("Error: Invalid callback data format. Please try again.")
                return
                
            group_id = int(parts[1])
            logger.info(f"Extracted group_id={group_id} from callback data")
        except (ValueError, IndexError) as e:
            logger.error(f"Error parsing callback data '{callback.data}': {e}")
            await callback.message.answer("Error: Invalid team ID. Please try again.")
            return
        
        # Get group details
        try:
            group = await group_repo.get(session, group_id)
            if not group:
                logger.error(f"Group with ID {group_id} not found in database")
                await callback.message.answer("Error: Team not found. Please try again.")
                return
            
            logger.info(f"Found group: id={group.id}, name={group.name}, creator_id={group.creator_id}")
        except Exception as e:
            logger.exception(f"Error retrieving group with ID {group_id}: {e}")
            await callback.message.answer("Error retrieving team details. Please try again.")
            return
        
        # Get user data
        user_tg = callback.from_user
        db_user = await user_repo.get_by_telegram_id(session, user_tg.id)
        if not db_user:
            logger.error(f"User with Telegram ID {user_tg.id} not found in database")
            await callback.message.answer("Error: Your user account was not found. Please try /start again.")
            return
        
        logger.info(f"Found user: id={db_user.id}, telegram_id={user_tg.id}")
            
        # Check if user is a member of this group
        is_member = await group_repo.is_user_in_group(session, db_user.id, group_id)
        if not is_member:
            logger.warning(f"User {db_user.id} is not a member of group {group_id}, adding them...")
            try:
                # Determine if they should be a creator or regular member
                role = MemberRole.MEMBER
                if group.creator_id == db_user.id:
                    role = MemberRole.CREATOR
                    logger.info(f"User {db_user.id} is the creator of group {group_id}, assigning CREATOR role")
                
                # Add them to the group
                await group_repo.add_user_to_group(session, db_user.id, group_id, role=role)
                logger.info(f"Added user {db_user.id} to group {group_id} with role {role}")
                await session.commit()
            except Exception as e:
                logger.exception(f"Error adding user {db_user.id} to group {group_id}: {e}")
                await callback.message.answer("Error joining the team. Please try again.")
                return
        
        # Update state with group info
        await state.update_data(current_group_id=group_id, current_group_name=group.name, current_db_user_id=db_user.id)
        await state.set_state(QuestionFlow.viewing_question)
        
        # Log the action
        logger.info(f"User {callback.from_user.id} (DB ID: {db_user.id}) clicked Go to group button for group {group_id} ({group.name})")
        
        # Edit the original message to avoid having too many messages
        try:
            success_text = f"🎉 You're now in <b>{group.name}</b>!"
            await callback.message.edit_text(success_text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error editing message: {e}")
            # If editing fails, send a new message
            await callback.message.answer(f"🎉 You're now in <b>{group.name}</b>!", parse_mode="HTML")
        
        # Show the group menu - put this in a try/except block
        try:
            await show_group_menu(callback.message, group_id, group.name, state, session=session)
        except Exception as e:
            logger.exception(f"Error showing group menu: {e}")
            await callback.message.answer("Error showing group menu. Please try again.")
            return
        
        # After showing the menu, trigger the questions view
        try:
            await on_show_questions(callback.message, state, session)
        except Exception as e:
            logger.exception(f"Error showing questions: {e}")
            await callback.message.answer("Error loading questions. Please try again.")
    except Exception as e:
        logger.exception(f"Unhandled error in on_go_to_group: {e}")
        try:
            await callback.message.answer("An unexpected error occurred. Please try /start to restart the bot.")
        except:
            pass


async def on_answer_error(callback: types.CallbackQuery, chat_id: int) -> None:
    """Handle error when answering a question."""
    await callback.answer("An error occurred while processing your answer.", show_alert=True)


async def cmd_clear_profile(message: types.Message, command: CommandObject = None, state: FSMContext = None, session: AsyncSession = None) -> None:
    """Handle /clear_profile command to clear a user's profile in the current group.
    Admin-only command that can be used like:
    /clear_profile - Clear your own profile
    /clear_profile @username - Clear profile for a specific user
    """
    # Check if user is an admin
    user_tg = message.from_user
    db_user = await user_repo.get_by_telegram_id(session, user_tg.id)
    if not db_user:
        await message.answer("Error: Could not find your user account.")
        return
    
    # Get current group ID from state
    data = await state.get_data()
    group_id = data.get("current_group_id")
    if not group_id:
        await message.answer("Error: You must be in a group to use this command.")
        return
    
    # Check if user is admin or creator in this group
    role = await group_repo.get_user_role(session, db_user.id, group_id)
    is_admin = role in [MemberRole.ADMIN, MemberRole.CREATOR]
    
    if not is_admin:
        await message.answer("Error: Only group admins can use this command.")
        return
    
    # Determine target user - self or specified username
    target_user_id = db_user.id
    target_username = None
    
    if command and command.args:
        # If username is specified, find that user
        target_username = command.args.strip()
        if target_username.startswith("@"):
            target_username = target_username[1:]  # Remove @ symbol
        
        # Find user by username
        from sqlalchemy import select
        query = select(User).where(User.username == target_username)
        result = await session.execute(query)
        target_db_user = result.scalar_one_or_none()
        
        if not target_db_user:
            await message.answer(f"Error: User @{target_username} not found.")
            return
        
        target_user_id = target_db_user.id
    
    # Check if target user is in the group
    is_member = await group_repo.is_user_in_group(session, target_user_id, group_id)
    if not is_member:
        await message.answer(f"Error: User is not a member of this group.")
        return
    
    try:
        # Clear profile data
        stmt = update(GroupMember).where(
            (GroupMember.user_id == target_user_id) & 
            (GroupMember.group_id == group_id)
        ).values(
            nickname=None,
            photo_file_id=None
        )
        await session.execute(stmt)
        await session.commit()
        
        if target_username:
            await message.answer(f"Successfully cleared profile data for @{target_username} in this group.")
        else:
            await message.answer("Successfully cleared your profile data in this group.")
        
        logger.info(f"Admin {db_user.id} cleared profile for user {target_user_id} in group {group_id}")
    except Exception as e:
        logger.error(f"Error clearing profile: {e}")
        await message.answer("Error: Failed to clear profile data.")
        await session.rollback()


async def process_group_nickname(message: types.Message, state: FSMContext, session: AsyncSession) -> None:
    """Process nickname input during group onboarding."""
    logger.info(f"Processing nickname input for user {message.from_user.id}")
    
    nickname = message.text.strip()
    if len(nickname) < 2 or len(nickname) > 32:
        logger.info(f"Nickname validation failed - length: {len(nickname)}")
        await message.answer("Nickname must be 2-32 characters. Please try again:")
        return
    
    data = await state.get_data()
    group_id = data.get("current_group_id")
    logger.info(f"Processing nickname for group {group_id}: {nickname}")
    
    # Check uniqueness in group
    members = await group_repo.get_group_members(session, group_id)
    if any(getattr(m, "nickname", None) == nickname for m in members if getattr(m, "user_id", None) != message.from_user.id):
        logger.info(f"Nickname '{nickname}' already exists in group {group_id}")
        await message.answer("This nickname is already taken in this group. Please choose another:")
        return
    
    # Nickname is valid and unique
    logger.info(f"Nickname '{nickname}' is valid for group {group_id}, proceeding to photo")
    await state.update_data(group_nickname=nickname)
    await state.set_state(GroupOnboarding.waiting_for_photo)
    await message.answer(
        "Great! Now send a photo for your group profile, or type /skip to use the default avatar."
    )


async def process_group_photo(message: types.Message, state: FSMContext, session: AsyncSession) -> None:
    """Process photo input during group onboarding."""
    logger.info(f"Processing photo input for user {message.from_user.id}")
    
    try:
        data = await state.get_data()
        group_id = data.get("current_group_id")
        nickname = data.get("group_nickname")
        
        if not group_id:
            logger.error(f"Missing group_id in state data: {data}")
            await message.answer("Error: Could not determine your current group. Please try /start again.")
            return
            
        if not nickname:
            logger.error(f"Missing nickname in state data: {data}")
            await message.answer("Error: Nickname is missing. Please try /start again.")
            return
        
        user_tg = message.from_user
        db_user = await user_repo.get_by_telegram_id(session, user_tg.id)
        if not db_user:
            logger.error(f"User with Telegram ID {user_tg.id} not found in database")
            await message.answer("Error: Your user account was not found. Please try /start again.")
            return
        
        logger.info(f"Processing photo for group {group_id}, user {user_tg.id}, nickname '{nickname}'")
        
        # Check if user is in the group
        try:
            is_member = await group_repo.is_user_in_group(session, db_user.id, group_id)
            if not is_member:
                logger.warning(f"User {db_user.id} is not in group {group_id}, attempting to add them")
                try:
                    await group_repo.add_user_to_group(session, db_user.id, group_id)
                    await session.commit()
                    logger.info(f"Successfully added user {db_user.id} to group {group_id}")
                except Exception as add_error:
                    logger.exception(f"Error adding user to group: {add_error}")
                    await message.answer("Error: Could not add you to the group. Please try /start again.")
                    return
        except Exception as check_error:
            logger.exception(f"Error checking if user is in group: {check_error}")
            # Continue anyway, we'll handle errors in the next step
        
        # Determine photo_file_id
        photo_file_id = None
        if message.photo:
            photo_file_id = message.photo[-1].file_id
            logger.info(f"Got photo with file_id: {photo_file_id}")
        elif message.text and message.text.strip().lower() == "/skip":
            logger.info(f"User skipped photo upload")
            photo_file_id = None
        else:
            logger.warning(f"Invalid photo input: {message.content_type}")
            await message.answer("Please send a photo or type /skip:")
            return
        
        # Store nickname and photo in GroupMember
        logger.info(f"Saving profile for user {db_user.id} in group {group_id}: nickname='{nickname}', has_photo={bool(photo_file_id)}")
        try:
            await group_repo.set_member_profile(session, db_user.id, group_id, nickname, photo_file_id)
            await session.commit()  # Explicitly commit to ensure the profile is saved
            logger.info(f"Profile saved successfully")
        except Exception as e:
            logger.exception(f"Error saving profile: {e}")
            
            # Try a different approach if the previous one failed
            try:
                logger.info("Attempting alternative method to update profile")
                from sqlalchemy import update
                stmt = update(GroupMember).where(
                    (GroupMember.user_id == db_user.id) & 
                    (GroupMember.group_id == group_id)
                ).values(
                    nickname=nickname,
                    photo_file_id=photo_file_id
                )
                await session.execute(stmt)
                await session.commit()
                logger.info("Alternative profile update succeeded")
            except Exception as alt_error:
                logger.exception(f"Alternative profile update also failed: {alt_error}")
                await message.answer("Error saving your profile. Please try again or contact support.")
                await session.rollback()
                return
        
        # Get group details
        try:
            group = await group_repo.get(session, group_id)
            if not group:
                logger.error(f"Group with ID {group_id} not found after setting profile")
                await message.answer("Error: Could not find your group. Please try /start again.")
                return
        except Exception as e:
            logger.exception(f"Error retrieving group {group_id}: {e}")
            await message.answer("Error retrieving group details. Please try again.")
            return
        
        # Onboarding complete, proceed to group content
        logger.info(f"Onboarding complete, proceeding to group content")
        await state.set_state(QuestionFlow.viewing_question)
        
        # Success message with welcome to the group
        welcome_text = f"🎉 You're all set! Welcome to <b>{group.name}</b>!"
        
        # Get user's points balance
        points = db_user.points if hasattr(db_user, 'points') else 0
        
        # Get the reply keyboard with points balance 
        try:
            reply_keyboard = get_group_menu_reply_keyboard(current_section="questions", balance=points)
            logger.info(f"Created reply keyboard for user with {points} points")
        except Exception as e:
            logger.exception(f"Error creating keyboard: {e}")
            # Fallback to a simple keyboard
            reply_keyboard = types.ReplyKeyboardMarkup(
                keyboard=[
                    [types.KeyboardButton(text="💬 Questions"), types.KeyboardButton(text="💞 Find Match")],
                    [types.KeyboardButton(text="➕ Add Question"), types.KeyboardButton(text="ℹ️ Group Info")],
                    [types.KeyboardButton(text="🏠 Start Menu")]
                ],
                resize_keyboard=True
            )
        
        # Send welcome message with menu buttons
        try:
            await message.answer(welcome_text, reply_markup=reply_keyboard, parse_mode="HTML")
            logger.info(f"Sent welcome message to user {user_tg.id}")
        except Exception as e:
            logger.exception(f"Error sending welcome message: {e}")
            await message.answer("Welcome to the group! Use the commands to navigate.")
            return
        
        # Get count of unanswered questions
        try:
            unanswered_count = await get_unanswered_question_count(session, db_user.id, group_id)
            logger.info(f"User has {unanswered_count} unanswered questions")
            
            # Get count of answered questions
            answers = await answer_repo.get_answers_for_user_in_group(session, db_user.id, group_id)
            answered_count = len(answers)
            logger.info(f"User has answered {answered_count} questions")
            
            # Add message about questions
            if unanswered_count > 0:
                await message.answer(f"You have {unanswered_count} questions to answer. Here's the first one:")
                # Display the first question (which won't trigger onboarding again)
                await check_and_display_next_question(message, db_user, group_id, state, session)
            else:
                await message.answer("You've answered all available questions in this group!")
        except Exception as e:
            logger.exception(f"Error getting questions count: {e}")
            await message.answer("Error getting questions. Please use the Questions button to view questions.")
    except Exception as e:
        logger.exception(f"Unhandled error in process_group_photo: {e}")
        await message.answer("An unexpected error occurred. Please try /start to restart the bot.")


async def on_delete_question_callback(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Redirect to on_delete_question function for backward compatibility."""
    await on_delete_question(callback, state, session)

async def on_leave_group_callback(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Handle when user wants to leave a group."""
    logger.info(f"Entering on_leave_group_callback for user {callback.from_user.id}")
    
    try:
        await callback.answer()
        
        # Extract group ID from callback data
        try:
            parts = callback.data.split(":")
            if len(parts) > 1:
                group_id = int(parts[1])
                logger.info(f"Extracted group_id={group_id} from callback data")
            else:
                logger.error(f"Invalid callback data format: {callback.data}")
                await callback.answer("Invalid group data", show_alert=True)
                return
        except (ValueError, IndexError) as e:
            logger.error(f"Error parsing callback data '{callback.data}': {e}")
            await callback.answer("Invalid group data format", show_alert=True)
            return
        
        # Get group details
        try:
            group = await group_repo.get(session, group_id)
            if not group:
                logger.error(f"Group with ID {group_id} not found in database")
                await callback.answer("Group not found", show_alert=True)
                return
            
            logger.info(f"Found group: id={group.id}, name={group.name}")
        except Exception as e:
            logger.exception(f"Error retrieving group with ID {group_id}: {e}")
            await callback.answer("Error retrieving group details", show_alert=True)
            return
        
        # Ask for confirmation
        confirmation_text = f"Are you sure you want to leave <b>{group.name}</b>?\n\nYour answers will remain in the group's database, but you will no longer have access to the group."
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [
                types.InlineKeyboardButton(text="✅ Yes, leave group", callback_data=f"confirm_leave:{group_id}"),
                types.InlineKeyboardButton(text="❌ No, stay", callback_data="cancel_leave"),
            ]
        ])
        
        try:
            await callback.message.edit_text(confirmation_text, reply_markup=keyboard, parse_mode="HTML")
            logger.info(f"Displayed leave confirmation for group {group_id} to user {callback.from_user.id}")
        except Exception as e:
            logger.exception(f"Error displaying leave confirmation: {e}")
            # Try to send a new message if editing fails
            try:
                await callback.message.answer(confirmation_text, reply_markup=keyboard, parse_mode="HTML")
            except Exception as inner_e:
                logger.exception(f"Error sending leave confirmation message: {inner_e}")
                await callback.answer("Error displaying leave confirmation", show_alert=True)
    except Exception as e:
        logger.exception(f"Unhandled error in on_leave_group_callback: {e}")
        try:
            await callback.answer("An unexpected error occurred", show_alert=True)
        except:
            pass

async def on_confirm_leave_group(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Handle confirmation to leave a group."""
    await callback.answer()
    
    # Extract group ID from callback data
    group_id = int(callback.data.split(":")[1])
    
    # Get group details
    group = await group_repo.get(session, group_id)
    if not group:
        await callback.answer("Group not found", show_alert=True)
        return
    
    # Get user from DB
    user_tg = callback.from_user
    db_user, _ = await user_repo.get_or_create_user(session, {
        "id": user_tg.id,
        "first_name": user_tg.first_name,
        "last_name": user_tg.last_name,
        "username": user_tg.username
    })
    
    # Check if user is in the group
    is_member = await group_repo.is_user_in_group(session, db_user.id, group_id)
    if not is_member:
        await callback.answer("You're not a member of this group", show_alert=True)
        return
    
    # Remove user from group
    try:
        # Delete the user's answers in this group while keeping their questions
        deleted_count = await delete_user_answers_in_group(session, db_user.id, group_id)
        logger.info(f"Deleted {deleted_count} answers from user {db_user.id} in group {group_id}")
        
        # Remove user from the group
        success = await group_repo.remove_user_from_group(session, db_user.id, group_id)
        if success:
            logger.info(f"User {db_user.id} left group {group_id} ({group.name})")
            
            # Clear state data related to this group
            data = await state.get_data()
            if data.get("current_group_id") == group_id:
                await state.update_data(current_group_id=None, current_group_name=None)
            
            # Show success message
            await callback.message.edit_text(f"You have successfully left <b>{group.name}</b>. Your answers have been removed, but your questions remain in the group.", parse_mode="HTML")
            
            # Show welcome menu
            await show_welcome_menu(callback.message)
        else:
            logger.error(f"Failed to remove user {db_user.id} from group {group_id}")
            await callback.answer("Error leaving the group. Please try again.", show_alert=True)
    except Exception as e:
        logger.error(f"Error removing user from group: {e}")
        await callback.answer("Error leaving the group. Please try again.", show_alert=True)

async def on_cancel_leave_group(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession = None) -> None:
    """Handle cancellation of leaving a group.
    
    This should just cancel the operation and return to the group menu,
    without making any changes to the user's group membership.
    """
    logger.info(f"User {callback.from_user.id} cancelled leaving group")
    
    try:
        await callback.answer()
        
        # Get current group from state
        data = await state.get_data()
        group_id = data.get("current_group_id")
        group_name = data.get("current_group_name", f"Group {group_id}")
        
        if not group_id:
            logger.error("No current_group_id in state data")
            await callback.message.edit_text("Action cancelled. Please try /start to reconnect.")
            return
        
        logger.info(f"User staying in group {group_id} ({group_name})")
        
        # Simply edit the message to confirm and return to group menu
        try:
            # Show stay confirmation and return to group menu
            await callback.message.edit_text(f"You'll stay in <b>{group_name}</b>.", parse_mode="HTML")
            
            # Wait a moment before showing the menu
            await asyncio.sleep(1)
            
            # Show the regular group menu - don't try to show group info
            # as that requires additional database operations that might fail
            await show_group_menu(callback.message, group_id, group_name, state)
            
        except Exception as e:
            logger.exception(f"Error returning to menu after cancelling leave: {e}")
            # Try one more time with minimal functionality
            try:
                await callback.message.answer("Action cancelled. Returning to menu...")
                await show_group_menu(callback.message, group_id, group_name, state)
            except Exception as menu_error:
                logger.exception(f"Error showing group menu: {menu_error}")
                await callback.message.answer("Please use /start to return to the main menu.")
    except Exception as e:
        logger.exception(f"Unhandled error in on_cancel_leave_group: {e}")
        await callback.message.answer("Action cancelled. Please use /start if you need to restart.")

async def on_manage_group_callback(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Handle group management actions."""
    logger.info(f"Entering on_manage_group_callback for user {callback.from_user.id}")
    logger.info(f"Callback data: {callback.data}")
    logger.info(f"Session type: {type(session)}")
    
    # Log all available callback properties for debugging
    logger.debug(f"Callback properties: id={callback.id}, chat_instance={callback.chat_instance}")
    if hasattr(callback, 'message') and callback.message:
        logger.debug(f"Callback message: id={callback.message.message_id}, chat={callback.message.chat.id}")
    
    try:
        await callback.answer()
        
        # Extract group ID from callback data
        try:
            parts = callback.data.split(":")
            if len(parts) > 1:
                group_id = int(parts[1])
                logger.info(f"Extracted group_id={group_id} from callback data")
            else:
                logger.error(f"Invalid callback data format: {callback.data}")
                await callback.message.answer("Invalid group data - please try again")
                return
        except (ValueError, IndexError) as e:
            logger.error(f"Error parsing callback data '{callback.data}': {e}")
            await callback.message.answer("Invalid group data format - please try again")
            return
        
        # Get group details
        try:
            group = await group_repo.get(session, group_id)
            if not group:
                logger.error(f"Group with ID {group_id} not found in database")
                await callback.message.answer("Group not found. Please try selecting your group again.")
                return
            
            logger.info(f"Found group: id={group.id}, name={group.name}")
        except Exception as e:
            logger.exception(f"Error retrieving group with ID {group_id}: {e}")
            await callback.message.answer("Error retrieving group details. Please try again later.")
            return
        
        # Get user from DB
        try:
            user_tg = callback.from_user
            db_user = await user_repo.get_by_telegram_id(session, user_tg.id)
            if not db_user:
                logger.error(f"User with Telegram ID {user_tg.id} not found in database")
                await callback.message.answer("Your user profile was not found. Please try /start to restart.")
                return
            
            logger.info(f"Found user: id={db_user.id}, telegram_id={user_tg.id}")
        except Exception as e:
            logger.exception(f"Error retrieving user: {e}")
            await callback.message.answer("Error retrieving user profile. Please try again later.")
            return
        
        # Check if user is a creator/admin of the group
        try:
            is_creator = await group_repo.is_group_creator(session, db_user.id, group_id)
            # Fallback check for admin role if not creator
            if not is_creator:
                role = await group_repo.get_user_role(session, db_user.id, group_id)
                is_admin = role in ["admin", "creator"]
                logger.info(f"User {db_user.id} has role {role} in group {group_id}")
                
                if not is_admin:
                    logger.warning(f"User {db_user.id} attempted to manage group {group_id} without permission")
                    await callback.message.answer("You don't have permission to manage this group.")
                    return
            
            logger.info(f"User {db_user.id} has permission to manage group {group_id}")
        except Exception as e:
            logger.exception(f"Error checking user permissions: {e}")
            await callback.message.answer("Error checking permissions. Please try again later.")
            return
        
        # Show management options
        management_text = f"<b>{group.name}</b> Management\n\nWhat would you like to do?"
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="✏️ Rename Group", callback_data=f"group_rename:{group_id}")],
            [types.InlineKeyboardButton(text="📝 Edit Description", callback_data=f"group_edit_desc:{group_id}")],
            [types.InlineKeyboardButton(text="❌ Delete Group", callback_data=f"group_delete:{group_id}")],
            [types.InlineKeyboardButton(text="🔙 Back", callback_data=f"go_to_group:{group_id}")],
        ])
        
        try:
            # Try to edit the message if possible
            if hasattr(callback, 'message') and callback.message:
                await callback.message.edit_text(management_text, reply_markup=keyboard, parse_mode="HTML")
                logger.info(f"Edited message to display management options for group {group_id}")
            else:
                # If we can't edit, send a new message
                logger.warning("Could not edit message, sending new one instead")
                await callback.bot.send_message(
                    chat_id=callback.from_user.id,
                    text=management_text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
                logger.info(f"Sent new message with management options for group {group_id}")
            
            logger.info(f"Displayed management options for group {group_id} to user {db_user.id}")
        except Exception as e:
            logger.exception(f"Error displaying management options: {e}")
            # Try sending a new message if editing failed
            try:
                await callback.bot.send_message(
                    chat_id=callback.from_user.id,
                    text=management_text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
                logger.info("Sent new message after edit failure")
            except Exception as send_error:
                logger.exception(f"Also failed to send new message: {send_error}")
                await callback.message.answer("Error displaying management options. Please try again.")
    except Exception as e:
        logger.exception(f"Unhandled error in on_manage_group_callback: {e}")
        try:
            await callback.message.answer("An unexpected error occurred. Please try again later.")
        except:
            pass


async def on_group_rename(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Handle group rename request."""
    await callback.answer()
    
    # Extract group ID from callback data
    group_id = int(callback.data.split(":")[1])
    
    # Get group details
    group = await group_repo.get(session, group_id)
    if not group:
        await callback.answer("Group not found", show_alert=True)
        return
    
    # Update state and ask for new name
    await state.update_data(edit_group_id=group_id, edit_group_name=group.name)
    await state.set_state(GroupFlow.waiting_for_rename)
    
    # Send instructions
    await callback.message.edit_text(
        f"Please enter a new name for <b>{group.name}</b>:",
        parse_mode="HTML"
    )


async def on_group_edit_description(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Handle group description edit request."""
    await callback.answer()
    
    # Extract group ID from callback data
    group_id = int(callback.data.split(":")[1])
    
    # Get group details
    group = await group_repo.get(session, group_id)
    if not group:
        await callback.answer("Group not found", show_alert=True)
        return
    
    # Update state and ask for new description
    await state.update_data(edit_group_id=group_id, edit_group_name=group.name)
    await state.set_state(GroupFlow.waiting_for_description_edit)
    
    # Show current description and send instructions
    current_desc = group.description or "No description"
    await callback.message.edit_text(
        f"Current description of <b>{group.name}</b>:\n\n{current_desc}\n\nPlease enter a new description:",
        parse_mode="HTML"
    )


async def on_group_delete(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Handle group delete request."""
    await callback.answer()
    
    # Extract group ID from callback data
    group_id = int(callback.data.split(":")[1])
    
    # Get group details
    group = await group_repo.get(session, group_id)
    if not group:
        await callback.answer("Group not found", show_alert=True)
        return
    
    # Ask for confirmation
    confirmation_text = f"⚠️ <b>WARNING</b> ⚠️\n\nAre you ABSOLUTELY sure you want to delete the group <b>{group.name}</b>?\n\nThis will remove ALL data associated with this group, including questions and answers. This action CANNOT be undone."
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="❌ NO, Cancel", callback_data=f"go_to_group:{group_id}"),
            types.InlineKeyboardButton(text="⚠️ YES, Delete", callback_data=f"confirm_group_delete:{group_id}"),
        ]
    ])
    
    await callback.message.edit_text(confirmation_text, reply_markup=keyboard, parse_mode="HTML")


async def on_confirm_group_delete(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Handle confirmation of group deletion."""
    await callback.answer()
    
    # Extract group ID from callback data
    group_id = int(callback.data.split(":")[1])
    
    # Get group details
    group = await group_repo.get(session, group_id)
    if not group:
        await callback.answer("Group already deleted", show_alert=True)
        return
    
    # Get user from DB
    user_tg = callback.from_user
    db_user, _ = await user_repo.get_or_create_user(session, {
        "id": user_tg.id,
        "first_name": user_tg.first_name,
        "last_name": user_tg.last_name,
        "username": user_tg.username
    })
    
    # Check if user is the creator
    is_creator = await group_repo.is_group_creator(session, db_user.id, group_id)
    if not is_creator:
        await callback.answer("Only the group creator can delete the group", show_alert=True)
        return
    
    # Attempt to delete the group
    try:
        # For now, just mark the group as inactive
        from sqlalchemy import update 
        from src.db.models.group import Group
        stmt = update(Group).where(Group.id == group_id).values(is_active=False)
        await session.execute(stmt)
        await session.commit()
        
        # Add more detailed logging for debugging
        logger.info(f"Group {group_id} ({group.name}) marked as inactive (soft deleted) by user {db_user.id}")
        logger.info(f"Group object before soft deletion: is_active={group.is_active}")
        
        # Re-fetch the group to verify changes
        updated_group = await group_repo.get(session, group_id)
        if updated_group:
            logger.info(f"Group after soft deletion: is_active={updated_group.is_active}")
        else:
            logger.error(f"Failed to re-fetch group {group_id} after marking inactive")
        
        # Clear state data related to this group
        data = await state.get_data()
        if data.get("current_group_id") == group_id:
            await state.update_data(current_group_id=None, current_group_name=None)
            logger.info(f"Cleared group {group_id} from user state")
        
        # Show success message
        await callback.message.edit_text(f"Group <b>{group.name}</b> has been deleted.", parse_mode="HTML")
        
        # Show welcome menu
        await show_welcome_menu(callback.message)
    except Exception as e:
        logger.error(f"Error deleting group: {e}")
        await callback.answer("Error deleting the group. Please try again.", show_alert=True)
        await session.rollback()


async def process_group_rename(message: types.Message, state: FSMContext, session: AsyncSession) -> None:
    """Process the new name for a group after the rename request."""
    new_name = message.text.strip()
    
    # Basic validation
    if len(new_name) < 3:
        await message.answer("Name is too short. Please enter a name with at least 3 characters.")
        return
    
    if len(new_name) > 50:
        await message.answer("Name is too long. Please enter a name with at most 50 characters.")
        return
    
    # Get group ID from state
    data = await state.get_data()
    group_id = data.get("edit_group_id")
    old_name = data.get("edit_group_name")
    
    if not group_id:
        await message.answer("Error: Group ID not found. Please try again.")
        await state.clear()
        return
    
    # Get user from DB
    user_tg = message.from_user
    db_user, _ = await user_repo.get_or_create_user(session, {
        "id": user_tg.id,
        "first_name": user_tg.first_name,
        "last_name": user_tg.last_name,
        "username": user_tg.username
    })
    
    # Check if user is the creator
    is_creator = await group_repo.is_group_creator(session, db_user.id, group_id)
    if not is_creator:
        await message.answer("Only the group creator can rename the group.")
        await state.clear()
        return
    
    # Update the group name
    try:
        from sqlalchemy import update 
        from src.db.models.group import Group
        stmt = update(Group).where(Group.id == group_id).values(name=new_name)
        await session.execute(stmt)
        await session.commit()
        
        logger.info(f"Group {group_id} renamed from '{old_name}' to '{new_name}' by user {db_user.id}")
        
        # Update state with new name
        await state.update_data(current_group_name=new_name)
        
        # Clear edit state
        await state.set_state(QuestionFlow.viewing_question)
        
        # Show success message
        await message.answer(f"Group successfully renamed from <b>{old_name}</b> to <b>{new_name}</b>.", parse_mode="HTML")
        
        # Show group menu with updated name
        await show_group_menu(message, group_id, new_name, state, session=session)
    except Exception as e:
        logger.error(f"Error renaming group: {e}")
        await message.answer("Error renaming the group. Please try again.")
        await session.rollback()


async def process_group_description_edit(message: types.Message, state: FSMContext, session: AsyncSession) -> None:
    """Process the new description for a group after the edit description request."""
    new_description = message.text.strip()
    
    # Basic validation
    if len(new_description) > 500:
        await message.answer("Description is too long. Please enter a description with at most 500 characters.")
        return
    
    # Get group ID from state
    data = await state.get_data()
    group_id = data.get("edit_group_id")
    group_name = data.get("edit_group_name")
    
    if not group_id:
        await message.answer("Error: Group ID not found. Please try again.")
        await state.clear()
        return
    
    # Get user from DB
    user_tg = message.from_user
    db_user, _ = await user_repo.get_or_create_user(session, {
        "id": user_tg.id,
        "first_name": user_tg.first_name,
        "last_name": user_tg.last_name,
        "username": user_tg.username
    })
    
    # Check if user is the creator
    is_creator = await group_repo.is_group_creator(session, db_user.id, group_id)
    if not is_creator:
        await message.answer("Only the group creator can edit the group description.")
        await state.clear()
        return
    
    # Update the group description
    try:
        from sqlalchemy import update 
        from src.db.models.group import Group
        stmt = update(Group).where(Group.id == group_id).values(description=new_description)
        await session.execute(stmt)
        await session.commit()
        
        logger.info(f"Description of group {group_id} ({group_name}) updated by user {db_user.id}")
        
        # Clear edit state
        await state.set_state(QuestionFlow.viewing_question)
        
        # Show success message
        await message.answer(f"Description of <b>{group_name}</b> has been updated.", parse_mode="HTML")
        
        # Show group menu
        await show_group_menu(message, group_id, group_name, state, session=session)
    except Exception as e:
        logger.error(f"Error updating group description: {e}")
        await message.answer("Error updating the group description. Please try again.")
        await session.rollback()


async def on_use_corrected_text(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Handle when the user chooses to use the corrected text."""
    user_data = await state.get_data()
    corrected_text = user_data.get("corrected_question_text", "")
    correction_msg_id = user_data.get("correction_msg_id")
    
    # Update the state with corrected text as the new question text
    await state.update_data(new_question_text=corrected_text)
    
    # Delete the correction message
    if correction_msg_id:
        try:
            await callback.bot.delete_message(
                chat_id=callback.message.chat.id,
                message_id=correction_msg_id
            )
        except Exception as e:
            logger.warning(f"Failed to delete correction message: {e}")
    
    # Show confirmation with the corrected text
    confirmation_text = f"Your question:\n\n{corrected_text}\n\nIs this correct and ready to be added?"
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="✅ Yes", callback_data="confirm_add_question"),
            types.InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_add_question"),
        ]
    ])
    confirmation_message = await callback.message.answer(confirmation_text, reply_markup=keyboard)
    await state.update_data(confirmation_message_id=confirmation_message.message_id)
    await state.set_state(QuestionFlow.reviewing_question)


async def on_use_original_text(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Handle when the user chooses to use the original text."""
    user_data = await state.get_data()
    original_text = user_data.get("original_question_text", "")
    correction_msg_id = user_data.get("correction_msg_id")
    
    # Update the state with original text as the new question text
    await state.update_data(new_question_text=original_text)
    
    # Delete the correction message
    if correction_msg_id:
        try:
            await callback.bot.delete_message(
                chat_id=callback.message.chat.id,
                message_id=correction_msg_id
            )
        except Exception as e:
            logger.warning(f"Failed to delete correction message: {e}")
    
    # Show confirmation with the original text
    confirmation_text = f"Your question:\n\n{original_text}\n\nIs this correct and ready to be added?"
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="✅ Yes", callback_data="confirm_add_question"),
            types.InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_add_question"),
        ]
    ])
    confirmation_message = await callback.message.answer(confirmation_text, reply_markup=keyboard)
    await state.update_data(confirmation_message_id=confirmation_message.message_id)
    await state.set_state(QuestionFlow.reviewing_question)


async def handle_instructions_message(message: types.Message, state: FSMContext, session: AsyncSession = None) -> None:
    """Handle the 'Instructions' button from the reply keyboard."""
    logger.info(f"User {message.from_user.id} pressed Instructions button")
    
    # Get current group info
    data = await state.get_data()
    group_id = data.get("current_group_id")
    group_name = data.get("current_group_name")
    
    if not group_id:
        await message.answer("Please select a group first.")
        return
    
    # Clean up previous instructions or group info messages
    previous_instructions_msg_id = data.get("instructions_msg_id")
    previous_group_info_msg_id = data.get("group_info_msg_id")
    
    if previous_instructions_msg_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=previous_instructions_msg_id)
        except Exception as e:
            logger.warning(f"Failed to delete previous instructions message: {e}")
    
    if previous_group_info_msg_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=previous_group_info_msg_id)
            await state.update_data(group_info_msg_id=None)
        except Exception as e:
            logger.warning(f"Failed to delete previous group info message: {e}")
    
    instructions_text = (
        "📝 <b>Instructions</b>\n\n"
        "• Answer questions with yes/no to find matches\n"
        "• Add your own questions for others\n"
        "• Find matches based on shared values\n"
        "• Chat anonymously with your matches\n\n"
        "The more questions you answer, the better your matches will be!"
    )
    
    try:
        # Send instructions and store the message ID for future cleanup
        instructions_msg = await message.answer(instructions_text, parse_mode="HTML")
        await state.update_data(instructions_msg_id=instructions_msg.message_id)
        
        # Set state to viewing_question to enable direct question entry
        await state.set_state(QuestionFlow.viewing_question)
        
        # Show group menu again to maintain context
        if group_id and group_name:
            await show_group_menu(message, group_id, group_name, state, session=session)
    except Exception as e:
        logger.error(f"Error sending instructions: {e}")


async def handle_group_info_message(message: types.Message, state: FSMContext, session: AsyncSession = None) -> None:
    """Handle the 'Group Info' button from the reply keyboard."""
    logger.info(f"User {message.from_user.id} pressed Group Info button")
    logger.info(f"Session type: {type(session)}")
    
    # Detailed session logging
    if session is None:
        logger.error("Session is None - middleware might not be providing the session correctly")
    else:
        logger.info(f"Session is available of type {type(session)}, is_active={session.is_active if hasattr(session, 'is_active') else 'unknown'}")
    
    # Get current group info
    data = await state.get_data()
    logger.info(f"State data: {data}")
    group_id = data.get("current_group_id")
    logger.info(f"Group ID from state: {group_id}")
    
    if not group_id:
        logger.error(f"Missing required data: group_id is None or empty")
        await message.answer("Please select a group first or reconnect to the bot by typing /start.")
        return
        
    if not session:
        logger.error(f"Session is None, cannot proceed with database operations")
        await message.answer("Database connection error. Please try again later or reconnect to the bot by typing /start.")
        return
    
    # Clean up previous instructions or group info messages
    previous_instructions_msg_id = data.get("instructions_msg_id")
    previous_group_info_msg_id = data.get("group_info_msg_id")
    
    if previous_instructions_msg_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=previous_instructions_msg_id)
            await state.update_data(instructions_msg_id=None)
        except Exception as e:
            logger.warning(f"Failed to delete previous instructions message: {e}")
    
    if previous_group_info_msg_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=previous_group_info_msg_id)
        except Exception as e:
            logger.warning(f"Failed to delete previous group info message: {e}")
    
    try:
        # Get group details from database
        from src.db.models import Group
        from sqlalchemy import func, select
        import base64
        from datetime import datetime
        
        # Get user from database
        user_tg = message.from_user
        db_user = await user_repo.get_by_telegram_id(session, user_tg.id)
        if not db_user:
            logger.error(f"User with Telegram ID {user_tg.id} not found in database")
            await message.answer("Your user profile was not found. Please try /start to restart.")
            return
        
        # Get group details
        logger.info(f"Attempting to fetch group with ID: {group_id}")
        group = await group_repo.get(session, group_id)
        
        if not group:
            logger.error(f"Group with ID {group_id} not found in database")
            await message.answer("Group information not found.")
            return
        
        logger.info(f"Found group: {group.name} (ID: {group.id})")
        
        # Get group members
        members = await group_repo.get_group_members(session, group_id)
        members_count = len(members) if members else 0
        logger.info(f"Group has {members_count} members")
        
        # Get user's role in group
        user_role = await group_repo.get_user_role(session, db_user.id, group_id)
        is_creator = user_role == "creator"
        
        # Format creation date
        created_at = group.created_at
        if created_at:
            if isinstance(created_at, str):
                try:
                    created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                except ValueError:
                    created_at = None
            
            if created_at:
                created_at_str = created_at.strftime("%d %b %Y")
            else:
                created_at_str = "Unknown date"
        else:
            created_at_str = "Unknown date"
        
        # Build group info message
        group_info = [
            f"<b>📋 Group Information</b>",
            f"",
            f"<b>Name:</b> {group.name}",
        ]
        
        # Add description if available
        if group.description:
            group_info.append(f"<b>Description:</b> {group.description}")
        
        # Add creation date and member count
        group_info.extend([
            f"<b>Created:</b> {created_at_str}",
            f"<b>Members:</b> {members_count}",
            f"<b>Your role:</b> {user_role.capitalize()}"
        ])
        
        # Add share info
        if hasattr(group, 'join_code') and group.join_code:
            group_info.extend([
                f"",
                f"<b>Share code:</b> <code>{group.join_code}</code>",
                f"You can share this code with others to invite them to this group."
            ])
        
        # Create inline keyboard with management options
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            # Show manage group button only for creator/admin
            [types.InlineKeyboardButton(
                text="⚙️ Manage Group", 
                callback_data=f"manage_group:{group_id}"
            )] if is_creator else [],
            # Always show leave group button
            [types.InlineKeyboardButton(
                text="🚪 Leave Group", 
                callback_data=f"leave_group:{group_id}"
            )]
        ])
        
        # Send the group info message
        info_msg = await message.answer("\n".join(group_info), parse_mode="HTML", reply_markup=keyboard)
        
        # Store the message ID for future cleanup
        await state.update_data(group_info_msg_id=info_msg.message_id)
        
        # Show group menu to maintain context
        await show_group_menu(message, group_id, group.name, state, current_section="group_info", session=session)
    except Exception as e:
        logger.error(f"Error getting group info: {e}", exc_info=True)
        # Just log the error without showing any messages
        try:
            # Get at least the group name for showing the menu
            group = await group_repo.get(session, group_id)
            if group:
                await show_group_menu(message, group_id, group.name, state, session=session)
            else:
                logger.error(f"Failed to get group {group_id} in exception handler")
                await message.answer("Error retrieving group information. Please try selecting your group again.")
        except Exception as inner_e:
            logger.error(f"Failed to recover from group info error: {inner_e}", exc_info=True)
            await message.answer("An error occurred while accessing group information. Please try /start again.")


async def handle_find_match_message(message: types.Message, state: FSMContext, session: AsyncSession = None) -> None:
    """Handle the 'Find Match' button from the reply keyboard."""
    try:
        logger.info(f"User {message.from_user.id} pressed Find Match button")
        
        # Get current data
        data = await state.get_data()
        group_id = data.get("current_group_id")
        
        if not group_id:
            logger.warning(f"User {message.from_user.id} has no current_group_id in state")
            await message.answer("Please select a group first.")
            return
        
        logger.info(f"Finding matches for user {message.from_user.id} in group {group_id}")
        
        # Clean up previous messages
        previous_instructions_msg_id = data.get("instructions_msg_id")
        previous_group_info_msg_id = data.get("group_info_msg_id")
        previous_find_match_msg_id = data.get("find_match_msg_id")
        
        for msg_id in [previous_instructions_msg_id, previous_group_info_msg_id, previous_find_match_msg_id]:
            if msg_id:
                try:
                    await message.bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
                except Exception as e:
                    logger.warning(f"Failed to delete previous message: {e}")
        
        # Clear stored message IDs
        update_data = {
            "instructions_msg_id": None,
            "group_info_msg_id": None,
            "find_match_msg_id": None
        }
        
        # Retrieve the user from the database
        db_user = await user_repo.get_by_telegram_id(session, message.from_user.id)
        if not db_user:
            logger.error(f"User {message.from_user.id} not found in database")
            await message.answer("❌ Your user profile couldn't be found. Please restart by clicking /start.")
            return
        
        # Check if user has enough points (1 point required)
        if db_user.points < FIND_MATCH_COST:
            logger.info(f"User {db_user.id} tried to find match but has insufficient points ({db_user.points})")
            await message.answer(
                f"❌ You need at least {FIND_MATCH_COST} points to find a match. You currently have {db_user.points} points.\n\n"
                "To earn more points, answer more questions in your group!"
            )
            return
        
        # Check if user has answered enough questions
        answer_count = await get_answer_count(session, db_user.id, int(group_id))
        logger.info(f"User {db_user.id} has answered {answer_count} questions in group {group_id}")
        
        if answer_count < MIN_QUESTIONS_FOR_MATCH:
            logger.info(f"User {db_user.id} tried to find match but has only answered {answer_count} questions (min required: {MIN_QUESTIONS_FOR_MATCH})")
            await message.answer(
                f"❌ You need to answer at least {MIN_QUESTIONS_FOR_MATCH} questions to find a match.\n"
                f"You've currently answered {answer_count} questions."
            )
            return
        
        # Get the group from the database
        group = await group_repo.get(session, int(group_id))
        if not group:
            logger.error(f"Group {group_id} not found in database")
            await message.answer("❌ Group not found. Please restart by clicking on the group link.")
            return
        
        # Get count of other users in the group for logging
        group_members = await group_repo.get_group_members(session, int(group_id))
        other_members_count = len([m for m in group_members if m.user_id != db_user.id])
        logger.info(f"Group {group_id} has {other_members_count} other members besides user {db_user.id}")
        
        # Deduct points from the initiating user
        db_user.points -= FIND_MATCH_COST
        session.add(db_user)
        await session.commit()
        logger.info(f"Deducted {FIND_MATCH_COST} points from user {db_user.id}, new balance: {db_user.points}")
        
        # Find matches
        logger.info(f"Calling find_matches for user {db_user.id} in group {group_id}")
        match_results = await find_matches(session, db_user.id, int(group_id))
        logger.info(f"Found {len(match_results)} potential matches for user {db_user.id} in group {group_id}")
        
        if not match_results or len(match_results) == 0:
            # No matches found
            logger.info(f"No matches found for user {db_user.id} in group {group_id}")
            
            # Refund points since no matches were found
            db_user.points += FIND_MATCH_COST
            session.add(db_user)
            await session.commit()
            logger.info(f"Refunded {FIND_MATCH_COST} points to user {db_user.id} due to no matches, new balance: {db_user.points}")
            
            try:
                # Send no matches message
                await message.answer(
                    "😔 No matches found at this time. Please try again later when more group members have answered questions."
                )
                
                # Show group menu to maintain context
                await show_group_menu(message, group_id, group.name, state, session=session)
            except Exception as menu_error:
                logger.error(f"Error showing group menu after no matches: {menu_error}")
                await message.answer("Please use /start to return to the main menu.")
            
            return
        
        # Get the top match
        matched_user_id, cohesion_score, common_questions, category_scores, category_counts = match_results[0]
        logger.info(f"Found match: user {matched_user_id} with cohesion score {cohesion_score:.2f}, {common_questions} common questions")
        
        # Store match data in state for callbacks to use
        update_data.update({
            "matched_user_id": matched_user_id,
            "cohesion_score": cohesion_score,
            "common_questions": common_questions,
            "category_scores": category_scores,
            "category_counts": category_counts,
            "current_group_id": int(group_id),  # Ensure group_id is always set
            "current_group_name": group.name    # Ensure group_name is always set
        })
        
        # Get the matched user from the database
        matched_db_user = await user_repo.get(session, matched_user_id)
        if not matched_db_user:
            logger.error(f"Could not find matched user with ID {matched_user_id} in database")
            
            # Refund points due to error
            db_user.points += FIND_MATCH_COST
            session.add(db_user)
            await session.commit()
            logger.info(f"Refunded {FIND_MATCH_COST} points to user {db_user.id} due to error, new balance: {db_user.points}")
            
            await message.answer("❌ An error occurred while retrieving your match information.")
            await show_group_menu(message, group_id, group.name, state, session=session)
            return
        
        logger.info(f"Found matched user in database: ID={matched_db_user.id}, Telegram ID={matched_db_user.telegram_id}")
        
        # Format the cohesion score as a percentage
        cohesion_percentage = int(cohesion_score * 100)
        
        # Prepare the match confirmation message
        confirmation_text = (
            f"🎉 <b>We found you a match with a team member!</b>\n\n"
            f"<b>Cohesion Score: {cohesion_percentage}%</b>\n"
            f"You share perspectives on <b>{common_questions} questions</b>.\n\n"
        )
        
        # Add category breakdown if available
        if category_scores:
            confirmation_text += "<b>Category Breakdown:</b>\n"
            for category, cat_score in category_scores.items():
                cat_percentage = int(cat_score * 100)  # Convert cohesion score to percentage
                question_count = category_counts.get(category, 0)
                confirmation_text += f"• <b>{category.title()}</b>: {cat_percentage}% ({question_count} questions)\n"
            confirmation_text += "\n"
        
        # Add hidden group ID for context recovery if needed
        confirmation_text += f"<span class='hidden'>group_id:{group_id}</span>"
        
        # Try to get the nickname and photo for the matched user
        matched_user_nickname = None
        matched_user_photo = None
        
        try:
            # Get the group member record for the matched user
            logger.info(f"Fetching group member data for matched user {matched_user_id} in group {group_id}")
            
            # Log database connection info
            logger.info(f"Database session valid: {session is not None}")
            
            matched_group_member = await group_repo.get_group_member(session, matched_user_id, int(group_id))
            
            if matched_group_member:
                logger.info(f"Found group member record for user {matched_user_id}: {matched_group_member}")
                matched_user_nickname = getattr(matched_group_member, "nickname", None)
                matched_user_photo = getattr(matched_group_member, "photo_file_id", None)
                logger.info(f"Retrieved nickname: '{matched_user_nickname}' and photo ID: '{matched_user_photo}'")
                
                # Store nickname and photo in state
                update_data["matched_user_nickname"] = matched_user_nickname
                update_data["matched_user_photo"] = matched_user_photo
                
                # Add the nickname to the confirmation text if available
                if matched_user_nickname:
                    logger.info(f"Adding nickname '{matched_user_nickname}' to confirmation text")
                    confirmation_text = confirmation_text.replace("with a team member", f"with <b>{matched_user_nickname}</b>")
                else:
                    logger.warning(f"No nickname found for matched user {matched_user_id}")
            else:
                logger.warning(f"No group member record found for matched user {matched_user_id} in group {group_id}")
        except Exception as e:
            logger.error(f"Error retrieving nickname/photo for matched user: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            # Continue without nickname/photo
        
        # Check if there is an existing match record
        existing_match = await get_match(session, db_user.id, matched_user_id, int(group_id))
        
        # Check if there is an existing chat session
        existing_chat = await get_chat_by_participants(
            session, db_user.id, matched_user_id, int(group_id)
        )
        
        # If no existing match or chat, create a new match record
        if not existing_match:
            match_record = Match(
                user1_id=db_user.id,
                user2_id=matched_user_id,
                group_id=int(group_id),
                score=cohesion_score,
                common_questions=common_questions,
                created_at=datetime.now()
            )
            session.add(match_record)
            await session.commit()
            logger.info(f"Created new match record for users {db_user.id} and {matched_user_id} in group {group_id}")
        else:
            logger.info(f"Using existing match record between users {db_user.id} and {matched_user_id}")
        
        # Create keyboard with the Start Chat button
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(
                text="🗣 Start Anonymous Chat",
                callback_data=f"start_anon_chat:{matched_user_id}"
            )],
            [types.InlineKeyboardButton(
                text="❌ Cancel",
                callback_data="cancel_match"
            )]
        ])
        
        # Add notice about points being deducted
        confirmation_text += f"👉 <b>{FIND_MATCH_COST} points</b> have been deducted from your account for this match.\n\n"
        confirmation_text += "Click the button below to start an anonymous chat with your match. Your identity will remain hidden until you choose to reveal it."
        
        # Log what we're about to put in state
        logger.info(f"About to update state with: {update_data}")
        
        # Send the message with the matched user's photo if available
        sent_message = None
        if matched_user_photo:
            try:
                logger.info(f"Sending match confirmation with photo ID: {matched_user_photo}")
                match_msg = await message.answer_photo(
                    photo=matched_user_photo,
                    caption=confirmation_text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
                update_data["find_match_msg_id"] = match_msg.message_id
                sent_message = match_msg
            except Exception as e:
                logger.error(f"Error sending matched user photo: {str(e)}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                # Fall back to text-only message
                try:
                    match_msg = await message.answer(
                        text=confirmation_text,
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
                    update_data["find_match_msg_id"] = match_msg.message_id
                    sent_message = match_msg
                except Exception as e2:
                    logger.error(f"Error sending text fallback: {str(e2)}")
                    raise
        else:
            # Send text-only message if no photo is available
            logger.info("No photo available, sending text-only match confirmation")
            try:
                match_msg = await message.answer(
                    text=confirmation_text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
                update_data["find_match_msg_id"] = match_msg.message_id
                sent_message = match_msg
            except Exception as e:
                logger.error(f"Error sending text message: {str(e)}")
                raise
        
        if not sent_message:
            logger.error("Failed to send match confirmation message")
            
            # Refund points due to error
            db_user.points += FIND_MATCH_COST
            session.add(db_user)
            await session.commit()
            logger.info(f"Refunded {FIND_MATCH_COST} points to user {db_user.id} due to error, new balance: {db_user.points}")
            
            await message.answer("❌ An error occurred while sending match information.")
            return
        
        # Update state data
        await state.update_data(**update_data)
        
        # Log that we've updated state
        logger.info(f"Updated state data for user {db_user.id} with match information")
        
        # Get the current state data to verify
        verification_data = await state.get_data()
        logger.info(f"Current state data: matched_user_id={verification_data.get('matched_user_id')}, "
                   f"cohesion_score={verification_data.get('cohesion_score')}, "
                   f"current_group_id={verification_data.get('current_group_id')}")
    except Exception as e:
        logger.error(f"Error in handle_find_match_message: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        # Safely attempt to refund points
        try:
            # Only refund if we have valid db_user
            if 'db_user' in locals() and db_user:
                db_user.points += FIND_MATCH_COST
                session.add(db_user)
                await session.commit()
                logger.info(f"Refunded {FIND_MATCH_COST} points to user {db_user.id} due to error, new balance: {db_user.points}")
        except Exception as e2:
            logger.error(f"Failed to refund points: {e2}")
        
        # Send a single error message rather than potentially sending two
        if not 'no_matches_sent' in locals() or not locals()['no_matches_sent']:
            try:
                await message.answer("❌ An error occurred while finding a match. Please try again later.")
            except Exception as e3:
                logger.error(f"Failed to send error message: {e3}")
        
        # Safely attempt to show group menu
        try:
            # Only try to show menu if we have valid group data
            if 'group' in locals() and group and 'group_id' in locals() and group_id:
                await show_group_menu(message, group_id, group.name, state, session=session)
        except Exception as e3:
            logger.error(f"Failed to show group menu: {e3}")
            # Try a simple fallback
            try:
                await message.answer("Use /start to return to the main menu.")
            except:
                pass


async def handle_add_question_message(message: types.Message, state: FSMContext, session: AsyncSession = None) -> None:
    """Handle the 'Add Question' button from the reply keyboard."""
    logger.info(f"User {message.from_user.id} pressed Add Question button")
    
    # Redirect to the existing add question handler
    await on_add_question(message, state, session)


# Add this debugging helper function at the top of the file
async def debug_callback(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession = None) -> None:
    """Debug handler that catches all unhandled callback queries."""
    try:
        # Log the unhandled callback
        logger.warning(f"Unhandled callback data: '{callback.data}' from user {callback.from_user.id}")
        
        # Log the state data
        state_data = await state.get_data()
        logger.warning(f"Current state data: {state_data}")
        logger.warning(f"Current state: {await state.get_state()}")
        
        # Get user info
        user_info = f"ID: {callback.from_user.id}, Username: @{callback.from_user.username}"
        logger.warning(f"User info: {user_info}")
        
        # Get message info if present
        if callback.message:
            message_info = f"Chat ID: {callback.message.chat.id}, Message ID: {callback.message.message_id}"
            if callback.message.text:
                message_text = callback.message.text[:50] + ("..." if len(callback.message.text) > 50 else "")
                message_info += f", Text: '{message_text}'"
            logger.warning(f"Message info: {message_info}")
        
        # For group-related callbacks, try to extract the group ID
        group_id = None
        if ":" in callback.data:
            parts = callback.data.split(":")
            try:
                group_id = int(parts[1])
                logger.warning(f"Extracted potential group ID: {group_id}")
            except (ValueError, IndexError):
                pass
        
        # Check if this callback might be for a group action
        if any(callback.data.startswith(prefix) for prefix in ["manage_group", "leave_group", "go_to_group"]):
            logger.warning(f"This appears to be a group-related callback: {callback.data}")
            
            # If we have a session and group_id, try to get the group info
            if session and group_id:
                try:
                    group = await group_repo.get(session, group_id)
                    if group:
                        logger.warning(f"Found group: id={group.id}, name={group.name}")
                    else:
                        logger.warning(f"Group with ID {group_id} not found in database")
                except Exception as e:
                    logger.exception(f"Error retrieving group info: {e}")
        
        # Acknowledge the callback to prevent the "loading" state
        await callback.answer("This action is not currently available", show_alert=True)
        
        # If we're in a development environment, send a debug message
        is_dev = not os.environ.get("RAILWAY_ENVIRONMENT")
        if is_dev:
            await callback.message.answer(
                f"DEBUG: Unhandled callback '{callback.data}'\n"
                f"State: {await state.get_state()}\n"
                f"Please report this to the developers."
            )
    except Exception as e:
        logger.exception(f"Error in debug callback handler: {e}")
        try:
            await callback.answer("An error occurred processing your request", show_alert=True)
        except:
            pass

async def echo_debug_handler(message: types.Message, state: FSMContext) -> None:
    """Debug handler to echo text messages and log state."""
    logger.info(f"ECHO DEBUG: Received text '{message.text}' from user {message.from_user.id}")
    
    # Get state information
    current_state = await state.get_state()
    state_data = await state.get_data()
    
    logger.info(f"Current state: {current_state}")
    logger.info(f"State data: {state_data}")
    
    # Don't actually echo in production
    is_dev = not os.environ.get("RAILWAY_ENVIRONMENT")
    if is_dev:
        await message.reply(f"Debug mode: Your message '{message.text}' was received, but no handler processed it.")


async def handle_direct_question_entry(message: types.Message, state: FSMContext, session: AsyncSession = None) -> None:
    """Handle direct question entry from user (a message that ends with a question mark)."""
    logger.info(f"Direct question entry detected: '{message.text}' from user {message.from_user.id}")
    
    if not session:
        logger.error("No database session provided to handle_direct_question_entry")
        await message.reply("Error: Could not process your question. Please try again later.")
        return
    
    # Get current state data
    data = await state.get_data()
    group_id = data.get("current_group_id")
    group_name = data.get("current_group_name")
    
    # If user is not in a group context, we can't process the question
    if not group_id or not group_name:
        logger.info(f"User {message.from_user.id} tried to add question but not in a group context")
        await message.reply("Please join or select a group first before adding questions.")
        return
    
    # Set state for question creation
    await state.set_state(QuestionFlow.creating_question)
    question_text = message.text.strip()
    
    # Show waiting message while checking with OpenAI
    waiting_msg = await message.reply("Processing your question, please wait...")
    
    # Check for spelling errors
    has_spelling_errors, corrected_text = await check_spelling(question_text)
    if has_spelling_errors:
        # Delete waiting message
        try:
            await message.bot.delete_message(message.chat.id, waiting_msg.message_id)
        except Exception as e:
            logger.warning(f"Failed to delete waiting message: {e}")
            
        # Store both versions of the text
        await state.update_data(
            original_question_text=question_text,
            corrected_question_text=corrected_text
        )
        
        # Show the correction suggestion with inline buttons
        correction_text = f"Did you mean:\n\n<b>{corrected_text}</b>"
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [
                types.InlineKeyboardButton(text="✅ Yes, use this", callback_data="use_corrected_text"),
                types.InlineKeyboardButton(text="❌ No, use original", callback_data="use_original_text"),
            ]
        ])
        
        correction_msg = await message.reply(correction_text, reply_markup=keyboard, parse_mode="HTML")
        await state.update_data(
            correction_msg_id=correction_msg.message_id,
            original_question_message_id=message.message_id
        )
        await state.set_state(QuestionFlow.choosing_correction)
        return
    
    # Check if it's a yes/no question using OpenAI
    is_yes_no, yes_no_reason = await is_yes_no_question(question_text)
    if not is_yes_no:
        # Delete waiting message
        try:
            await message.bot.delete_message(message.chat.id, waiting_msg.message_id)
        except Exception as e:
            logger.warning(f"Failed to delete waiting message: {e}")
            
        validation_msg = await message.reply("🙋‍♂️ Please ask a question that can be answered with Agree/Disagree.")
        return
    
    # Check for duplicate questions
    is_duplicate, duplicate_text, duplicate_id = await check_duplicate_question(question_text, group_id, session)
    if is_duplicate:
        # Delete waiting message
        try:
            await message.bot.delete_message(message.chat.id, waiting_msg.message_id)
        except Exception as e:
            logger.warning(f"Failed to delete waiting message: {e}")
            
        duplicate_msg = await message.reply(f"🔄 This seems similar to an existing question. Please try a different question.")
        return
    
    # Delete waiting message
    try:
        await message.bot.delete_message(message.chat.id, waiting_msg.message_id)
    except Exception as e:
        logger.warning(f"Failed to delete waiting message: {e}")
    
    # Store the question text and ask for confirmation
    await state.update_data(
        new_question_text=question_text,
        original_question_message_id=message.message_id
    )
    
    confirmation_text = f"Your question:\n\n{question_text}\n\nIs this correct and ready to be added?"
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="✅ Yes", callback_data="confirm_add_question"),
            types.InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_add_question"),
        ]
    ])
    confirmation_message = await message.reply(confirmation_text, reply_markup=keyboard)
    await state.update_data(confirmation_message_id=confirmation_message.message_id)
    await state.set_state(QuestionFlow.reviewing_question)

