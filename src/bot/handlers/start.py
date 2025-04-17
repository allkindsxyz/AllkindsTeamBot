from aiogram import Dispatcher, F, types, Bot
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.utils.deep_linking import decode_payload, create_start_link
from loguru import logger
import base64
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete, update

# from src.bot.config import bot_settings # No longer needed
from src.core.config import get_settings # Import main settings
from src.bot.keyboards.inline import (
    get_start_menu_keyboard, 
    get_group_menu_keyboard, 
    get_answer_keyboard_with_skip,
    get_group_menu_reply_keyboard,
    get_match_confirmation_keyboard # Import keyboard function (will create next)
)
from src.bot.states import TeamCreation, TeamJoining, QuestionFlow, MatchingStates, GroupOnboarding
from src.core.openai_service import is_yes_no_question, check_duplicate_question, check_spelling
from src.db import get_session
from src.db.repositories import user_repo, question_repo, answer_repo, group_repo, match_repo
from src.db.models import Answer, User, AnswerType, MemberRole, Question, Match, GroupMember
from src.bot.utils.matching import find_best_match
from src.db.repositories.match_repo import get_match_between_users, create_match
from src.db.repositories.chat_session_repo import create_chat_session, get_by_match_id

settings = get_settings() # Get settings from config

# Define the mapping for answer values
ANSWER_VALUES = {
    "strong_no": -2,
    "no": -1,
    "skip": 0, # Special case for skip
    "yes": 1,
    "strong_yes": 2,
}


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
        # Special case for known deep link "ZzE" = base64("g1")
        if args == "ZzE":
            logger.info("DEBUG: Found exact match for ZzE (g1)")
            group_id = 1
            await handle_group_invite(message, group_id, state, session)
            return
        
        # General base64 decode attempt
        try:
            decoded_args = base64.b64decode(args).decode('utf-8')
            logger.info(f"DEBUG: Decoded args from base64: {decoded_args}")
            
            # Check if it's an invite link in decoded form
            if decoded_args.startswith('g') and decoded_args[1:].isdigit():
                group_id = int(decoded_args[1:])
                logger.info(f"DEBUG: Deep link join for group {group_id}")
                await handle_group_invite(message, group_id, state, session)
                return
        except Exception as e:
            logger.info(f"DEBUG: Not a valid base64 string, using raw args: {e}")
        
        # Check if it's an invite link in raw form
        if args.startswith('g') and args[1:].isdigit():
            group_id = int(args[1:])
            logger.info(f"DEBUG: Direct deep link join for group {group_id}")
            await handle_group_invite(message, group_id, state, session)
            return
    
    user_tg = message.from_user
    logger.info(f"User {user_tg.id} started the bot")
    
    # Ensure session is available (dependency injection handles this)
    if not session:
        logger.error("Database session not available in cmd_start")
        await message.answer("Sorry, there was a problem connecting to the database.")
        return
        
    # Get or create user in DB - Convert Telegram user to dict manually
    user_dict = {
        "id": user_tg.id,
        "first_name": user_tg.first_name,
        "last_name": user_tg.last_name,
        "username": user_tg.username,
        "is_bot": user_tg.is_bot
    }
    db_user, created = await user_repo.get_or_create_user(session, user_dict)
    if created:
        logger.info(f"Created new user in DB: {db_user.id} (TG: {db_user.telegram_id})")
    else:
        logger.info(f"Found existing user in DB: {db_user.id} (TG: {db_user.telegram_id})")

    # Check if user belongs to any groups
    user_groups = await group_repo.get_user_groups(session, db_user.id)
    
    # Create state if it doesn't exist
    if not state:
        state = Dispatcher.get_current().fsm_storage.get_context(bot=message.bot, chat_id=message.chat.id, user_id=message.from_user.id)
    
    # Check if there's a deep link payload
    if command and command.args:
        raw_arg = command.args
        logger.info(f"Received start command with raw args: {raw_arg}")
        payload = None
        
        try:
            # Attempt base64 decoding first
            missing_padding = len(raw_arg) % 4
            if missing_padding:
                padded_arg = raw_arg + '=' * (4 - missing_padding)
            else:
                padded_arg = raw_arg
            
            decoded_bytes = base64.urlsafe_b64decode(padded_arg)
            payload = decoded_bytes.decode('utf-8')
            logger.info(f"Successfully base64 decoded payload: {payload}")
            
        except (base64.binascii.Error, UnicodeDecodeError) as decode_error:
            # If decoding fails, assume the raw argument is the payload
            logger.warning(f"Base64 decode failed ({decode_error}), using raw arg as payload: {raw_arg}")
            payload = raw_arg
        except Exception as e:
            # Catch any other unexpected errors during decoding attempt
            logger.error(f"Unexpected error during payload decoding attempt for '{raw_arg}': {e}")
            payload = None # Ensure payload is None if error occurs
            
        # Process the payload if we have one
        if payload:
            logger.info(f"Processing payload: {payload}")
            if payload.startswith("g"):
                try:
                    group_id = int(payload[1:])
                    
                    # Check if user is already in this group
                    is_member = False
                    for group in user_groups:
                        if group.id == group_id:
                            is_member = True
                            break
                    
                    if is_member:
                        # User is already in this group, go directly to questions
                        logger.info(f"User {user_tg.id} is already in group {group_id}. Going directly to questions.")
                        group = await group_repo.get(session, group_id)
                        if group:
                            await state.update_data(current_group_id=group_id, current_group_name=group.name)
                            await state.set_state(QuestionFlow.viewing_question)
                            await on_show_questions(message, state, session)
                            return
                    else:
                    # User is not in this group, ask to join
                        await handle_group_invite(message, group_id, state, session)
                        return
                        
                except ValueError as e:
                    logger.warning(f"Invalid group ID in payload: {payload}, error: {e}")
            else:
                logger.warning(f"Unknown payload format: {payload}")
        else:
            logger.error("Failed to obtain a valid payload from start argument.")

    # No valid deep link, check if user is in any groups
    if user_groups:
        # User is already in some group
        # For now, consider that a user has just one group
        group = user_groups[0]  # Take the first group
        
        # Verify the group still exists
        if not await group_repo.get(session, group.id):
            logger.warning(f"Group {group.id} no longer exists for user {user_tg.id}")
            await message.answer("This group was deleted.")
            await show_welcome_menu(message)
            return
        
        logger.info(f"User {user_tg.id} is in group {group.id}. Showing group info.")
        
        # Get user's points balance
        points = db_user.points
        
        # Split the welcome message into two parts:
        # 1. Welcome message with menu buttons
        welcome_text = f"Welcome back to <b>{group.name}</b>!"
        
        # 2. Balance message with inline button
        balance_text = f"Your balance: 💎 {points} points"
        
        # Update state with current group
        await state.update_data(current_group_id=group.id, current_group_name=group.name)
        await state.set_state(QuestionFlow.viewing_question)
        
        # Get count of unanswered questions
        unanswered_count = await get_unanswered_question_count(session, db_user.id, group.id)
        
        # Get count of answered questions
        answers = await answer_repo.get_answers_for_user_in_group(session, db_user.id, group.id)
        answered_count = len(answers)
        
        # Get the reply keyboard with points balance for the welcome message
        reply_keyboard = get_group_menu_reply_keyboard(current_section="questions", balance=points)
        
        # Create inline keyboard with Load previously answered questions button for the balance message
        inline_keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(
                text=f"📋 Load previously answered questions ({answered_count})", 
                callback_data="load_answered_questions"
            )]
        ])
        
        # Send welcome message with menu buttons (reply keyboard)
        await message.answer(welcome_text, reply_markup=reply_keyboard, parse_mode="HTML")
        
        # Send balance message with inline keyboard
        await message.answer(balance_text, reply_markup=inline_keyboard, parse_mode="HTML")
        
        # Check if there are new questions to answer and display the first one
        await check_and_display_next_question(message, db_user, group.id, state, session)
    else:
        # User is not in any group, show welcome menu with create/join options
        logger.info(f"User {user_tg.id} is not in any groups. Showing welcome menu.")
        await show_welcome_menu(message)


