#!/usr/bin/env python3

minimal_content = '''from aiogram import types, Bot
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.utils.deep_linking import decode_payload, create_start_link
from loguru import logger
import base64
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from src.core.config import get_settings
from src.bot.keyboards.inline import (
    get_start_menu_keyboard,
    get_group_menu_keyboard,
    get_answer_keyboard_with_skip,
    get_group_menu_reply_keyboard,
    get_match_confirmation_keyboard
)
from src.bot.states import TeamCreation, TeamJoining, QuestionFlow, MatchingStates
from src.core.openai_service import is_yes_no_question, check_duplicate_question, check_spelling
from src.db.repositories import user_repo, question_repo, answer_repo, group_repo
from src.bot.utils.matching import find_best_match

# Get settings from config
settings = get_settings()

# Define the mapping for answer values
ANSWER_VALUES = {
    "strong_no": -2,
    "no": -1,
    "skip": 0, # Special case for skip
    "yes": 1,
    "strong_yes": 2,
}

# Start command handler
async def cmd_start(message: types.Message, command: CommandObject = None, state: FSMContext = None, session: AsyncSession = None) -> None:
    """
    Handle /start command and deep linking.
    """
    user_tg = message.from_user
    logger.info(f"User {user_tg.id} started the bot")
    
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

# Basic navigation
async def on_create_team(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Handle create team button callback."""
    await callback.answer("Create team feature coming soon!")
    await show_welcome_menu(callback.message)
    
async def on_join_team(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Handle join team button callback."""
    await callback.answer("Join team feature coming soon!")
    await show_welcome_menu(callback.message)

# Handler registration
def register_handlers(dp) -> None:
    """Register all handlers."""
    # Start command
    dp.message.register(cmd_start, Command("start"))
    
    # Basic navigation
    dp.callback_query.register(on_create_team, lambda c: c.data == "create_team")
    dp.callback_query.register(on_join_team, lambda c: c.data == "join_team")
'''

# Backup current file
import time
from pathlib import Path

file_path = Path("src/bot/handlers/start.py")
backup_path = f"{file_path}.bak_{int(time.time())}"

with open(file_path, 'r') as source, open(backup_path, 'w') as dest:
    dest.write(source.read())
print(f"Backed up current file to {backup_path}")

# Write minimal content
with open(file_path, 'w') as f:
    f.write(minimal_content)
print(f"Wrote minimal content to {file_path}") 