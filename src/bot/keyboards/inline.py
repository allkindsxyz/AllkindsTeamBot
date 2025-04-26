from aiogram import types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from src.db.models import AnswerType
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from loguru import logger


def get_question_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard for answering questions."""
    keyboard = [
        [
            InlineKeyboardButton(text="Strong No", callback_data="answer_strong_no"),
            InlineKeyboardButton(text="No", callback_data="answer_no"),
        ],
        [
            InlineKeyboardButton(text="Yes", callback_data="answer_yes"),
            InlineKeyboardButton(text="Strong Yes", callback_data="answer_strong_yes"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_start_menu_keyboard() -> types.InlineKeyboardMarkup:
    """Create keyboard for start welcome menu."""
    keyboard = [
        [
            types.InlineKeyboardButton(text="👥 Create a Team", callback_data="create_team"),
            types.InlineKeyboardButton(text="🔍 Join a Team", callback_data="join_team"),
        ]
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_group_menu_keyboard(current_section=None) -> types.InlineKeyboardMarkup:
    """Return keyboard for group menu with navigation buttons."""
    # Log the keyboard generation for debugging
    logger.debug(f"Creating group menu keyboard with current_section={current_section}")
    
    # Create buttons with visual indicator if selected
    questions_btn = types.InlineKeyboardButton(
        text="❓ Questions" if current_section != "questions" else "️▶️ Questions", 
        callback_data="show_questions"
    )
    
    add_question_btn = types.InlineKeyboardButton(
        text="➕ Add Question" if current_section != "add_question" else "▶️ Add Question", 
        callback_data="add_question"
    )
    
    matches_btn = types.InlineKeyboardButton(
        text="🤝 Matches" if current_section != "matches" else "▶️ Matches", 
        callback_data="find_match"  # Make sure this matches the handler registration
    )
    
    main_menu_btn = types.InlineKeyboardButton(
        text="🔙 Main Menu", 
        callback_data="show_start_menu"
    )
    
    # Create the keyboard
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [questions_btn, add_question_btn],
        [matches_btn, main_menu_btn]
    ])
    
    # Log the generated keyboard for debugging
    logger.debug(f"Generated keyboard with callbacks: show_questions, add_question, find_match, show_start_menu")
    
    return keyboard


def get_group_menu_reply_keyboard(current_section=None, balance=0) -> types.ReplyKeyboardMarkup:
    """Creates a persistent reply keyboard for the group menu."""
    builder = ReplyKeyboardBuilder()

    # Use plain text matching handler filters
    matches_text = "Find Match"

    # First row - only match button
    builder.row(
        types.KeyboardButton(text=matches_text)
    )
    
    # Second row - group info and instructions
    builder.row(
        types.KeyboardButton(text="Group Info"),
        types.KeyboardButton(text="Instructions")
    )
    
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=False)


def get_answer_keyboard_with_skip(question_id: int) -> types.InlineKeyboardMarkup:
    """Create keyboard with all answer options plus skip in a single row."""
    keyboard = [
        [
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
                callback_data=f"answer:{question_id}:skip"
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
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_match_confirmation_keyboard(matched_user_id: int, session_id: str = None, bot_username: str = None) -> types.InlineKeyboardMarkup:
    """
    Creates inline keyboard for match confirmation.
    If session_id is provided, creates a direct deep link button to the communicator bot.
    Otherwise, creates a button that triggers the start_anon_chat callback.
    """
    builder = InlineKeyboardBuilder()
    
    # If we have session_id and bot_username, create a direct deep link button
    if session_id and bot_username:
        deep_link = f"https://t.me/{bot_username}?start=chat_{session_id}"
        builder.button(
            text="Start Anonymous Chat",
            url=deep_link
        )
    else:
        # Otherwise, use the callback that will create the chat session first
        builder.button(
            text="Start Anonymous Chat",
            callback_data=f"start_anon_chat:{matched_user_id}"
        )
    
    builder.button(
        text="❌ Cancel",
        callback_data="cancel_match"
    )
    
    builder.adjust(1)  # Arrange buttons vertically
    return builder.as_markup() 