async def display_single_question(message: types.Message, question, db_user, session: AsyncSession) -> None:
    """Display a single question to the user."""
    logger.info(f"Starting display_single_question for question {question.id} to user {db_user.id}")
    
    # Check if user can delete this question
    can_delete = await can_delete_question(db_user.id, question, session)
    
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
        
        # Ensure any pending changes are committed to avoid inconsistent state
        await session.commit()
        
        # Get user's current answers to make sure we have up-to-date data
        # This is critical for PostgreSQL to avoid caching issues
        current_answers = await answer_repo.get_answers_for_user_in_group(session, db_user.id, group_id)
        answered_ids = [a.question_id for a in current_answers]
        
        # Log answered questions to help with debugging
        logger.info(f"User {db_user.id} has answered {len(answered_ids)} questions in group {group_id}")
        logger.info(f"Recently shown questions: {recently_shown_questions}")
        
        # Get the total number of available questions for user in this group
        all_questions_query = select(Question).where(
            Question.group_id == group_id,
            Question.is_active == True
        )
        all_questions_result = await session.execute(all_questions_query)
        all_questions = all_questions_result.scalars().all()
        total_available = len([q for q in all_questions if q.id not in answered_ids])
        
        # If we've shown all questions, reset the recently shown list
        if len(recently_shown_questions) >= total_available:
            recently_shown_questions = []
            logger.info(f"Reset recently shown questions list for user {db_user.id} as all available questions have been shown")
        
        # Get the next unanswered question with a fresh query, excluding recently shown ones
        next_question = await question_repo.get_next_question_for_user(
            session,
            db_user.id,
            group_id,
            excluded_ids=recently_shown_questions
        )
        
        # If no questions available when excluding recently shown ones,
        # but there are unanswered questions, try again without the exclusion
        if not next_question and total_available > 0:
            logger.info(f"No new questions for user {db_user.id}, showing previously seen ones")
            # Only exclude the very last shown question to avoid immediate repetition
            last_shown = [last_displayed_question_id] if last_displayed_question_id else []
            next_question = await question_repo.get_next_question_for_user(
                session,
                db_user.id,
                group_id,
                excluded_ids=last_shown
            )
        
        # Safety check to ensure we don't show a question that was just answered
        # This is especially important for PostgreSQL in Railway environment
        if next_question and next_question.id in answered_ids:
            logger.warning(f"Question {next_question.id} was already answered by user {db_user.id} but was returned again. Skipping it.")
            # Try to get another question by explicitly excluding this one
            await session.refresh(next_question)  # Refresh the object from DB
            logger.info(f"Retrying with explicit exclusion of question {next_question.id}")
            return False  # Don't show a question, signal that none was displayed
        
        # If we found a question, display it
        if next_question:
            # Reset the "no questions shown" flag since we have a question to show
            if no_questions_shown:
                await state.update_data(no_questions_shown=False)
                
            # Clean up previous unanswered question messages to avoid having multiple unanswered questions
            await cleanup_previous_questions(message, state)
                
            await display_single_question(message, next_question, db_user, session)
            logger.info(f"Displayed next question {next_question.id} for user {db_user.id} in group {group_id}")
            
            # Update recently shown questions (keep up to 50 most recent questions)
            if next_question.id not in recently_shown_questions:
                recently_shown_questions.append(next_question.id)
                # Keep the list at a reasonable size
                if len(recently_shown_questions) > 50:
                    recently_shown_questions = recently_shown_questions[-50:]
            
            # Update state with the question we just displayed
            await state.update_data(
                last_displayed_question_id=next_question.id,
                recently_shown_questions=recently_shown_questions
            )
            
            return True
        else:
            # No more questions to answer
            # Only show the message if we haven't shown it before
            if not no_questions_shown:
                no_questions_msg = await message.answer("No more questions from people at the moment")
                # Store the message ID so we can delete it later if needed
                await state.update_data(
                    no_questions_msg_id=no_questions_msg.message_id,
                    no_questions_shown=True
                )
                logger.info(f"No more questions for user {db_user.id} in group {group_id}, displayed 'no questions' message")
            else:
                logger.info(f"No more questions for user {db_user.id} in group {group_id}, 'no questions' message already shown")
            
            return False
    except Exception as e:
        logger.error(f"Error checking/displaying next question for user {db_user.id}: {e}", exc_info=True)
        await message.answer("An error occurred while loading questions.")
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
    """Handle the 'Load previously answered questions' button click."""
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
    
    await message.answer(welcome_text, reply_markup=keyboard)


async def show_welcome_menu(message: types.Message) -> None:
    """Show welcome message with create/join options."""
    user = message.from_user
    
    welcome_text = (
        f"👋 Welcome to Allkinds, {user.first_name}!\n\n"
        "Connect with people who share your values through yes/no questions and answers.\n\n"
        "What would you like to do?"
    )
    
    # Get the keyboard with "Create a Team" and "Contact Allkinds Team" buttons
    keyboard = get_start_menu_keyboard()
    
    await message.answer(welcome_text, reply_markup=keyboard)


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


