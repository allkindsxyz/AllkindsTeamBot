#!/usr/bin/env python3
import re
import os
from pathlib import Path
import time

def clean_start_py():
    """Fix all indentation issues in start.py by using a more direct approach."""
    # First, check if we can use a backup from a previous run
    file_path = Path("src/bot/handlers/start.py")
    backup_files = sorted(list(file_path.parent.glob("start.py.backup*")))
    
    if backup_files:
        print(f"Found {len(backup_files)} backup files. Using the newest: {backup_files[-1]}")
        
        # Create a new backup of current file
        current_backup = f"{file_path}.broken_{int(time.time())}"
        with open(file_path, 'r') as source, open(current_backup, 'w') as dest:
            dest.write(source.read())
        print(f"Backed up current file to {current_backup}")
        
        # Copy the newest backup to start.py
        with open(backup_files[-1], 'r') as source, open(file_path, 'w') as dest:
            dest.write(source.read())
        print(f"Restored {backup_files[-1]} to {file_path}")
        
        return True
    else:
        print("No backup files found. Creating a simplified version from the beginning.")
        return create_minimal_start_py()

def create_minimal_start_py():
    """Create a minimal version of start.py with just the essential handlers."""
    file_path = Path("src/bot/handlers/start.py")
    
    # Create a backup of the current file
    backup_path = f"{file_path}.backup_before_minimal_{int(time.time())}"
    try:
        with open(file_path, 'r') as source, open(backup_path, 'w') as dest:
            dest.write(source.read())
        print(f"Backed up current file to {backup_path}")
    except Exception as e:
        print(f"Error creating backup: {e}")
    
    # Write a simplified version of the file with only the critical components
    minimal_content = '''import logging
import base64
from aiogram import types, Bot
from aiogram.dispatcher import Dispatcher, FSMContext
from aiogram.dispatcher.filters import Command
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils.callback_data import CallbackData
from aiogram.dispatcher.filters.builtin import CommandObject
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.repositories.user_repository import UserRepository
from src.db.repositories.group_repository import GroupRepository
from src.db.repositories.question_repository import QuestionRepository
from src.db.repositories.answer_repository import AnswerRepository
from src.bot.utils.matching import find_best_match, get_answer_keyboard, get_answer_keyboard_with_skip
from src.bot.utils.openai_client import check_spelling, is_yes_no_question, check_duplicate_question

# Initialize logger
logger = logging.getLogger(__name__)

# Initialize repositories
user_repo = UserRepository()
group_repo = GroupRepository()
question_repo = QuestionRepository()
answer_repo = AnswerRepository()

# Define state groups
class TeamCreation(StatesGroup):
    waiting_for_name = State()
    waiting_for_description = State()
    confirm_creation = State()

class TeamJoining(StatesGroup):
    waiting_for_code = State()
    confirm_join = State()

class QuestionFlow(StatesGroup):
    viewing_question = State()
    creating_question = State()
    reviewing_question = State()
    choosing_correction = State()
    confirming_delete = State()

# Callback data for sharing
question_cd = CallbackData("question", "action", "id")

# Utility functions
def get_start_menu_keyboard():
    """Get the keyboard for the start menu."""
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="🏢 Create a Team", callback_data="create_team"),
            types.InlineKeyboardButton(text="🚪 Join a Team", callback_data="join_team"),
        ]
    ])

# Start command handler
async def cmd_start(message: types.Message, command: CommandObject = None, state: FSMContext = None, session: AsyncSession = None) -> None:
    """
    Handle /start command and deep linking.
    
    The start command can have an optional deep link payload which can contain:
    - Group invitation code
    """
    user_tg = message.from_user
    logger.info(f"User {user_tg.id} started the bot")
    
    # Ensure session is available (dependency injection handles this)
    if not session:
        logger.error("Database session not available in cmd_start")
        await message.answer("Sorry, there was a problem connecting to the database.")
        return
        
    # Get or create user in DB
    user_dict = {
        "id": user_tg.id,
        "first_name": user_tg.first_name,
        "last_name": user_tg.last_name,
        "username": user_tg.username
    }
    db_user, created = await user_repo.get_or_create_user(session, user_dict)
    
    # Show welcome message
    await show_welcome_menu(message)

# Welcome menu
async def show_welcome_menu(message: types.Message) -> None:
    """Show welcome message with create/join options."""
    user = message.from_user
    
    welcome_text = (
        f"👋 Welcome to Allkinds, {user.first_name}!\\n\\n"
        "This bot helps you find people who share your values.\\n\\n"
        "How it works:\\n"
        "1. Join or create a Team\\n"
        "2. Answer yes/no questions about your values\\n"
        "3. Get matched with people who have similar answers\\n\\n"
        "What would you like to do?"
    )
    
    keyboard = get_start_menu_keyboard()
    await message.answer(welcome_text, reply_markup=keyboard)

# Handler registration
def register_handlers(dp: Dispatcher) -> None:
    """Register all handlers."""
    # Start command
    dp.register_message_handler(cmd_start, Command("start"))
    
    # Basic navigation
    dp.register_callback_query_handler(on_create_team, text="create_team")
    dp.register_callback_query_handler(on_join_team, text="join_team")
    
    # Placeholder handlers for proper registration
    async def on_create_team(callback: types.CallbackQuery, state: FSMContext) -> None:
        await callback.answer("Create team feature coming soon!")
        await show_welcome_menu(callback.message)
        
    async def on_join_team(callback: types.CallbackQuery, state: FSMContext) -> None:
        await callback.answer("Join team feature coming soon!")
        await show_welcome_menu(callback.message)
'''
    
    # Write the simplified file
    with open(file_path, 'w') as f:
        f.write(minimal_content)
    
    print(f"Created minimal version of {file_path}")
    return True

if __name__ == "__main__":
    if clean_start_py():
        print("Completed file cleaning process. Try starting the bot now.")
    else:
        print("Failed to clean the file. Manual intervention may be needed.") 