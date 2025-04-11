from aiogram import Dispatcher, F, types, Bot
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.utils.deep_linking import decode_payload, create_start_link
from loguru import logger
import base64
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete

# from src.bot.config import bot_settings # No longer needed
from src.core.config import get_settings # Import main settings
from src.bot.keyboards.inline import (
    get_start_menu_keyboard, 
    get_group_menu_keyboard, 
    get_answer_keyboard_with_skip,
    get_group_menu_reply_keyboard,
    get_match_confirmation_keyboard # Import keyboard function (will create next)
)
from src.bot.states import TeamCreation, TeamJoining, QuestionFlow, MatchingStates
from src.core.openai_service import is_yes_no_question, check_duplicate_question, check_spelling
from src.db import get_session
from src.db.repositories import user_repo, question_repo, answer_repo, group_repo
from src.db.models import Answer, User, AnswerType, MemberRole, Question
from src.bot.utils.matching import find_best_match

settings = get_settings() # Get settings from config

# Define the mapping for answer values
ANSWER_VALUES = {
    "strong_no": -2,
    "no": -1,
    "skip": 0, # Special case for skip
    "yes": 1,
    "strong_yes": 2,
}


async def cmd_start(message: types.Message, command: CommandObject = None, state: FSMContext = None, session: AsyncSession = None) -> None:
    """
    Handle /start command.
    If user is already in a group state, shows group menu.
    Supports deep linking with group ID or shows main menu if started directly.
    """
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
        # User is already in some group, go to the first one
        group = user_groups[0]  # Take the first group
        logger.info(f"User {user_tg.id} is in group {group.id}. Going directly to questions.")
        await state.update_data(current_group_id=group.id, current_group_name=group.name)
        await state.set_state(QuestionFlow.viewing_question)
        await on_show_questions(message, state, session)
    else:
        # User is not in any group, show beta testing message
        logger.info(f"User {user_tg.id} is not in any groups. Showing beta testing message.")
        await show_beta_message(message)


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
        "This bot helps you find people who share your values.\n\n"
        "How it works:\n"
        "1. Join or create a Team\n"
        "2. Answer yes/no questions about your values\n"
        "3. Get matched with people who have similar answers\n\n"
        "What would you like to do?"
    )
    
    # Get the keyboard with "Create a Team" and "Join a Team" buttons
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
            f"Use /questions to start creating questions for your team!"
        )
        
        logger.info(f"Created team '{team_name}' with ID {new_group.id}, invite link: {invite_link}")
        
        await callback.message.answer(success_text)
        
    except Exception as e:
        logger.error(f"Error creating group: {e}")
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
    
    # Show the group menu
    await state.update_data(current_group_id=group_id, current_group_name=group.name)
    await state.set_state(QuestionFlow.viewing_question)
    await show_group_menu(callback.message, group_id, group.name, state, session=session)