async def on_join_team(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Handle join team button callback."""
    await callback.answer()
    
    text = (
        "To join a Team, you need an invitation link or code.\n\n"
        "Please enter the invitation code or ask the Team creator for an invitation link."
    )
    
    # Set user state to waiting for team code
    await state.set_state(TeamJoining.waiting_for_code)
    
    await callback.message.answer(text)


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


async def on_team_confirm(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Handle team creation confirmation."""
    await callback.answer()
    
    # Get team data
    data = await state.get_data()
    team_name = data.get("team_name")
    team_description = data.get("team_description", "")
    
    # Create the team in the database
    user_tg = callback.from_user
    db_user = await user_repo.get_by_telegram_id(session, user_tg.id)
    
    if not db_user:
        logger.error(f"User {user_tg.id} not found in database")
        await callback.message.answer("Error creating team. Please try again.")
        return
    
    # Create the group in the database
    try:
        new_group = await group_repo.create(session, {
            "creator_id": db_user.id,
            "name": team_name,
            "description": team_description,
            "is_active": True,
            "is_private": False
        })
        
        # Automatically add the creator as a member with CREATOR role
        await group_repo.add_user_to_group(
            session,
            db_user.id,
            new_group.id,
            role=MemberRole.CREATOR
        )
        logger.info(f"Added creator {db_user.id} as member of group {new_group.id} with CREATOR role")
        
        # Generate an invite link using the real group ID
        bot = callback.bot
        payload = f"g{new_group.id}"
        invite_link = await create_start_link(bot, payload, encode=True)
        
        success_text = (
            f"🎉 Your Team '{team_name}' has been created successfully!\n\n"
            f"Share this link to invite others to your team:\n{invite_link}\n\n"
            f"Click the button below to go to your team:"
        )
        
        # Create keyboard with Go to group button
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🚀 Go to the group", callback_data=f"go_to_group:{new_group.id}")]
        ])
        
        logger.info(f"Created team '{team_name}' with ID {new_group.id}, invite link: {invite_link}")
        
        await callback.message.answer(success_text, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Error creating team: {e}")
        await callback.message.answer("Error creating team. Please try again.")
    
    # Clear the state
    await state.clear()


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
    If text is None, will try to use an invisible character to keep the chat clean.
    """
    await state.update_data(current_group_id=group_id, current_group_name=group_name)
    # Don't set viewing_question state here, let the specific action handler do it
    
    # Get user points if session is provided
    points = 0
    points_text = ""
    if session:
        user_tg = message.from_user
        db_user = await user_repo.get_by_telegram_id(session, user_tg.id)
        if db_user:
            points = db_user.points
            points_text = f"Your balance: 💎 {points} points"
    
    # Get the reply keyboard with points balance
    keyboard = get_group_menu_reply_keyboard(current_section, balance=points)
    
    # If text is explicitly provided as None, use keyboard-only approach
    if text is None:
        try:
            # Send keyboard directly to the chat without a message
            await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
            await message.bot.set_chat_menu_button(
                chat_id=message.chat.id,
                menu_button=types.MenuButtonCommands()
            )
            # Just call answer_callback_query to update the keyboard without a message
            if isinstance(message, types.CallbackQuery):
                await message.answer()
                
            # Another option is to edit a previous menu message if we can find it
            data = await state.get_data()
            prev_menu_msg_id = data.get("group_menu_msg_id")
            
            if prev_menu_msg_id:
                try:
                    # Try to edit previous message
                    await message.bot.edit_message_reply_markup(
                        chat_id=message.chat.id,
                        message_id=prev_menu_msg_id,
                        reply_markup=None  # Remove inline keyboard
                    )
                except Exception as e:
                    logger.error(f"Failed to edit previous menu message: {e}")
            
            # We still need to set the keyboard for the chat
            menu_msg = await message.answer(" ", reply_markup=keyboard)
            # Try to delete the message immediately but keep the keyboard
            try:
                await menu_msg.delete()
            except Exception as e:
                logger.error(f"Failed to delete menu message: {e}")
                # If we can't delete, make it as minimal as possible
                try:
                    await message.bot.edit_message_text(
                        chat_id=message.chat.id, 
                        message_id=menu_msg.message_id,
                        text="⌨️"  # Just a keyboard emoji
                    )
                except Exception as sub_e:
                    logger.error(f"Failed to edit menu message text: {sub_e}")
                    
            await state.update_data(group_menu_msg_id=menu_msg.message_id)
        except Exception as e:
            logger.error(f"Failed to send invisible menu message: {e}")
            # If all else fails, use a minimal text
            menu_msg = await message.answer("⌨️", reply_markup=keyboard)
            await state.update_data(group_menu_msg_id=menu_msg.message_id)
        return
        
    # For matches section, questions section, or keyboard-only mode, use minimal text
    if current_section == "matches" or current_section == "questions":
        # Use a minimal message to avoid duplicate balance information
        menu_msg = await message.answer("⌨️", reply_markup=keyboard)
        await state.update_data(group_menu_msg_id=menu_msg.message_id)
    else:
        # Show the full message for other contexts
        text = f"You are in <b>{group_name}</b>.\n{points_text}\nWhat would you like to do?"
        menu_msg = await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        # Store message ID in state so we can delete it later if needed
        await state.update_data(group_menu_msg_id=menu_msg.message_id)


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
    db_user = await user_repo.get_by_telegram_id(session, user_tg.id)
    if not db_user:
        logger.error(f"User {user_tg.id} not found in DB when showing questions")
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
    """Handles the 'Go to anonymous chat' button click."""
    await query.answer()
    user_id = query.from_user.id
    data = await state.get_data()
    
    # Check if the user has a pending match
    if not data.get("has_pending_match", False):
        logger.warning(f"User {user_id} clicked start_anon_chat but has no pending match in state data.")
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
        logger.warning(f"User {user_id} clicked start_anon_chat but no matched_user_id found in state.")
        await query.message.edit_text("Something went wrong, match data lost. Please try finding a match again.")
        return

    logger.info(f"User {user_id} confirmed chat with {matched_user_id}")
    
    # Get users from database
    db_user = await user_repo.get_by_telegram_id(session, user_id)
    matched_db_user = await user_repo.get_by_telegram_id(session, matched_user_id)
    
    if not db_user or not matched_db_user:
        logger.error(f"Could not find users in database: {user_id} or {matched_user_id}")
        await query.message.edit_text("Error: Could not find user data. Please try again.")
        return
    
    try:
        # Check if there's already a match between these users
        existing_match = await get_match_between_users(session, db_user.id, matched_db_user.id)
        if not existing_match:
            # Create a new match record
            existing_match = await create_match(
                session=session,
                user1_id=db_user.id,
                user2_id=matched_db_user.id,
                score=score,
                common_questions=common_questions
            )
        
        # Check if there's already an active chat session
        existing_chat = await get_by_match_id(session, existing_match.id)
        
        # Create a new chat session if none exists or if the existing one is not active
        if not existing_chat or existing_chat.status != "active":
            # Create a new chat session
            chat_session = await create_chat_session(
                session=session,
                initiator_id=db_user.id,
                recipient_id=matched_db_user.id,
                match_id=existing_match.id
            )
        else:
            # Use existing chat session
            chat_session = existing_chat
            logger.info(f"Using existing chat session {chat_session.id} for match {existing_match.id}")
        
        # Format the cohesion score for display
        cohesion_percentage = int(score * 100)  # Convert cohesion score to percentage
        
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
        bot_username = settings.COMMUNICATOR_BOT_USERNAME
        deep_link = f"https://t.me/{bot_username}?start=chat_{chat_session.session_id}"
        
        # Create inline button for the deeplink
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="Start Anonymous Chat", url=deep_link)]
        ])
        
        # Update the message with the deeplink
        match_text += "Click the button below to start an anonymous chat with your match. Your identity will remain hidden until you choose to reveal it."
        
        # If the original message was a photo message, edit the caption, otherwise edit text
        if query.message.photo and len(query.message.photo) > 0:
            await query.message.edit_caption(caption=match_text, reply_markup=keyboard, parse_mode="HTML")
        else:
            await query.message.edit_text(match_text, reply_markup=keyboard, parse_mode="HTML")
        
        try:
            # Create notification for the matched user
            notification_text = (
                f"🎉 <b>Someone has matched with you as their most resonating team member!</b>\n\n"
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
                
            notification_text += "Click the button below to join the anonymous chat. Your identity will remain hidden until you choose to reveal it."
            
            # Create keyboard for the matched user
            recipient_keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="Join Anonymous Chat", url=deep_link)]
            ])
            
            # Get initiator's nickname and photo if available
            try:
                initiator_nickname = None
                initiator_photo = None
                
                # Get the current group
                group_id = data.get("current_group_id")
                if group_id:
                    # Get the group member record for the initiator
                    group_member = await group_repo.get_group_member(session, db_user.id, int(group_id))
                    if group_member:
                        initiator_nickname = getattr(group_member, "nickname", None)
                        initiator_photo = getattr(group_member, "photo_file_id", None)
                        logger.info(f"Found nickname '{initiator_nickname}' and photo '{initiator_photo}' for initiator {db_user.id}")
            except Exception as e:
                logger.warning(f"Error retrieving nickname/photo for initiator {db_user.id}: {e}")
                # Continue without nickname/photo
            
            # Send notification to the matched user including initiator's photo if available
            if initiator_photo:
                try:
                    await bot.send_photo(
                        chat_id=matched_user_id,
                        photo=initiator_photo,
                        caption=notification_text,
                        reply_markup=recipient_keyboard,
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.warning(f"Error sending initiator photo: {e}. Falling back to text-only notification.")
                    await bot.send_message(
                        chat_id=matched_user_id,
                        text=notification_text,
                        reply_markup=recipient_keyboard,
                        parse_mode="HTML"
                    )
            else:
                await bot.send_message(
                    chat_id=matched_user_id,
                    text=notification_text,
                    reply_markup=recipient_keyboard,
                    parse_mode="HTML"
                )
            logger.info(f"Sent match notification to matched user {matched_user_id}")
        except Exception as e:
            logger.error(f"Failed to send match notification to matched user {matched_user_id}: {e}")
    
        # Remove the pending match flag from state data
        await state.update_data(has_pending_match=False)
    except Exception as e:
        logger.error(f"Error in handle_start_anon_chat: {e}")
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
    """Handle find match button press."""
    user_id = message.from_user.id
    data = await state.get_data()
    group_id = data.get("current_group_id")
    group_name = data.get("current_group_name", f"Team {group_id}")
    
    # Store the message ID of the "Find a match" message for potential cleanup later
    await state.update_data(find_match_message_id=message.message_id)
    
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
    
    # We no longer delete the group menu message - we keep it visible
    
    # Set the current section in state
    await state.update_data(current_section="matches")
    
    # Get user from DB
    db_user = await user_repo.get_by_telegram_id(session, user_id)
    if not db_user:
        logger.error(f"User {user_id} not found in DB when finding matches")
        await message.answer("Error: Could not find your user account. Please try /start again.")
        return
    
    # Check if user has enough points (10 required)
    if db_user.points < 10:
        remaining = 10 - db_user.points
        await message.answer(
            f"You need at least 10💎 to find a match. Your balance: {db_user.points}💎\n\n"
            f"You need {remaining} more 💎. Create questions (+5💎) or answer questions (+1💎) to earn more points."
        )
        return
    
    # Check if user has answered enough questions
    answers = await answer_repo.get_answers_for_user_in_group(session, db_user.id, group_id)
    if len(answers) < 3:  # Require at least 3 answers
        await message.answer("You need to answer at least 3 questions before finding matches. Please go to Questions first.")
        return
    
    # Find matches for this user
    waiting_msg = await message.answer("Finding matches for you... Please wait.")
    
    # Set state to finding matches temporarily for any intermediate handlers
    await state.set_state(MatchingStates.finding_matches)
    
    # Find best match using the matching algorithm
    match_result = await find_best_match(session, db_user.id, group_id)
    
    if not match_result:
        logger.warning(f"No matches found for user {db_user.id} in group {group_id}")
        await waiting_msg.delete()
        await message.answer("No matches found. Please try again later when more people have answered questions.")
        await state.set_state(QuestionFlow.viewing_question)
        return
    
    # Deduct 10 points for finding a match
    updated_user = await user_repo.subtract_points(session, db_user.id, 10)
    logger.info(f"Deducted 10 points from user {db_user.id} for finding a match. New balance: {updated_user.points}💎")
    
    matched_user_id, score, common_questions, category_scores, category_counts = match_result
    
    # Get the matched user details
    matched_user = await user_repo.get(session, matched_user_id)
    if not matched_user:
        logger.error(f"Matched user {matched_user_id} not found in DB")
        await waiting_msg.delete()
        await message.answer("Error: Could not find the matched user. Please try again.")
        await state.set_state(QuestionFlow.viewing_question)
        return
    
    # Get the matched user's nickname and photo from the GroupMember table
    matched_user_nickname = None
    matched_user_photo = None
    
    try:
        # Get the group member record for the matched user
        group_member = await group_repo.get_group_member(session, matched_user_id, group_id)
        if group_member:
            matched_user_nickname = getattr(group_member, "nickname", None)
            matched_user_photo = getattr(group_member, "photo_file_id", None)
            logger.info(f"Found nickname '{matched_user_nickname}' and photo '{matched_user_photo}' for matched user {matched_user_id}")
    except Exception as e:
        logger.warning(f"Error retrieving nickname/photo for matched user {matched_user_id}: {e}")
        # Continue without nickname/photo - this is not a critical error
    
    # Format the cohesion score - convert from -1.0...1.0 scale to 0-100% scale
    cohesion_percentage = int(score * 100)  # Convert cohesion score to percentage
    
    # Create confirmation message with match details
    match_text = (
        f"🎉 <b>Found your most resonating team member!</b>\n\n"
    )
    
    # Use nickname if available, otherwise fall back to "team member"
    if matched_user_nickname:
        match_text += f"<b>Nickname: {matched_user_nickname}</b>\n"
    
    match_text += (
        f"<b>Cohesion Score: {cohesion_percentage}%</b>\n"
        f"You share perspectives on <b>{len(common_questions)} questions</b>.\n\n"
    )
    
    # Add category breakdown if available
    if category_scores:
        match_text += "<b>Category Breakdown:</b>\n"
        for category, cat_score in category_scores.items():
            cat_percentage = int(cat_score * 100)  # Convert cohesion score to percentage
            question_count = category_counts.get(category, 0)
            match_text += f"• <b>{category.title()}</b>: {cat_percentage}% ({question_count} questions)\n"
        match_text += "\n"
    
    match_text += "Would you like to connect with this person?"
    
    # Store the match info in state
    await state.update_data(
        pending_match_user_id=matched_user.telegram_id,
        pending_match_score=score,
        pending_match_common_questions=len(common_questions),
        pending_match_category_scores=category_scores,
        pending_match_category_counts=category_counts,
        has_pending_match=True,  # Flag to indicate user has a pending match
        pending_match_message_id=None,  # Will be set after sending the message
        pending_match_nickname=matched_user_nickname,
        pending_match_photo=matched_user_photo
    )
    
    # Create confirmation keyboard
    keyboard = get_match_confirmation_keyboard(matched_user.telegram_id)
    
    # Delete the waiting message
    await waiting_msg.delete()
    
    # Show confirmation message - with photo if available
    if matched_user_photo:
        try:
            match_message = await message.bot.send_photo(
                chat_id=message.chat.id,
                photo=matched_user_photo,
                caption=match_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            logger.info(f"Sent match photo for user {matched_user_id}")
        except Exception as e:
            logger.warning(f"Error sending match photo: {e}. Falling back to text-only message.")
            match_message = await message.answer(match_text, reply_markup=keyboard, parse_mode="HTML")
    else:
        match_message = await message.answer(match_text, reply_markup=keyboard, parse_mode="HTML")
    
    # Update the state with the match message ID
    await state.update_data(pending_match_message_id=match_message.message_id)
    
    # No need to update the menu or keyboard, just update state
    await state.set_state(QuestionFlow.viewing_question)


async def on_show_start_menu(message: types.Message, state: FSMContext) -> None:
    """Handle Main Menu button click."""
    # Clear the current group from state
    await state.update_data(current_group_id=None, current_group_name=None)
    
    # Reset the state
    await state.clear()
    
    # Show the welcome menu
    await show_welcome_menu(message)


async def on_add_question_callback(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Handle add question callback button."""
    await callback.answer()
    
    data = await state.get_data()
    group_id = data.get("current_group_id")
    group_name = data.get("current_group_name")
    
    if not group_id or not group_name:
        await callback.message.answer("Error: Could not determine your current group.")
        return
    
    # Set state to creating question
    await state.set_state(QuestionFlow.creating_question)
    
    # Store the menu message ID for later cleanup
    await state.update_data(menu_msg_id=callback.message.message_id)
    
    # Show group menu with add_question section highlighted
    await show_group_menu(callback.message, group_id, group_name, state, current_section="add_question", session=session)
    
    # Send prompt for the question
    prompt_msg = await callback.message.answer("Please ask your yes/no question:")
    await state.update_data(question_prompt_msg_id=prompt_msg.message_id)


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
    callback: types.CallbackQuery, state: FSMContext
) -> None:
    """
    Handles the callback when user presses the Find Match button.
    Retrieves user answers, finds best match, and shows match confirmation.
    """
    # Answer callback to close the loading indicator
    await callback.answer()
    
    # Store the message ID of the callback message (the one with Find a match button)
    await state.update_data(find_match_message_id=callback.message.message_id)
    
    # Clean up any previous messages
    data = await state.get_data()
    group_id = data.get("current_group_id")
    group_name = data.get("current_group_name", f"Team {group_id}")
    
    # Clean up any info messages
    for msg_id in [data.get("group_info_msg_id"), data.get("instructions_msg_id")]:
        if msg_id:
            try:
                await callback.bot.delete_message(callback.message.chat.id, msg_id)
            except Exception as e:
                logger.warning(f"Failed to delete message: {e}")
    
    # We no longer delete the group menu message - we keep it visible
    
    # Update state to reflect current section
    await state.update_data(current_section="matches")
    
    # Get required data from database
    user_id = callback.from_user.id
    user_tg_id = callback.from_user.id
    
    # Show "searching" message
    wait_message = await callback.message.answer("Searching for your best match... 🔍")
    
    async with async_session_factory() as session:
        # Check if user exists in database
        user = await get_user_by_tg_id(user_tg_id, session)
        if not user:
            logger.error(f"User {user_tg_id} not found in database during find match.")
            await wait_message.delete()
            error_msg = await callback.message.answer("⚠️ Error: Your profile data was not found. Please restart the bot with /start.")
            await show_group_menu(callback.message, group_id, group_name, state, current_section="questions", session=session)
            return
            
        # Check if user has enough points
        if user.points < FIND_MATCH_COST:
            logger.info(f"User {user_tg_id} tried to find match but has insufficient points ({user.points})")
            await wait_message.delete()
            await callback.message.answer(
                f"⚠️ You need {FIND_MATCH_COST} points to find a match. You currently have {user.points} points.",
                reply_markup=get_earn_points_keyboard()
            )
            await show_group_menu(callback.message, group_id, group_name, state, current_section="questions", session=session)
            return
            
        # Check if user has answered enough questions
        answer_repo = AnswerRepository()
        question_count = await answer_repo.get_user_answer_count(session, user.id)
        
        if question_count < MIN_QUESTIONS_FOR_MATCH:
            logger.info(f"User {user_tg_id} tried to find match but has only answered {question_count} questions")
            await wait_message.delete()
            await callback.message.answer(
                f"⚠️ You need to answer at least {MIN_QUESTIONS_FOR_MATCH} questions to find a match. "
                f"You've currently answered {question_count} questions."
            )
            await show_group_menu(callback.message, group_id, group_name, state, current_section="questions", session=session)
            return
            
        # Get user group information
        group_repo = GroupRepository()
        membership_repo = GroupMembershipRepository()
        
        # Get user's current group
        current_group = await membership_repo.get_current_group_for_user(session, user.id)
        if not current_group:
            logger.error(f"User {user_tg_id} has no current group during find match.")
            await wait_message.delete()
            await callback.message.answer("⚠️ Error: You are not assigned to any group. Please contact support.")
            await show_group_menu(callback.message, group_id, group_name, state, current_section="questions", session=session)
            return
            
        # Find best match
        try:
            best_match = await find_best_match(session, user.id)
        except Exception as e:
            logger.error(f"Error finding match for user {user_tg_id}: {e}")
            await wait_message.delete()
            await callback.message.answer("⚠️ An error occurred while finding your match. Please try again later.")
            await show_group_menu(callback.message, group_id, group_name, state, current_section="questions", session=session)
            return
            
        # Handle case when no match is found
        if not best_match:
            logger.info(f"No match found for user {user_tg_id}")
            await wait_message.delete()
            await callback.message.answer(
                "😔 We couldn't find a suitable match for you at this time. "
                "Please try again later or answer more questions to improve matching."
            )
            await show_group_menu(callback.message, group_id, group_name, state, current_section="questions", session=session)
            return
            
        # Deduct points for finding a match
        user.points -= FIND_MATCH_COST
        session.add(user)
        await session.commit()
        
        # Get matched user details
        matched_user = await get_user_by_id(best_match.matched_user_id, session)
        if not matched_user:
            logger.error(f"Matched user {best_match.matched_user_id} not found in database.")
            await wait_message.delete()
            await callback.message.answer("⚠️ An error occurred while retrieving match details. Please try again.")
            await show_group_menu(callback.message, group_id, group_name, state, current_section="questions", session=session)
            return
            
        # Format the match message
        percentage = round(best_match.similarity * 100)
        common_questions = best_match.common_questions
        
        # Get the matched user's nickname and photo from the GroupMember table
        matched_user_nickname = None
        matched_user_photo = None
        
        try:
            # Get the current group
            group_id = data.get("current_group_id")
            if group_id:
                # Get the group member record for the matched user
                group_member = await group_repo.get_group_member(session, matched_user.id, int(group_id))
                if group_member:
                    matched_user_nickname = getattr(group_member, "nickname", None)
                    matched_user_photo = getattr(group_member, "photo_file_id", None)
                    logger.info(f"Found nickname '{matched_user_nickname}' and photo '{matched_user_photo}' for matched user {matched_user.id}")
        except Exception as e:
            logger.warning(f"Error retrieving nickname/photo for matched user {matched_user.id}: {e}")
            # Continue without nickname/photo - this is not a critical error
        
        # Start constructing the message
        match_text = [
            f"🎯 <b>We found a match for you!</b>\n",
        ]
        
        # Use nickname if available, otherwise fall back to first name
        display_name = matched_user_nickname if matched_user_nickname else matched_user.first_name
        match_text.append(f"👤 <b>{display_name}</b> ({percentage}% match cohesion)")
        match_text.append(f"📋 Based on {common_questions} common questions\n")
        
        # Add category breakdown
        if best_match.category_scores:
            match_text.append("<b>Category breakdown:</b>")
            for category, score in best_match.category_scores.items():
                if category in best_match.category_counts and best_match.category_counts[category] > 0:
                    cat_percentage = round(score * 100)
                    count = best_match.category_counts[category]
                    match_text.append(f"• {category}: {cat_percentage}% ({count} Qs)")
                    
        # Create confirmation keyboard
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            types.InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_match:{matched_user.id}"),
            types.InlineKeyboardButton("❌ Cancel", callback_data="cancel_match")
        )
        
        # Delete wait message and show match confirmation
        await wait_message.delete()
        match_message = await callback.message.answer("\n".join(match_text), reply_markup=keyboard, parse_mode="HTML")
        
        # Update state with match information
        await state.update_data(
            has_pending_match=True,
            pending_match_user_id=matched_user.id,
            pending_match_score=best_match.similarity,
            pending_match_common_questions=best_match.common_questions,
            pending_match_category_scores=best_match.category_scores,
            pending_match_category_counts=best_match.category_counts,
            pending_match_message_id=match_message.message_id,
            pending_match_nickname=matched_user_nickname,
            pending_match_photo=matched_user_photo
        )
        
        # Display a single menu message with the balance - only do this once to avoid flickering
        await show_group_menu(callback.message, group_id, group_name, state, current_section="matches", session=session)
        
    return QuestionFlow.waiting


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
    """Register all start-related handlers."""
    # Command handlers - Register correctly for deep links
    from aiogram.filters import CommandObject
    
    # Register /start with and without arguments
    dp.message.register(cmd_start, Command("start"))
    dp.message.register(cmd_cancel, Command("cancel"))
    dp.message.register(cmd_clear_profile, Command("clear_profile"))
    
    # Callback handlers for team and group management
    dp.callback_query.register(on_create_team, F.data == "create_team")
    dp.callback_query.register(on_join_team, F.data == "join_team")
    dp.callback_query.register(on_cancel_join, F.data == "cancel_join")
    dp.callback_query.register(on_go_to_group, F.data.startswith("go_to_group:"))
    dp.callback_query.register(on_team_confirm, F.data == "confirm_team", TeamCreation.confirm_creation)
    dp.callback_query.register(on_team_cancel, F.data == "cancel_team", TeamCreation.confirm_creation)
    dp.callback_query.register(on_join_confirm, F.data.startswith("confirm_join:"))
    dp.callback_query.register(on_join_group_callback, F.data.startswith("join_group:"))
    dp.callback_query.register(on_confirm_leave_group, F.data.startswith("confirm_leave:"))
    dp.callback_query.register(on_cancel_leave_group, F.data.startswith("cancel_leave"))
    dp.callback_query.register(on_leave_group_callback, F.data.startswith("leave_group:"))
    dp.callback_query.register(on_manage_group_callback, F.data.startswith("manage_group:"))
    
    # Callback handlers for questions
    dp.callback_query.register(on_add_question_callback, F.data == "add_question")
    dp.callback_query.register(on_show_questions_callback, F.data == "show_questions")
    dp.callback_query.register(on_load_answered_questions, F.data == "load_answered_questions")
    dp.callback_query.register(on_use_corrected_text, F.data == "use_corrected_text")
    dp.callback_query.register(on_use_original_text, F.data == "use_original")
    dp.callback_query.register(on_confirm_add_question, F.data == "confirm_add_question", QuestionFlow.reviewing_question)
    dp.callback_query.register(on_cancel_add_question, F.data == "cancel_add_question")
    dp.callback_query.register(on_confirm_delete_question, F.data.startswith("confirm_delete_question:"), QuestionFlow.confirming_delete)
    dp.callback_query.register(on_cancel_delete_question, F.data.startswith("cancel_delete_question:"))
    dp.callback_query.register(on_delete_question_callback, F.data.startswith("delete_question:"))
    dp.callback_query.register(process_answer_callback, F.data.startswith("answer:"))
    dp.callback_query.register(on_skip_question, F.data.startswith("skip_question:"))
    
    # Callback handlers for matches and navigation
    dp.callback_query.register(on_find_match_callback, F.data == "find_match")
    dp.callback_query.register(handle_start_anon_chat, F.data.startswith("start_anon_chat:"))
    dp.callback_query.register(handle_cancel_match, F.data == "cancel_match")
    dp.callback_query.register(on_show_start_menu_callback, F.data == "show_start_menu")
    
    # Message handlers
    dp.message.register(on_find_match, F.text == "🔍 Find a match")
    dp.message.register(on_group_info, F.text == "📌 Group Info")
    dp.message.register(on_instructions, F.text == "📚 Instructions")
    
    # Register direct question entry handler for any text in viewing_question or answering states
    dp.message.register(handle_direct_question_entry, ~F.text.startswith("/"), QuestionFlow.viewing_question)
    dp.message.register(handle_direct_question_entry, ~F.text.startswith("/"), QuestionFlow.answering)
    
    # State handlers
    dp.message.register(process_team_name, TeamCreation.waiting_for_name)
    dp.message.register(process_team_description, TeamCreation.waiting_for_description)
    dp.message.register(process_invite_code, TeamJoining.waiting_for_code)
    dp.message.register(process_new_question_text, QuestionFlow.creating_question)
    
    # Onboarding handlers
    dp.message.register(process_group_nickname, GroupOnboarding.waiting_for_nickname)
    dp.message.register(process_group_photo, GroupOnboarding.waiting_for_photo)


