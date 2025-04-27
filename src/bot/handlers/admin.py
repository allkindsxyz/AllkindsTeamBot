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
    logger.info(f"Admin command called by user {user_id}")
    
    try:
        # Check if user is admin
        if not await is_user_admin(user_id, session):
            logger.warning(f"Non-admin user {user_id} attempted to use admin command")
            await message.answer("Sorry, this command is only available to administrators.")
            return
        
        logger.info(f"User {user_id} is an admin, showing admin options")
        
        # Set state to awaiting choice
        try:
            previous_state = await state.get_state() 
            logger.info(f"Previous state for user {user_id}: {previous_state}")
            await state.set_state(AdminStates.awaiting_choice)
        except Exception as state_error:
            logger.error(f"Error setting state: {state_error}")
            # Continue anyway - the command should work even if state management fails
        
        # Show admin options
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="🗑️ Delete Data", callback_data="admin:delete_data")],
            [types.InlineKeyboardButton(text="👥 Manage Users", callback_data="admin:manage_users")],
            [types.InlineKeyboardButton(text="👪 Manage Groups", callback_data="admin:manage_groups")],
            [types.InlineKeyboardButton(text="❌ Cancel", callback_data="admin:cancel")]
        ])
        
        await message.answer("👑 Admin Panel - Choose an option:", reply_markup=keyboard)
        logger.info(f"Admin panel displayed for user {user_id}")
    except Exception as e:
        logger.error(f"Error in admin command handler: {e}")
        logger.exception("Full traceback for admin command error:")
        # Try to respond with a generic error message
        try:
            await message.answer("An error occurred while processing the admin command. Please try again.")
        except:
            pass

async def on_admin_option(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession = None) -> None:
    """Handle admin option selection."""
    user_id = callback.from_user.id
    logger.info(f"Admin option callback from user {user_id}: {callback.data}")
    
    try:
        # Check if user is admin
        if not await is_user_admin(user_id, session):
            logger.warning(f"Non-admin user {user_id} attempted to use admin callback")
            await callback.answer("Not authorized", show_alert=True)
            await state.clear()
            return
        
        # Get the option
        option = callback.data.split(":")[1]
        logger.info(f"Admin {user_id} selected option: {option}")
        
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
            logger.info(f"Displayed delete confirmation for admin {user_id}")
        elif option == "manage_users":
            # Not implemented yet
            await callback.answer("User management is not implemented yet", show_alert=True)
            logger.info(f"Admin {user_id} attempted to use unimplemented feature: manage_users")
        elif option == "manage_groups":
            # Not implemented yet
            await callback.answer("Group management is not implemented yet", show_alert=True)
            logger.info(f"Admin {user_id} attempted to use unimplemented feature: manage_groups")
        elif option == "cancel":
            await state.clear()
            await callback.message.edit_text("Admin operation cancelled.")
            logger.info(f"Admin {user_id} cancelled admin operation")
        elif option == "confirm_delete":
            # Execute data deletion
            logger.warning(f"Admin {user_id} confirmed data deletion - beginning process")
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
                        logger.info(f"Truncating table {table}")
                        await session.execute(text(f"TRUNCATE TABLE {table} CASCADE;"))
                        logger.info(f"Admin {user_id} truncated table: {table}")
                    except Exception as e:
                        logger.error(f"Error truncating {table}: {e}")
                        logger.exception(f"Full traceback for error truncating {table}:")
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
                logger.exception("Full traceback for database reset error:")
                await session.rollback()
                await callback.message.edit_text("❌ Error: Database reset failed. Please try again later.")
            
            # Clear state
            await state.clear()
        else:
            await callback.answer("Unknown option")
            logger.warning(f"Admin {user_id} selected unknown option: {option}")
    except Exception as e:
        logger.error(f"Error in admin option handler: {e}")
        logger.exception("Full traceback for admin option error:")
        try:
            await callback.answer("An error occurred", show_alert=True)
        except:
            pass

def register_handlers(dp: Dispatcher) -> None:
    """Register admin handlers."""
    # Register admin command without any state requirements
    dp.message.register(cmd_admin, Command(commands=["admin"]))
    
    # Register callback handlers for admin actions
    dp.callback_query.register(on_admin_option, lambda c: c.data.startswith("admin:")) 