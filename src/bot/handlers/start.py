from aiogram import Dispatcher, F, types, Bot
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.utils.deep_linking import decode_payload, create_start_link
from loguru import logger
import base64
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

# from src.bot.config import bot_settings # No longer needed
from src.core.config import get_settings # Import main settings
from src.bot.keyboards.inline import (
    get_start_menu_keyboard, 
    get_group_menu_keyboard, 
    get_answer_keyboard_with_skip,
    get_group_menu_reply_keyboard
)
from src.bot.states import TeamCreation, TeamJoining, QuestionFlow
from src.core.openai_service import is_yes_no_question, check_duplicate_question, check_spelling
from src.db import get_session
from src.db.repositories import user_repo, question_repo, answer_repo, group_repo
from src.db.models import AnswerType # Import AnswerType enum

settings = get_settings()

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

    # TODO: Check if user belongs to any groups
    # For now, we'll use a placeholder - this should be replaced with actual database query
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
    await show_group_menu(callback.message, group_id, group.name, state)


async def show_group_menu(message: types.Message, group_id: int, group_name: str, state: FSMContext, edit: bool = False, current_section: str = None) -> None:
    """Shows the main menu for a user within a group."""
    await state.update_data(current_group_id=group_id, current_group_name=group_name)
    # Don't set viewing_question state here, let the specific action handler do it
    
    # Get the reply keyboard
    keyboard = get_group_menu_reply_keyboard()
    
    # Only show the full message if we're not coming from the questions view
    if current_section != "questions":
        text = f"You are in <b>{group_name}</b>. What would you like to do?"
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        # Use a minimal visible character that Telegram will accept
        await message.answer(".", reply_markup=keyboard)


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
    await show_group_menu(callback.message, group_id, group_name, state)
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
    
    # Set state to answering questions
    await state.set_state(QuestionFlow.answering)
    logger.info(f"Setting state to QuestionFlow.answering for question feed")
    
    # Get all questions for the group
    questions = await question_repo.get_group_questions(session, group_id)
    
    # Get user's answers for this group
    answers = await answer_repo.get_answers_for_user_in_group(session, db_user.id, group_id)
    
    # Create a map of question_id -> answer for quick lookup
    answer_map = {answer.question_id: answer for answer in answers}
    
    # Check if chat is private (DM) or group
    chat_id = message.chat.id
    
    # Send welcome message
    welcome_text = f"Questions for {group.name}:"
    await message.answer(welcome_text)
    
    # Track if user has any unanswered questions
    has_unanswered = False
    
    # Dictionary to track which message_id corresponds to which question_id
    message_question_map = {}
    
    # Iterate through questions and show to user
    for question in questions:
        # Check if user has answered this question
        answer = answer_map.get(question.id)
        is_author = question.author_id == db_user.id
        
        if answer:
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
            
            # Add a delay to ensure separation
            await asyncio.sleep(0.5)
        else:
            # User hasn't answered this question
            has_unanswered = True
            
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
            
            # Add a delay to ensure separation
            await asyncio.sleep(0.5)
    
    # Store the message_question_map in state for use by message deletion handler
    await state.update_data(message_question_map=message_question_map)
    logger.info(f"Stored mapping for {len(message_question_map)} messages to questions")
    
    # If no questions or all questions answered, show a message
    if not questions:
        await message.answer("There are no questions in this team yet. You can add one with the '➕ Add Question' button!")
    elif not has_unanswered:
        await message.answer("You've answered all the questions! You can add more with the '➕ Add Question' button.")
    
    # Show group menu with questions section highlighted
    await show_group_menu(message, group_id, group.name, state, edit=False, current_section="questions")


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
    # Extract question ID from callback data
    question_id = int(callback.data.split(":")[1])
    
    # Get user from DB
    user_tg = callback.from_user
    db_user = await user_repo.get_by_telegram_id(session, user_tg.id)
    if not db_user:
        await callback.answer("Error: Could not verify your identity.", show_alert=True)
        return
    
    # Verify user is the author of the question
    question = await question_repo.get(session, question_id)
    if not question:
        await callback.answer("This question no longer exists.", show_alert=True)
        return
    
    if question.author_id != db_user.id:
        await callback.answer("You can only delete questions you created.", show_alert=True)
        return
    
    # Ask for confirmation
    confirmation_text = "You're about to delete your question. This will remove it for everyone in the team. Are you sure?"
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="✅ Yes, delete", callback_data=f"confirm_delete_question:{question_id}"),
            types.InlineKeyboardButton(text="❌ No, keep", callback_data=f"cancel_delete_question:{question_id}"),
        ]
    ])
    
    # Edit the message to show confirmation
    await callback.message.edit_text(
        text=f"{question.text}\n\n{confirmation_text}",
        reply_markup=keyboard
    )
    await callback.answer()