async def process_invite_code(message: types.Message, state: FSMContext, session: AsyncSession) -> None:
    """Process invite code entered by user."""
    user_tg = message.from_user
    invite_code = message.text.strip()
    
    # Validate the code format
    if not invite_code.isalnum():
        await message.answer("Invalid invite code format. Please enter a valid code.")
        return
    
    # Look for group with this code
    group = await group_repo.get_by_invite_code(session, invite_code)
    if not group:
        await message.answer("Invalid invite code. Please check the code and try again.")
        return
    
    logger.info(f"User {user_tg.id} trying to join group {group.id} with invite code")
    
    # Get user from DB
    db_user = await user_repo.get_by_telegram_id(session, user_tg.id)
    if not db_user:
        logger.error(f"User {user_tg.id} not found in DB when processing invite code")
        await message.answer("Error: Could not find your user account. Please try /start again.")
        return
    
    # Check if user is already in this group
    is_member = await group_repo.is_user_in_group(session, db_user.id, group.id)
    if is_member:
        logger.info(f"User {user_tg.id} is already in group {group.id}")
        await message.answer(f"You are already a member of {group.name}.")
        
        # Set current group and go to questions
        await state.update_data(current_group_id=group.id, current_group_name=group.name)
        await state.set_state(QuestionFlow.viewing_question)
        await on_show_questions(message, state, session)
        return
    
    # Add user to group
    await group_repo.add_user_to_group(
        session, 
        user_id=db_user.id, 
        group_id=group.id, 
        role=MemberRole.MEMBER
    )
    
    logger.info(f"User {user_tg.id} joined group {group.id}")
    
    success_text = f"🎉 You've successfully joined <b>{group.name}</b>!"
    await message.answer(success_text, parse_mode="HTML")
    
    # Set current group and update state
    await state.update_data(current_group_id=group.id, current_group_name=group.name)
    await state.set_state(QuestionFlow.viewing_question)
    
    # Show group menu
    await show_group_menu(message, group.id, group.name, state, current_section="questions", session=session)
    
    # Show the first question immediately after joining
    await check_and_display_next_question(message, db_user, group.id, state, session)


