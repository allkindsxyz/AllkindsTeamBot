import logging
from aiogram import types, Dispatcher
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.db.models import User

logger = logging.getLogger(__name__)

# Define admin states
class AdminStates(StatesGroup):
    awaiting_choice = State()
    confirm_data_deletion = State()

async def is_user_admin(user_id: int, session: AsyncSession) -> bool:
    """Check if the user is an admin."""
    settings = get_settings()
    
    # First check if the user is in the ADMIN_IDS list from settings
    if user_id in settings.ADMIN_IDS:
        return True
    
    # Then check the database
    from sqlalchemy import select
    query = select(User).where(User.telegram_id == user_id, User.is_admin == True)
    result = await session.execute(query)
    user = result.scalar_one_or_none()
    return user is not None

async def cmd_admin(message: types.Message, state: FSMContext, session: AsyncSession = None) -> None:
    """Handler for the /admin command. Shows admin options if user is an admin."""
    user_id = message.from_user.id
    
    # Check if user is admin
    if not await is_user_admin(user_id, session):
        logger.warning(f"Non-admin user {user_id} attempted to use admin command")
        await message.answer("Sorry, this command is only available to administrators.")
        return
    
    # Set state to awaiting choice
    await state.set_state(AdminStates.awaiting_choice)
    
    # Show admin options
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🗑️ Delete Data", callback_data="admin:delete_data")],
        [types.InlineKeyboardButton(text="👥 Manage Users", callback_data="admin:manage_users")],
        [types.InlineKeyboardButton(text="👪 Manage Groups", callback_data="admin:manage_groups")],
        [types.InlineKeyboardButton(text="❌ Cancel", callback_data="admin:cancel")]
    ])
    
    await message.answer("👑 Admin Panel - Choose an option:", reply_markup=keyboard)

async def on_admin_option(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession = None) -> None:
    """Handle admin option selection."""
    user_id = callback.from_user.id
    
    # Check if user is admin
    if not await is_user_admin(user_id, session):
        logger.warning(f"Non-admin user {user_id} attempted to use admin callback")
        await callback.answer("Not authorized", show_alert=True)
        await state.clear()
        return
    
    # Get the option
    option = callback.data.split(":")[1]
    
    if option == "delete_data":
        # Confirm data deletion
        await state.set_state(AdminStates.confirm_data_deletion)
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="⚠️ YES, DELETE ALL DATA", callback_data="admin:confirm_delete")],
            [types.InlineKeyboardButton(text="❌ Cancel", callback_data="admin:cancel")]
        ])
        await callback.message.edit_text(
            "⚠️ <b>WARNING: This will delete ALL data</b> ⚠️\n\n"
            "The following data will be removed:\n"
            "- All groups/teams\n"
            "- Group memberships\n"
            "- Questions\n"
            "- Answers\n"
            "- Matches\n\n"
            "User accounts will be preserved.\n\n"
            "This action cannot be undone. Are you sure?",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    elif option == "manage_users":
        # Not implemented yet
        await callback.answer("User management is not implemented yet", show_alert=True)
    elif option == "manage_groups":
        # Not implemented yet
        await callback.answer("Group management is not implemented yet", show_alert=True)
    elif option == "cancel":
        await state.clear()
        await callback.message.edit_text("Admin operation cancelled.")
    elif option == "confirm_delete":
        # Execute data deletion
        await callback.message.edit_text("🔄 Deleting data... Please wait.")
        
        try:
            # List of tables to truncate in order (respecting foreign keys)
            tables = [
                "answers",
                "questions",
                "matches",
                "group_members",
                "groups"
            ]
            
            # Truncate tables
            for table in tables:
                try:
                    await session.execute(text(f"TRUNCATE TABLE {table} CASCADE;"))
                    logger.info(f"Admin {user_id} truncated table: {table}")
                except Exception as e:
                    logger.error(f"Error truncating {table}: {e}")
                    await session.rollback()
                    await callback.message.edit_text(f"❌ Error: Failed to delete {table} data. Operation aborted.")
                    await state.clear()
                    return
            
            # Commit changes
            await session.commit()
            logger.warning(f"Admin {user_id} completed database reset")
            
            # Success message
            await callback.message.edit_text(
                "✅ All data has been successfully deleted.\n\n"
                "The database has been reset, but user accounts are preserved."
            )
        except Exception as e:
            logger.error(f"Database reset failed: {e}")
            await session.rollback()
            await callback.message.edit_text("❌ Error: Database reset failed. Please try again later.")
        
        # Clear state
        await state.clear()
    else:
        await callback.answer("Unknown option")

def register_handlers(dp: Dispatcher) -> None:
    """Register admin handlers."""
    dp.message.register(cmd_admin, Command(commands=["admin"]))
    dp.callback_query.register(on_admin_option, lambda c: c.data.startswith("admin:")) 