async def on_confirm_delete_question(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Handle confirmation to delete a question."""
    await callback.answer("Processing...")
    
    # Extract question ID from callback data
    question_id = int(callback.data.split(":")[1])
    
    # Get user from DB
    user_tg = callback.from_user
    db_user = await user_repo.get_by_telegram_id(session, user_tg.id)
    if not db_user:
        await callback.message.edit_text("Error: Could not verify your identity. Please try again.")
        return
    
    # Verify user is the author of the question
    question = await question_repo.get(session, question_id)
    if not question:
        await callback.message.edit_text("This question no longer exists.")
        return
    
    if question.author_id != db_user.id:
        await callback.message.edit_text("You can only delete questions you created.")
        return
    
    # Delete the question
    try:
        # Mark question as inactive instead of hard delete
        await question_repo.mark_inactive(session, question_id)
        
        # Delete the message completely instead of showing a success message
        await callback.message.delete()
        logger.info(f"User {db_user.id} deleted their question {question_id}")
        
    except Exception as e:
        logger.error(f"Error deleting question {question_id}: {e}")
        await callback.message.edit_text("Error deleting the question. Please try again.")


async def on_cancel_delete_question(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Handle cancellation of question deletion."""
    await callback.answer("Deletion cancelled")
    
    # Extract question ID from callback data
    question_id = int(callback.data.split(":")[1])
    
    # Get the question
    question = await question_repo.get(session, question_id)
    if not question:
        await callback.message.edit_text("This question no longer exists.")
        return
    
    # Get user from DB
    user_tg = callback.from_user
    db_user = await user_repo.get_by_telegram_id(session, user_tg.id)
    if not db_user:
        # If we can't get user info, just remove the confirmation buttons
        await callback.message.edit_text(question.text)
        return
    
    # Check if user has already answered this question
    answer = await answer_repo.get_by_attribute(
        session,
        expression=(answer_repo.model.user_id == db_user.id) & 
                   (answer_repo.model.question_id == question_id)
    )
    
    if answer:
        # User already answered - show their current answer
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
        
        # Add action buttons
        keyboard_buttons = []
        # Answer button
        keyboard_buttons.append(
            types.InlineKeyboardButton(
                text=answer_display,
                callback_data=f"answer:{question_id}:toggle"
            )
        )
        
        # Delete button (only for authors)
        if question.author_id == db_user.id:
            keyboard_buttons.append(
                types.InlineKeyboardButton(
                    text="🗑️ Delete",
                    callback_data=f"delete_question:{question_id}"
                )
            )
            
        # Create the keyboard with the appropriate buttons
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[keyboard_buttons])
        
        # Restore the question with the user's answer
        await callback.message.edit_text(
            text=question.text,
            reply_markup=keyboard
        )
    else:
        # User hasn't answered - show answer options
        # Create keyboard with answer options
        answer_buttons = [
            types.InlineKeyboardButton(
                text="👎👎",
                callback_data=f"answer:{question_id}:{AnswerType.STRONG_NO.value}"
            ),
            types.InlineKeyboardButton(
                text="👎",
                callback_data=f"answer:{question_id}:{AnswerType.NO.value}"
            ),
            types.InlineKeyboardButton(
                text="⏭️",
                callback_data=f"skip_question:{question_id}"
            ),
            types.InlineKeyboardButton(
                text="👍",
                callback_data=f"answer:{question_id}:{AnswerType.YES.value}"
            ),
            types.InlineKeyboardButton(
                text="👍👍",
                callback_data=f"answer:{question_id}:{AnswerType.STRONG_YES.value}"
            )
        ]
        
        # Create a row for actions
        action_buttons = []
        
        # Delete button (only for authors)
        if question.author_id == db_user.id:
            action_buttons.append(
                types.InlineKeyboardButton(
                    text="🗑️ Delete",
                    callback_data=f"delete_question:{question_id}"
                )
            )
        
        # Create keyboard with answer options in first row and actions in second row
        keyboard_rows = [answer_buttons]
        if action_buttons:
            keyboard_rows.append(action_buttons)
            
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
        
        # Restore the question with answer options
        await callback.message.edit_text(
            text=question.text,
            reply_markup=keyboard
        )


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
    
    # Format the notification message with plain question text
    notification_text = (
        f"<b>📝 New Question in {group.name}</b>\n\n"
        f"{question.text}"
    )
    
    # Add answer buttons
    keyboard = get_answer_keyboard_with_skip(question_id)
    
    # Send to each member except the author
    for member in group_members:
        if member.user_id != question.author_id:
            try:
                # Get user's Telegram ID
                user = await user_repo.get(session, member.user_id)
                if user and user.telegram_id:
                    await bot.send_message(
                        chat_id=user.telegram_id,
                        text=notification_text,
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
                    logger.info(f"Sent question notification to user {user.telegram_id}")
            except Exception as e:
                logger.error(f"Failed to send question notification to user {member.user_id}: {e}")


# --- Placeholder handlers for question confirmation ---

async def process_new_question_text(message: types.Message, state: FSMContext, session: AsyncSession) -> None:
    """Handle the text entered by the user for a new question."""
    question_text = message.text.strip()
    user_id = message.from_user.id
    data = await state.get_data()
    group_id = data.get("current_group_id")
    
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
    
    # Check for spelling errors
    has_spelling_errors, corrected_text = await check_spelling(question_text)
    if has_spelling_errors:
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
        validation_msg = await message.answer("🙋‍♂️ Please ask a question that can be answered with Agree/Disagree.")
        await state.update_data(validation_msg_id=validation_msg.message_id)
        return
    
    # Check for duplicate questions
    is_duplicate, duplicate_text, duplicate_id = await check_duplicate_question(question_text, group_id, session)
    if is_duplicate:
        duplicate_msg = await message.answer(f"🔄 This seems similar to an existing question. Please try a different question.")
        await state.update_data(validation_msg_id=duplicate_msg.message_id)
        return
        
    # Store the question text, user's message ID, and ask for confirmation
    await state.update_data(
        new_question_text=question_text,
        original_question_message_id=message.message_id
    )
    confirmation_text = f"Your question:\n\n{question_text}\n\nIs this correct and ready to be added?"
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="✅ Yes, add it", callback_data="confirm_add_question"),
            types.InlineKeyboardButton(text="✏️ Edit", callback_data="edit_add_question"),
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
    original_question_message_id = user_data.get("original_question_message_id")
    confirmation_message_id = user_data.get("confirmation_message_id")
    validation_msg_id = user_data.get("validation_msg_id")
    
    if not question_text or not group_id:
        await callback.answer("Error: Missing question text or group ID", show_alert=True)
        return
    
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
        
        # Just acknowledge with a small popup
        await callback.answer("Question added successfully!")
        
        # Set state to viewing_question
        await state.set_state(QuestionFlow.viewing_question)
        
        # Delete the user's original message that contained the question text
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
            except Exception as e:
                logger.warning(f"Failed to delete confirmation message: {e}")
        elif confirmation_message_id:
            try:
                await callback.bot.delete_message(
                    chat_id=callback.message.chat.id,
                    message_id=confirmation_message_id
                )
            except Exception as e:
                logger.warning(f"Failed to delete confirmation message by ID: {e}")
        
        # Delete any validation messages
        if validation_msg_id:
            try:
                await callback.bot.delete_message(
                    chat_id=callback.message.chat.id,
                    message_id=validation_msg_id
                )
            except Exception as e:
                logger.warning(f"Failed to delete validation message: {e}")
        
        # Send notification to other group members
        await send_question_notification(callback.bot, new_question.id, group_id, session)
        
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
        await callback.bot.send_message(
            chat_id=callback.message.chat.id,
            text=new_question.text,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Error saving question: {e}")
        await callback.answer("Error saving your question. Please try again.", show_alert=True)


async def on_edit_add_question(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Handle user wanting to edit their question."""
    # Get message IDs for cleanup
    data = await state.get_data()
    original_question_message_id = data.get("original_question_message_id")
    confirmation_message_id = data.get("confirmation_message_id")
    validation_msg_id = data.get("validation_msg_id")
    
    # Set state back to creating question to allow edit
    await state.set_state(QuestionFlow.creating_question)
    
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
    
    # Send prompt to edit the question
    prompt_msg = await callback.message.answer("Please edit your question:")
    await state.update_data(question_prompt_msg_id=prompt_msg.message_id)
    
    # Acknowledge with a small popup
    await callback.answer("Edit your question")


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
        
        # Split by : to get parts
        parts = callback_data.split(":")
        if len(parts) < 3:
            logger.error(f"Invalid callback data format: {callback_data}")
            await callback.answer("Invalid callback data", show_alert=True)
            return
            
        _, question_id_str, answer_type_str = parts
        question_id = int(question_id_str)
        
        # Check if user is toggling the answer (clicked on the answer button)
        if answer_type_str == "toggle":
            logger.info(f"User {callback.from_user.id} toggling answer for question {question_id}")
            question = await question_repo.get(session, question_id)
            if not question:
                await callback.answer("Cannot find this question anymore.", show_alert=True)
                return
                
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
                        callback_data=f"delete_question:{question_id}"
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
             
        # Save the answer to the database
        try:
            saved_answer = await answer_repo.save_answer(
                session=session,
                user_id=db_user.id,
                question_id=question_id,
                answer_type=actual_answer_type,
                value=answer_value
            )
            await callback.answer("Answer saved! ✅")
            
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

            # Get the question data
            question = await question_repo.get(session, question_id)
            if question:
                # Create keyboard buttons
                keyboard_buttons = [
                    types.InlineKeyboardButton(
                        text=selected_button_display_text,
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
                single_button_keyboard = types.InlineKeyboardMarkup(inline_keyboard=[keyboard_buttons])
                
                # Edit the message to show the question text and the buttons
                await callback.message.edit_reply_markup(reply_markup=single_button_keyboard)
                
                logger.debug("Answer processed. Updated message with answer button and delete option if author.")
                
                # Store the message ID and question ID to handle toggling later
                await state.update_data(
                    last_answered_msg_id=callback.message.message_id,
                    last_answered_q_id=question_id,
                    is_showing_single_answer=True
                )
            else:
                 # Fallback if question fetch fails
                 await callback.message.edit_text("Answer saved! Question not found.")
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


async def show_beta_message(message: types.Message) -> None:
    """Show message about beta testing."""
    beta_text = (
        "🔬 <b>Beta Testing Mode</b>\n\n"
        "Thank you for your interest in Allkinds! The bot is currently in beta testing.\n\n"
        "To join, please contact the administrator for an invitation link."
    )
    
    # Add a button to contact admin
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="Contact Administrator", url="https://t.me/allkinds_admin")]
    ])
    
    await message.answer(beta_text, reply_markup=keyboard)


async def on_message_deleted(event, bot: Bot, state: FSMContext, session: AsyncSession) -> None:
    """
    NOTE: This function is currently not in use as Telegram Bot API doesn't support direct message deletion events.
    
    In the future, we could implement an alternative approach to track deleted messages, such as:
    1. Periodically checking if messages still exist
    2. Storing message IDs and timestamps, and inferring deletion
    3. Using application-specific buttons for deletion instead of relying on Telegram's deletion
    """
    logger.warning("Message deletion detection attempted, but Telegram Bot API doesn't provide this capability")
    logger.info("Consider implementing an alternative approach for tracking deleted questions")


def register_handlers(dp: Dispatcher) -> None:
    """Register start command handlers."""
    dp.message.register(cmd_start, Command("start"))
    
    # Register skip command for team description
    dp.message.register(
        process_team_description, # Handler first
        Command("skip"),         # Then filters
        TeamCreation.waiting_for_description # Then state
    )
    
    # Register callback handlers for initial start menu (allow from any state)
    dp.callback_query.register(on_create_team, F.data == "create_team")
    dp.callback_query.register(on_join_team, F.data == "join_team")
    dp.callback_query.register(on_cancel_join, F.data == "cancel_join")
    
    # Callbacks requiring specific states for team creation/joining
    dp.callback_query.register(on_team_confirm, F.data == "confirm_team", TeamCreation.confirm_creation)
    dp.callback_query.register(on_team_cancel, F.data == "cancel_team", TeamCreation.confirm_creation)
    dp.callback_query.register(
        on_join_confirm, # Handler first
        F.data.startswith("confirm_join:") # Filter
    )
    dp.callback_query.register(
        on_join_group_callback, # Handler first
        F.data.startswith("join_group:") # Filter
    )
    
    # Register menu callback handlers for group menu
    dp.callback_query.register(on_show_questions_callback, F.data == "show_questions")
    dp.callback_query.register(on_add_question_callback, F.data == "add_question")
    dp.callback_query.register(on_show_matches_callback, F.data == "show_matches")
    dp.callback_query.register(on_show_start_menu_callback, F.data == "show_start_menu")
    
    # Register text handlers for menu buttons
    dp.message.register(on_show_questions, F.text == "❓ Questions", QuestionFlow.viewing_question)
    dp.message.register(on_add_question, F.text == "➕ Add Question", QuestionFlow.viewing_question)
    dp.message.register(on_show_matches, F.text == "🤝 Matches", QuestionFlow.viewing_question)
    dp.message.register(on_show_start_menu_callback, F.text == "🔙 Main Menu", QuestionFlow.viewing_question)
    # Also support for answering questions state
    dp.message.register(on_show_questions, F.text == "❓ Questions", QuestionFlow.answering)
    dp.message.register(on_add_question, F.text == "➕ Add Question", QuestionFlow.answering)
    dp.message.register(on_show_matches, F.text == "🤝 Matches", QuestionFlow.answering)
    dp.message.register(on_show_start_menu_callback, F.text == "🔙 Main Menu", QuestionFlow.answering)

    # Register callback handlers for question confirmation
    dp.callback_query.register(on_confirm_add_question, F.data == "confirm_add_question", QuestionFlow.reviewing_question)
    dp.callback_query.register(on_edit_add_question, F.data == "edit_add_question", QuestionFlow.reviewing_question)
    dp.callback_query.register(on_cancel_add_question, F.data == "cancel_add_question", QuestionFlow.reviewing_question)

    # Register callback handler for answering questions - allow from any state
    dp.callback_query.register(process_answer_callback, F.data.startswith("answer:"))
    
    # Register handlers for question actions
    dp.callback_query.register(on_skip_question, F.data.startswith("skip_question:"))
    dp.callback_query.register(on_delete_question, F.data.startswith("delete_question:"))
    dp.callback_query.register(on_confirm_delete_question, F.data.startswith("confirm_delete_question:"))
    dp.callback_query.register(on_cancel_delete_question, F.data.startswith("cancel_delete_question:"))
    
    # Register handler for spacer buttons
    dp.callback_query.register(handle_spacer_callback, F.data.startswith("spacer:"))

    # Register message handlers for FSM states
    dp.message.register(process_team_name, TeamCreation.waiting_for_name)
    dp.message.register(process_team_description, TeamCreation.waiting_for_description)
    dp.message.register(process_join_code, TeamJoining.waiting_for_code)
    dp.message.register(process_new_question_text, QuestionFlow.creating_question)
    
    # Treat any text message in question states as a new question
    dp.message.register(process_any_text_as_question, F.text, QuestionFlow.viewing_question)
    dp.message.register(process_any_text_as_question, F.text, QuestionFlow.answering)

    # Register spelling correction handlers
    dp.callback_query.register(on_use_corrected_text, F.data == "use_corrected_text", QuestionFlow.choosing_correction)
    dp.callback_query.register(on_use_original_text, F.data == "use_original_text", QuestionFlow.choosing_correction)    


async def on_show_questions_callback(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Callback handler for show questions button."""
    await callback.answer()
    await on_show_questions(callback.message, state, session)


async def on_add_question_callback(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Callback handler for add question button."""
    # Just acknowledge with a small popup without text message
    await callback.answer()
    
    # Set state to creating question
    await state.set_state(QuestionFlow.creating_question)
    
    # Store original message ID (with the menu)
    await state.update_data(menu_msg_id=callback.message.message_id)
    
    # Replace with prompt and store the prompt message ID
    prompt_msg = await callback.message.edit_text("Please ask your yes/no question:")
    await state.update_data(question_prompt_msg_id=prompt_msg.message_id)


async def on_show_matches_callback(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Callback handler for show matches button."""
    await callback.answer()
    await on_show_matches(callback.message, state, session)


async def on_show_start_menu_callback(message: types.Message, state: FSMContext) -> None:
    """Handler for the 'Back' or 'Main Menu' button from group menu."""
    await state.clear() # Clear group context
    await show_welcome_menu(message)


async def handle_spacer_callback(callback: types.CallbackQuery) -> None:
    """Handle clicks on spacer buttons by doing nothing."""
    # Just acknowledge the callback without any action or notification
    await callback.answer()
    return


async def on_add_question(message: types.Message, state: FSMContext) -> None:
    """Handle add question button press."""
    # Set state to creating question
    await state.set_state(QuestionFlow.creating_question)
    
    # Store the original user message ID to delete later
    await state.update_data(add_question_user_msg_id=message.message_id)
    
    # Send prompt and store its message ID
    prompt_msg = await message.answer("Please ask your yes/no question:")
    await state.update_data(question_prompt_msg_id=prompt_msg.message_id)


async def on_show_matches(message: types.Message, state: FSMContext, session: AsyncSession) -> None:
    """Handle show matches button press."""
    user_id = message.from_user.id
    data = await state.get_data()
    group_id = data.get("current_group_id")
    group_name = data.get("current_group_name", f"Team {group_id}")
    
    await message.answer("Showing matches... (Not implemented yet)")
    
    # Show group menu with matches section highlighted
    await show_group_menu(message, group_id, group_name, state, edit=False, current_section="matches") 


async def process_any_text_as_question(message: types.Message, state: FSMContext, session: AsyncSession) -> None:
    """Treat any text message in question states as a new question."""
    # Skip if the message is a button press (these are already handled by specific handlers)
    if message.text in ["❓ Questions", "➕ Add Question", "🤝 Matches", "🔙 Main Menu"]:
        return
    
    # Get the current group from state
    data = await state.get_data()
    group_id = data.get("current_group_id")
    
    if not group_id:
        logger.error(f"User {message.from_user.id} submitted question but no group_id found in state.")
        await message.answer("Error: Could not determine your current group. Please go back to the main menu.")
        await state.clear()
        return
    
    question_text = message.text.strip()
    
    # Basic validation
    if len(question_text) < 10:
        validation_msg = await message.answer("Your question seems a bit short. Please provide more detail.")
        await state.update_data(validation_msg_id=validation_msg.message_id)
        return
    if len(question_text) > 500:
        validation_msg = await message.answer("Your question is too long (max 500 characters). Please shorten it.")
        await state.update_data(validation_msg_id=validation_msg.message_id)
        return
    
    # Check for spelling errors
    has_spelling_errors, corrected_text = await check_spelling(question_text)
    if has_spelling_errors:
        # Store both versions of the text
        await state.update_data(
            original_question_text=question_text,
            corrected_question_text=corrected_text,
            original_question_message_id=message.message_id
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
        await state.update_data(correction_msg_id=correction_msg.message_id)
        await state.set_state(QuestionFlow.choosing_correction)
        return
    
    # Check if it's a yes/no question using OpenAI
    is_yes_no, yes_no_reason = await is_yes_no_question(question_text)
    if not is_yes_no:
        validation_msg = await message.answer("🙋‍♂️ Please ask a question that can be answered with Agree/Disagree.")
        await state.update_data(validation_msg_id=validation_msg.message_id)
        return
    
    # Check for duplicate questions
    is_duplicate, duplicate_text, duplicate_id = await check_duplicate_question(question_text, group_id, session)
    if is_duplicate:
        duplicate_msg = await message.answer(f"🔄 This seems similar to an existing question. Please try a different question.")
        await state.update_data(validation_msg_id=duplicate_msg.message_id)
        return
    
    # Store the message text as the question text
    await state.update_data(
        new_question_text=question_text,
        original_question_message_id=message.message_id
    )
    
    # Show confirmation dialog
    confirmation_text = f"Your question:\n\n{question_text}\n\nIs this correct and ready to be added?"
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="✅ Yes, add it", callback_data="confirm_add_question"),
            types.InlineKeyboardButton(text="✏️ Edit", callback_data="edit_add_question"),
            types.InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_add_question"),
        ]
    ])
    
    confirmation_message = await message.answer(confirmation_text, reply_markup=keyboard)
    await state.update_data(confirmation_message_id=confirmation_message.message_id)
    await state.set_state(QuestionFlow.reviewing_question)