async def on_delete_question_callback(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Handle delete question button."""
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


async def on_use_corrected_text(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Handle when user selects to use the corrected text."""
    user_data = await state.get_data()
    corrected_text = user_data.get("corrected_question_text", "")
    
    if not corrected_text:
        await callback.answer("Error: Corrected text not found", show_alert=True)
        return
    
    # Get message IDs for cleanup
    correction_msg_id = user_data.get("correction_msg_id")
    original_message_id = user_data.get("original_question_message_id")
    
    # Delete the correction message
    if callback.message and callback.message.message_id:
        try:
            await callback.message.delete()
        except Exception as e:
            logger.warning(f"Failed to delete correction message: {e}")
    
    # Save the corrected text and continue with the process
    await state.update_data(new_question_text=corrected_text)
    
    # Send confirmation
    confirmation_text = f"Your question (corrected):\n\n{corrected_text}\n\nIs this correct and ready to be added?"
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
    """Handle when user selects to use the original text."""
    user_data = await state.get_data()
    original_text = user_data.get("original_question_text", "")
    
    if not original_text:
        await callback.answer("Error: Original text not found", show_alert=True)
        return
    
    # Get message IDs for cleanup
    correction_msg_id = user_data.get("correction_msg_id")
    original_message_id = user_data.get("original_question_message_id")
    
    # Delete the correction message
    if callback.message and callback.message.message_id:
        try:
            await callback.message.delete()
        except Exception as e:
            logger.warning(f"Failed to delete correction message: {e}")
    
    # Save the original text and continue with the process
    await state.update_data(new_question_text=original_text)
    
    # Send confirmation
    confirmation_text = f"Your question (original):\n\n{original_text}\n\nIs this correct and ready to be added?"
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="✅ Yes", callback_data="confirm_add_question"),
            types.InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_add_question"),
        ]
    ])
    confirmation_message = await callback.message.answer(confirmation_text, reply_markup=keyboard)
    await state.update_data(confirmation_message_id=confirmation_message.message_id)
    await state.set_state(QuestionFlow.reviewing_question)


