from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_group_menu_keyboard(group_id: int, current_section: str = None, show_manage: bool = False):
    """Create the keyboard for the main group menu with the correct callback data."""
    buttons = []
    
    # Questions and Matches buttons (first row)
    questions_button = InlineKeyboardButton(
        text="💬 Questions" if current_section != "questions" else "• 💬 Questions •",
        callback_data="show_questions"
    )
    
    matches_button = InlineKeyboardButton(
        text="💞 Find Match" if current_section != "matches" else "• 💞 Find Match •",
        callback_data="find_match"  # Ensure this is exactly "find_match"
    )
    
    buttons.append([questions_button, matches_button])
    
    # Add question and Info buttons (second row)
    add_question_button = InlineKeyboardButton(
        text="➕ Add Question" if current_section != "add_question" else "• ➕ Add Question •",
        callback_data="add_question"
    )
    
    group_info_button = InlineKeyboardButton(
        text="ℹ️ Group Info" if current_section != "group_info" else "• ℹ️ Group Info •",
        callback_data=f"group_info:{group_id}"
    )
    
    buttons.append([add_question_button, group_info_button])
    
    # Return to main menu (third row)
    buttons.append([InlineKeyboardButton(
        text="🏠 Main Menu",
        callback_data="show_start_menu"
    )])
    
    # Add management button if requested (fourth row)
    if show_manage:
        buttons.append([InlineKeyboardButton(
            text="⚙️ Manage Group",
            callback_data=f"manage_group:{group_id}"
        )])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons) 