async def on_use_corrected_text(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Handle when user accepts the corrected text version."""
    await callback.answer("Using corrected text")
    
    # Get state data
    data = await state.get_data()
    corrected_text = data.get("corrected_question_text")
    group_id = data.get("current_group_id")
    original_msg_id = data.get("original_question_message_id")
    correction_msg_id = data.get("correction_msg_id")
    
    # Clean up correction message
    if callback.message and callback.message.message_id:
        try:
            await callback.message.delete()
        except Exception as e:
            logger.warning(f"Failed to delete correction message: {e}")
    
    # Store the corrected text for confirmation
    await state.update_data(new_question_text=corrected_text)
    
    # Show confirmation dialog with corrected text
    confirmation_text = f"Your question:\n\n{corrected_text}\n\nIs this correct and ready to be added?"
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="✅ Yes, add it", callback_data="confirm_add_question"),
            types.InlineKeyboardButton(text="✏️ Edit", callback_data="edit_add_question"),
            types.InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_add_question"),
        ]
    ])
    
    confirmation_message = await callback.message.answer(confirmation_text, reply_markup=keyboard)
    await state.update_data(confirmation_message_id=confirmation_message.message_id)
    await state.set_state(QuestionFlow.reviewing_question)


async def on_use_original_text(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Handle when user rejects the corrected text and wants to use original."""
    await callback.answer("Using original text")
    
    # Get state data
    data = await state.get_data()
    original_text = data.get("original_question_text")
    group_id = data.get("current_group_id")
    original_msg_id = data.get("original_question_message_id")
    correction_msg_id = data.get("correction_msg_id")
    
    # Clean up correction message
    if callback.message and callback.message.message_id:
        try:
            await callback.message.delete()
        except Exception as e:
            logger.warning(f"Failed to delete correction message: {e}")
    
    # Store the original text for confirmation
    await state.update_data(new_question_text=original_text)
    
    # Show confirmation dialog with original text
    confirmation_text = f"Your question:\n\n{original_text}\n\nIs this correct and ready to be added?"
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="✅ Yes, add it", callback_data="confirm_add_question"),
            types.InlineKeyboardButton(text="✏️ Edit", callback_data="edit_add_question"),
            types.InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_add_question"),
        ]
    ])
    
    confirmation_message = await callback.message.answer(confirmation_text, reply_markup=keyboard)
    await state.update_data(confirmation_message_id=confirmation_message.message_id)
    await state.set_state(QuestionFlow.reviewing_question)