# Add a new function to handle direct question entry
async def handle_direct_question_entry(message: types.Message, state: FSMContext) -> None:
    """Handle when a user directly types a question without pressing Add Question."""
    # Make sure we're in a group context
    data = await state.get_data()
    group_id = data.get("current_group_id")
    group_name = data.get("current_group_name")
    
    if not group_id:
        await message.answer("Please join or create a team first before asking questions.")
        return
    
    # Transition to question creation flow
    await state.set_state(QuestionFlow.creating_question)
    await state.update_data(original_question_message_id=message.message_id)
    
    # Process the question text directly
    question_text = message.text.strip()
    if len(question_text) < 10:
        validation_msg = await message.answer("Your question seems a bit short. Please provide more detail.")
        await state.update_data(validation_msg_id=validation_msg.message_id)
        return
    if len(question_text) > 500:
        validation_msg = await message.answer("Your question is too long (max 500 characters). Please shorten it.")
        await state.update_data(validation_msg_id=validation_msg.message_id)
        return
    
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
    
    # Delete waiting message before showing confirmation
    try:
        await message.bot.delete_message(message.chat.id, waiting_msg.message_id)
    except Exception as e:
        logger.warning(f"Failed to delete waiting message: {e}")
        
    # Store the question text and ask for confirmation
    await state.update_data(new_question_text=question_text)
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