async def show_group_menu(message: types.Message, group_id: int, group_name: str, state: FSMContext, edit: bool = False, current_section: str = None, session: AsyncSession = None) -> None:
    """Shows the main menu for a user within a group."""
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
    
    # For matches section, just show the balance
    if current_section == "matches":
        menu_msg = await message.answer(points_text, reply_markup=keyboard)
        await state.update_data(group_menu_msg_id=menu_msg.message_id)
    # Only show the full message if we're not coming from the questions view
    elif current_section != "questions":
        text = f"You are in <b>{group_name}</b>.\n{points_text}\nWhat would you like to do?"
        menu_msg = await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        # Store message ID in state so we can delete it later if needed
        await state.update_data(group_menu_msg_id=menu_msg.message_id)
    else:
        # Use a minimal visible character that Telegram will accept
        menu_msg = await message.answer(".", reply_markup=keyboard)
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
    
    # Add user to the group as a member
    try:
        await group_repo.add_user_to_group(session, db_user.id, group_id)
        logger.info(f"Added user {db_user.id} to group {group_id} as a member")
    except Exception as e:
        logger.error(f"Error adding user to group: {e}")
        await callback.message.answer("Error joining the team. Please try again.")
        return
    
    await state.update_data(
        current_group_id=group_id,
        current_group_name=group_name
    )
    
    success_text = f"🎉 You've successfully joined <b>{group_name}</b>!\n"
    logger.info(f"User {callback.from_user.id} joined group {group_id} ({group_name})")
    
    # Edit the original message to show success, then show group menu
    await callback.message.edit_text(success_text)
    await show_group_menu(callback.message, group_id, group_name, state, session=session)
    await state.set_state(QuestionFlow.viewing_question) # Set default state after showing menu


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
        
        # Create keyboard buttons
        keyboard_buttons = [
            types.InlineKeyboardButton(
                text="⏭️",
                callback_data=f"answer:{question_id}:toggle"
            )
        ]
        
        # Add delete button if user is the author
        if question.author_id == db_user.id:
            keyboard_buttons.append(
                types.InlineKeyboardButton(
                    text="🗑️ Delete",
                    callback_data=f"delete_question:{question_id}"
                )
            )
        
        # Create the keyboard with the appropriate buttons
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[keyboard_buttons])
        
        # Edit the message to show the skipped status with delete button if author
        await callback.message.edit_reply_markup(reply_markup=keyboard)
        
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
    
    # Check if user is the author of the question
    if question.author_id != db_user.id:
        await callback.message.edit_text("You can only delete questions you created.")
        return
    
    # Delete the question
    await question_repo.delete(session, question_id)
    await session.commit()
    
    # Log the deletion
    logger.info(f"User {db_user.id} deleted question {question_id}")
    
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
    Restores the original question display.
    """
    await callback.answer("Cancelled")
    
    # Extract question ID from callback data
    question_id = int(callback.data.split(":")[1])
    
    # Get the question from the database
    question = await question_repo.get(session, question_id)
    if not question:
        await callback.message.edit_text("This question no longer exists.")
        return
    
    # Recreate the original question display
    # First check if user has answered this question
    user_tg = callback.from_user
    db_user = await user_repo.get_by_telegram_id(session, user_tg.id)
    if not db_user:
        await callback.message.edit_text("Error: Could not find your user account.")
        return
    
    # Get user's answer if any
    user_answer = await answer_repo.get_answer_by_question_and_user(
        session, 
        question_id=question_id,
        user_id=db_user.id
    )
    
    # Create action buttons based on whether user is the author
    action_buttons = []
    if question.author_id == db_user.id:
        # Author can delete
        action_buttons.append(
            types.InlineKeyboardButton(
                text="🗑️ Delete",
                callback_data=f"delete_question:{question_id}"
            )
        )
    
    # Create answer buttons
    answer_buttons = []
    if not user_answer:
        # User hasn't answered yet, show answer options
        answer_buttons = [
            [
                types.InlineKeyboardButton(
                    text="--",
                    callback_data=f"answer:{question_id}:-2"
                ),
                types.InlineKeyboardButton(
                    text="-",
                    callback_data=f"answer:{question_id}:-1"
                ),
                types.InlineKeyboardButton(
                    text="+",
                    callback_data=f"answer:{question_id}:1"
                ),
                types.InlineKeyboardButton(
                    text="++",
                    callback_data=f"answer:{question_id}:2"
                ),
            ],
            [
                types.InlineKeyboardButton(
                    text="Skip",
                    callback_data=f"skip_question:{question_id}"
                )
            ]
        ]
    else:
        # User has answered, show their answer
        answer_text = {
            -2: "Strong No (--)",
            -1: "No (-)",
            1: "Yes (+)",
            2: "Strong Yes (++)"
        }.get(user_answer.value, "Unknown")
        
        answer_buttons = [
            [
                types.InlineKeyboardButton(
                    text=f"Your answer: {answer_text}",
                    callback_data=f"dummy:{question_id}"
                )
            ]
        ]
    
    # Combine all buttons
    keyboard_buttons = answer_buttons
    if action_buttons:
        keyboard_buttons.append(action_buttons)
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    # Update the message to show the original question again
    await callback.message.edit_text(
        text=question.text,
        reply_markup=keyboard
    )
    
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
    
    # Format the notification message with plain question text
    notification_text = (
        f"<b>📝 New Question in {group.name}</b>\n\n"
        f"{question.text}"
    )
    
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
    