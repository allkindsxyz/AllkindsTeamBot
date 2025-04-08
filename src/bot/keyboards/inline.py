from aiogram import types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from src.db.models import AnswerType
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder


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
    # Create buttons with one disabled if it matches current_section
    questions_btn = types.InlineKeyboardButton(
        text="❓ Questions" if current_section != "questions" else "️▶️ Questions", 
        callback_data="show_questions"
    )
    questions_btn.disable = current_section == "questions"
    
    add_question_btn = types.InlineKeyboardButton(
        text="➕ Add Question" if current_section != "add_question" else "▶️ Add Question", 
        callback_data="add_question"
    )
    add_question_btn.disable = current_section == "add_question"
    
    matches_btn = types.InlineKeyboardButton(
        text="🤝 Matches" if current_section != "matches" else "▶️ Matches", 
        callback_data="show_matches"
    )
    matches_btn.disable = current_section == "matches"
    
    main_menu_btn = types.InlineKeyboardButton(
        text="🔙 Main Menu", 
        callback_data="show_start_menu"
    )
    
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [questions_btn, add_question_btn],
        [matches_btn, main_menu_btn]
    ])


def get_group_menu_reply_keyboard(current_section=None) -> types.ReplyKeyboardMarkup:
    """Creates a persistent reply keyboard for the group menu."""
    builder = ReplyKeyboardBuilder()

    # Define button texts based on current section
    questions_text = "▶️ Questions" if current_section == "questions" else "❓ Questions"
    add_question_text = "▶️ Add Question" if current_section == "add_question" else "➕ Add Question"
    matches_text = "▶️ Find a match" if current_section == "matches" else "🔍 Find a match"

    builder.row(
        types.KeyboardButton(text=questions_text),
        types.KeyboardButton(text=add_question_text)
    )
    builder.row(
        types.KeyboardButton(text=matches_text),
        types.KeyboardButton(text="🔙 Main Menu")
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


def get_match_confirmation_keyboard(matched_user_id: int) -> types.InlineKeyboardMarkup:
    """Creates inline keyboard with Go to chat and Cancel buttons."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="💬 Go to anonymous chat",
        callback_data=f"start_anon_chat:{matched_user_id}"
    )
    builder.button(
        text="❌ Cancel",
        callback_data="cancel_match"
    )
    builder.adjust(1) # Arrange buttons vertically
    return builder.as_markup() 