async def on_group_info(message: types.Message, state: FSMContext, session: AsyncSession) -> None:
    """Handle Group Info button click."""
    logger.info("Group Info button clicked")
    data = await state.get_data()
    group_id = data.get("current_group_id")
    
    if not group_id:
        logger.error(f"User {message.from_user.id} clicked Group Info but no group_id in state: {data}")
        await message.answer("Error: Could not determine your current group. Use /start to begin again.")
        return
    
    # Clean up any instruction or find match messages
    instructions_msg_id = data.get("instructions_msg_id")
    find_match_message_id = data.get("find_match_message_id")
    pending_match_message_id = data.get("pending_match_message_id")
    
    if instructions_msg_id:
        try:
            await message.bot.delete_message(message.chat.id, instructions_msg_id)
            await state.update_data(instructions_msg_id=None)
        except Exception as e:
            logger.warning(f"Failed to delete instructions message: {e}")
    
    if find_match_message_id:
        try:
            await message.bot.delete_message(message.chat.id, find_match_message_id)
            await state.update_data(find_match_message_id=None)
        except Exception as e:
            logger.warning(f"Failed to delete find match message: {e}")
            
    if pending_match_message_id:
        try:
            await message.bot.delete_message(message.chat.id, pending_match_message_id)
            await state.update_data(pending_match_message_id=None, has_pending_match=False)
        except Exception as e:
            logger.warning(f"Failed to delete pending match message: {e}")
    
    # Get group from DB
    group = await group_repo.get(session, group_id)
    if not group:
        logger.error(f"Group {group_id} not found in DB for user {message.from_user.id}")
        await message.answer("Error: Group not found. Please try /start again.")
        return
    
    logger.info(f"Displaying group info for group {group_id} ({group.name}) to user {message.from_user.id}")
    
    # Create an invite link for the group
    invite_payload = f"g{group.id}"
    invite_link = await create_start_link(message.bot, payload=invite_payload, encode=True)
    
    # Get user info
    user_id = message.from_user.id
    db_user = await user_repo.get_by_telegram_id(session, user_id)
    if not db_user:
        logger.error(f"User {user_id} not found in DB when showing group info")
        await message.answer("Error: Could not find your user account. Please try /start again.")
        return
    
    # Check if the user is the creator of the group
    is_creator = await group_repo.is_group_creator(session, db_user.id, group_id)
    
    # Get group description (default if not set)
    description = group.description or "No description available"
    
    # Create keyboard buttons
    keyboard_buttons = []
    
    # Always add leave group button
    keyboard_buttons.append([
        types.InlineKeyboardButton(text="❌ Leave the group", callback_data=f"leave_group:{group.id}")
    ])
    
    # Add manage group button only for the creator
    if is_creator:
        keyboard_buttons.append([
            types.InlineKeyboardButton(text="⚙️ Manage the group", callback_data=f"manage_group:{group.id}")
        ])
    
    # Create keyboard with buttons
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    # Create the info message
    info_text = (
        f"<b>{group.name}</b>\n\n"
        f"{description}\n\n"
        f"Share this link with others to invite them to your group:\n"
        f"{invite_link}"
    )
    
    # Store the message ID to clean it up later
    info_msg = await message.answer(info_text, reply_markup=keyboard, parse_mode="HTML")
    await state.update_data(group_info_msg_id=info_msg.message_id)


async def on_instructions(message: types.Message, state: FSMContext, session: AsyncSession = None) -> None:
    """Handle Instructions button click."""
    
    # Clean up any group info or find match messages
    data = await state.get_data()
    group_info_msg_id = data.get("group_info_msg_id")
    find_match_message_id = data.get("find_match_message_id")
    pending_match_message_id = data.get("pending_match_message_id")
    
    if group_info_msg_id:
        try:
            await message.bot.delete_message(message.chat.id, group_info_msg_id)
            await state.update_data(group_info_msg_id=None)
        except Exception as e:
            logger.warning(f"Failed to delete group info message: {e}")
    
    if find_match_message_id:
        try:
            await message.bot.delete_message(message.chat.id, find_match_message_id)
            await state.update_data(find_match_message_id=None)
        except Exception as e:
            logger.warning(f"Failed to delete find match message: {e}")
            
    if pending_match_message_id:
        try:
            await message.bot.delete_message(message.chat.id, pending_match_message_id)
            await state.update_data(pending_match_message_id=None, has_pending_match=False)
        except Exception as e:
            logger.warning(f"Failed to delete pending match message: {e}")
    
    instructions_text = (
        "📚 <b>How to Use Allkinds</b>\n\n"
        "<b>Asking Questions:</b>\n"
        "• Simply type your yes/no question in the chat\n"
        "• Each new question earns you 5💎 points\n\n"
        
        "<b>Answering Questions:</b>\n"
        "• Questions will appear in your feed\n"
        "• Tap the buttons to answer (👍👍, 👍, 👎, 👎👎)\n"
        "• Each answer earns you 1💎 point\n\n"
        
        "<b>Finding Matches:</b>\n"
        "• Tap 'Find a match' to discover team members with similar values\n"
        "• Finding a match costs 10💎 points\n"
        "• The more questions you answer, the better the matches!\n\n"
        
        "<b>Points System:</b>\n"
        "• Create a question: +5💎\n"
        "• Answer a question: +1💎\n"
        "• Find a match: -10💎\n\n"
        
        "Have questions or need help? Contact the administrators."
    )
    
    # Store the message ID to clean it up later
    instructions_msg = await message.answer(instructions_text, parse_mode="HTML")
    await state.update_data(instructions_msg_id=instructions_msg.message_id)


async def on_leave_group_callback(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Handle when user clicks Leave Group button."""
    await callback.answer()
    
    # Extract group ID from callback data
    group_id = int(callback.data.split(":")[1])
    
    # Get user from DB
    user_tg = callback.from_user
    db_user = await user_repo.get_by_telegram_id(session, user_tg.id)
    if not db_user:
        await callback.message.answer("Error: Could not find your user account.")
        return
    
    # Get group from DB
    group = await group_repo.get(session, group_id)
    if not group:
        await callback.message.answer("Error: Group not found.")
        return
    
    # Confirm leaving group
    confirm_text = f"Are you sure you want to leave {group.name}?\n\nYour answers will be deleted, but questions you've created will remain in the group."
    confirm_keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="✅ Yes, leave group", callback_data=f"confirm_leave:{group_id}"),
            types.InlineKeyboardButton(text="❌ No, stay", callback_data="cancel_leave")
        ]
    ])
    
    await callback.message.edit_text(confirm_text, reply_markup=confirm_keyboard)


async def on_confirm_leave_group(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Handle when user confirms leaving a group."""
    await callback.answer()
    
    # Extract group ID from callback data
    group_id = int(callback.data.split(":")[1])
    
    # Get user from DB
    user_tg = callback.from_user
    db_user = await user_repo.get_by_telegram_id(session, user_tg.id)
    if not db_user:
        await callback.message.answer("Error: Could not find your user account.")
        return
    
    # Get group from DB
    group = await group_repo.get(session, group_id)
    if not group:
        await callback.message.answer("Error: Group not found.")
        return
    
    try:
        # Clear nickname and photo data first (will be important if they rejoin)
        try:
            member = await group_repo.get_group_member(session, db_user.id, group_id)
            if member:
                # Record if they had profile data before for the message
                had_profile = bool(getattr(member, "nickname", None))
                
                # Clear their profile data
                from sqlalchemy import update
                stmt = update(GroupMember).where(
                    (GroupMember.user_id == db_user.id) & 
                    (GroupMember.group_id == group_id)
                ).values(
                    nickname=None,
                    photo_file_id=None
                )
                await session.execute(stmt)
                logger.info(f"Cleared profile data for user {db_user.id} in group {group_id}")
        except Exception as e:
            logger.error(f"Error clearing profile data: {e}")
            # Continue with removal even if clearing profile fails
        
        # Delete user's answers in this group
        deleted_count = await delete_user_answers_in_group(session, db_user.id, group_id)
        
        # Remove user from the group
        removed = await group_repo.remove_user_from_group(session, db_user.id, group_id)
        if not removed:
            await callback.message.answer("Error: Failed to remove you from the group.")
            return
        
        # Commit the changes
        await session.commit()
        
        # Show success message
        success_text = f"You have left {group.name}. {deleted_count} of your answers were deleted."
        await callback.message.edit_text(success_text)
        
        # Clear the group from state
        await state.update_data(current_group_id=None, current_group_name=None)
        
        # Show the welcome menu
        await show_welcome_menu(callback.message)
        
    except Exception as e:
        logger.error(f"Error leaving group: {e}")
        await callback.message.answer("Error: Failed to leave group. Please try again.")
        await session.rollback()


async def on_cancel_leave_group(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Handle when user cancels leaving a group."""
    await callback.answer("Staying in the group")
    
    # Get data from state
    data = await state.get_data()
    group_id = data.get("current_group_id")
    
    # Get group from DB
    group = await group_repo.get(session, group_id)
    if not group:
        await callback.message.answer("Error: Group not found.")
        return
    
    # Restore the group info message
    await on_group_info(callback.message, state, session)


async def on_manage_group_callback(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Handle when a creator clicks Manage Group button."""
    await callback.answer("Group management functionality is coming soon!")
    
    # No actual functionality yet, just acknowledge the click
    # In the future, this will show admin controls
    
    # Get data from state
    data = await state.get_data()
    group_id = int(callback.data.split(":")[1])
    
    # Get user from DB
    user_tg = callback.from_user
    db_user = await user_repo.get_by_telegram_id(session, user_tg.id)
    if not db_user:
        await callback.message.answer("Error: Could not find your user account.")
        return
    
    # Get group from DB
    group = await group_repo.get(session, group_id)
    if not group:
        await callback.message.answer("Error: Group not found.")
        return
    
    # Verify the user is the creator
    is_creator = await group_repo.is_group_creator(session, db_user.id, group_id)
    if not is_creator:
        await callback.message.answer("Error: Only the group creator can manage the group.")
        return
    
    # For now, just show a message about the upcoming feature
    coming_soon_text = (
        f"<b>Group Management for {group.name}</b>\n\n"
        f"Group management features are coming soon!\n\n"
        f"Future features will include:\n"
        f"• Editing group name and description\n"
        f"• Managing member permissions\n"
        f"• Moderating questions and answers\n"
        f"• Group analytics and insights"
    )
    
    # Show the message
    await callback.message.edit_text(coming_soon_text, parse_mode="HTML")


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
    await callback.answer()
    
    # Extract group ID from callback data
    group_id = int(callback.data.split(":")[1])
    
    # Get group details
    group = await group_repo.get(session, group_id)
    if not group:
        await callback.message.answer("Error: Team not found. Please try again.")
        return
    
    # Update state with group info
    await state.update_data(current_group_id=group_id, current_group_name=group.name)
    await state.set_state(QuestionFlow.viewing_question)
    
    # Log the action
    logger.info(f"User {callback.from_user.id} clicked Go to group button for group {group_id} ({group.name})")
    
    # Edit the original message to avoid having too many messages
    try:
        success_text = f"🎉 You're now in <b>{group.name}</b>!"
        await callback.message.edit_text(success_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        # If editing fails, send a new message
        await callback.message.answer(f"🎉 You're now in <b>{group.name}</b>!", parse_mode="HTML")
    
    # Show the group menu
    await show_group_menu(callback.message, group_id, group.name, state, session=session)
    
    # After showing the menu, trigger the questions view
    await on_show_questions(callback.message, state, session)


async def on_answer_error(callback: types.CallbackQuery, chat_id: int) -> None:
    """Handle error in answer processing."""
    try:
        await callback.answer("Sorry, there was an error processing your answer.")
        await callback.bot.send_message(chat_id, "Sorry, there was an error processing your answer.")
    except Exception as e:
        logger.error("Failed to send error message to user")


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
    
    data = await state.get_data()
    group_id = data.get("current_group_id")
    nickname = data.get("group_nickname")
    user_tg = message.from_user
    db_user = await user_repo.get_by_telegram_id(session, user_tg.id)
    
    logger.info(f"Processing photo for group {group_id}, user {user_tg.id}, nickname '{nickname}'")
    
    # Determine photo_file_id
    photo_file_id = None
    if message.photo:
        photo_file_id = message.photo[-1].file_id
        logger.info(f"Got photo with file_id: {photo_file_id}")
    elif message.text and message.text.strip().lower() == "/skip":
        logger.info(f"User skipped photo upload")
        photo_file_id = None
    else:
        logger.info(f"Invalid photo input: {message.content_type}")
        await message.answer("Please send a photo or type /skip:")
        return
    
    # Store nickname and photo in GroupMember
    logger.info(f"Saving profile for user {db_user.id} in group {group_id}: nickname='{nickname}', has_photo={bool(photo_file_id)}")
    try:
        await group_repo.set_member_profile(session, db_user.id, group_id, nickname, photo_file_id)
        await session.commit()  # Explicitly commit to ensure the profile is saved
        logger.info(f"Profile saved successfully")
    except Exception as e:
        logger.error(f"Error saving profile: {e}")
        await message.answer("Error saving your profile. Please try again or contact support.")
        return
    
    # Get group details
    group = await group_repo.get(session, group_id)
    
    # Onboarding complete, proceed to group content
    logger.info(f"Onboarding complete, proceeding to group content")
    await state.set_state(QuestionFlow.viewing_question)
    
    # Success message with welcome to the group
    welcome_text = f"🎉 You're all set! Welcome to <b>{group.name}</b>!"
    
    # Get user's points balance
    points = db_user.points if hasattr(db_user, 'points') else 0
    
    # Get the reply keyboard with points balance 
    reply_keyboard = get_group_menu_reply_keyboard(current_section="questions", balance=points)
    
    # Send welcome message with menu buttons
    await message.answer(welcome_text, reply_markup=reply_keyboard, parse_mode="HTML")
    
    # Get count of unanswered questions
    unanswered_count = await get_unanswered_question_count(session, db_user.id, group_id)
    
    # Get count of answered questions
    answers = await answer_repo.get_answers_for_user_in_group(session, db_user.id, group_id)
    answered_count = len(answers)
    
    # Add message about questions
    if unanswered_count > 0:
        await message.answer(f"You have {unanswered_count} questions to answer. Here's the first one:")
        # Display the first question (which won't trigger onboarding again)
        await check_and_display_next_question(message, db_user, group_id, state, session)
    else:
        await message.answer("You've answered all available questions in this group!")

