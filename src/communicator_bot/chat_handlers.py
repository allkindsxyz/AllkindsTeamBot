"""
Chat management functionality for the communicator bot.
"""
from aiogram import Bot, F, Router, types
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime

from src.db.models import Chat
from src.db.repositories.user import user_repo
from src.db.repositories.match_repo import get_match_between_users, get_with_users
from src.db.repositories.chat_message_repo import chat_message_repo
from src.db.repositories.blocked_user_repo import blocked_user_repo

from .states import ChatState
from .keyboards import (
    get_main_menu_keyboard,
    get_chat_selection_keyboard,
    get_user_management_keyboard,
    get_select_user_to_manage_keyboard,
    get_confirm_delete_keyboard,
    get_confirm_block_keyboard,
    get_in_chat_keyboard,
    get_back_to_menu_keyboard,
    get_chat_history_keyboard,
    get_whats_next_keyboard
)
from .repositories import (
    get_active_chats_for_user,
    get_unread_message_count,
    mark_messages_as_read,
    get_partner_nickname,
    end_chat_session,
    get_unread_chat_summary
)

router = Router()

# Main menu handler
@router.message(Command("menu"))
@router.message(F.text == "🔙 Back to menu")
async def show_main_menu(message: Message, state: FSMContext, session: AsyncSession):
    """Show the main menu with options to select chat and manage users."""
    await state.clear()  # Clear any active state
    
    # Get user
    user = await user_repo.get_by_telegram_id(session, message.from_user.id)
    if not user:
        await message.answer("You need to register in the main bot first.")
        return
        
    # Get all active chats
    active_chats = await get_active_chats_for_user(session, user.id)
    active_chat_count = len(active_chats)
    
    # Check for unread messages
    unread_summary = await get_unread_chat_summary(session, user.id)
    total_unread = sum(chat["unread_count"] for chat in unread_summary)
    
    # Create menu text
    menu_text = f"Welcome to the chat menu! You have {active_chat_count} active chats."
    
    # Add unread message summary if there are any
    if total_unread > 0:
        menu_text += f"\n\n📬 You have {total_unread} unread message(s) from:"
        for i, chat in enumerate(unread_summary[:3]):  # Show at most 3 chats
            menu_text += f"\n- {chat['partner_name']}: {chat['unread_count']} message(s)"
        
        if len(unread_summary) > 3:
            menu_text += f"\n- and {len(unread_summary) - 3} more chat(s)"
            
        menu_text += "\n\nClick 'Select user to chat' to view your messages."
    
    await message.answer(
        menu_text,
        reply_markup=get_main_menu_keyboard()
    )


# Start with deep link (from match)
@router.message(CommandStart(deep_link=True))
async def handle_start_with_link(message: Message, state: FSMContext, bot: Bot, session: AsyncSession):
    """Handle /start command with deep link payload from matching."""
    user_id = message.from_user.id
    try:
        # Получаем пользователя из БД для дальнейшего использования
        user = await user_repo.get_by_telegram_id(session, user_id)
        if not user:
            await message.answer("You need to register in the main bot first.")
            return
        
        # Log the raw message text to see exactly what Telegram sends
        logger.info(f"[DEEP_LINK] Raw message text: {message.text}")
        logger.info(f"[DEEP_LINK] User {user_id} started communicator bot with deep link")
        
        # First check if the state is already set to chat
        current_state = await state.get_state()
        if current_state == ChatState.in_chat:
            # User is already in a chat, get their current context
            state_data = await state.get_data()
            logger.info(f"[DEEP_LINK] User {user_id} already in chat state, current data: {state_data}")
            
            # If they're already in an active chat, show that info
            chat_id = state_data.get("chat_id")
            partner_id = state_data.get("partner_id")
            if chat_id and partner_id:
                logger.info(f"[DEEP_LINK] User already has active chat {chat_id} with partner {partner_id}")
                # Check if this chat is still valid
                try:
                    chat = await get_chat_by_id(session, chat_id)
                    if chat:
                        logger.info(f"[DEEP_LINK] Found chat with ID: {chat.id}")
                        
                        # Get partner's display name
                        partner = await user_repo.get(session, partner_id)
                        if partner:
                            partner_name = await get_partner_nickname(session, partner_id)
                            await message.answer(
                                f"You're already in a chat with {partner_name}. Your messages will be forwarded to them.",
                                reply_markup=get_in_chat_keyboard(partner_name)
                            )
                            return
                except Exception as e:
                    logger.error(f"[DEEP_LINK] Error checking existing chat: {e}")
                    # Continue with new chat setup as fallback
        
        # Extract the payload from the message
        try:
            payload = message.text.split(' ')[1]  # Get the payload after /start
            logger.info(f"[DEEP_LINK] Extracted payload: {payload}")
        except IndexError:
            logger.error(f"[DEEP_LINK] Failed to extract payload from message: {message.text}")
            await message.answer("Invalid link format. Please use the link provided after finding a match.")
            return
        
        # Validate payload format (expecting "chat_[chat_id]" or "match_[match_id]")
        if payload.startswith("chat_"):
            # Direct chat link
            try:
                chat_id = int(payload.split('_')[1])
                logger.debug(f"[DEEP_LINK] Extracted chat_id from payload: {chat_id}")
                
                # Get chat
                chat = await get_chat_by_id(session, chat_id)
                if not chat:
                    logger.error(f"[DEEP_LINK] Chat with ID {chat_id} not found")
                    await message.answer("Chat not found. It may have been deleted or expired.")
                    return
                
                # Determine partner
                partner_id = chat.recipient_id if user.id == chat.initiator_id else chat.initiator_id
                
                # Get partner info
                partner = await user_repo.get(session, partner_id)
                if not partner:
                    logger.error(f"[DEEP_LINK] Partner with ID {partner_id} not found")
                    await message.answer("Partner not found in database. They may have deleted their account.")
                    return
                
                # Set up state for chat
                await state.set_state(ChatState.in_chat)
                await state.update_data({
                    "chat_id": chat.id,
                    "partner_id": partner_id
                })
                
                # Mark messages as read
                await mark_messages_as_read(session, chat.id, user.id)
                
                # Get partner's nickname
                partner_name = await get_partner_nickname(session, partner_id)
                
                # Get recent messages
                messages_limit = 5
                recent_messages = await chat_message_repo.get_chat_messages(
                    session, chat.id, limit=messages_limit
                )
                
                # Format recent messages
                message_history = ""
                if recent_messages:
                    message_history = "Recent messages:\n\n"
                    for msg in reversed(recent_messages):  # Show in chronological order
                        sender = "You" if msg.sender_id == user.id else partner_name
                        message_history += f"{sender}: {msg.text_content}\n"
                
                # Send welcome message
                await message.answer(
                    f"Connected with {partner_name}!\n\n"
                    f"{message_history}\n"
                    "Your messages will be forwarded to your match.",
                    reply_markup=get_in_chat_keyboard(partner_name)
                )
                logger.info(f"[DEEP_LINK] Successfully connected user {user_id} with partner {partner_id} in chat")
                return
                
            except (ValueError, IndexError, Exception) as e:
                logger.error(f"[DEEP_LINK] Error processing chat deep link: {e}")
                await message.answer("Invalid chat link. Please use the link provided after finding a match.")
                return
                
        elif payload.startswith("match_"):
            # Match link - create a new chat
            try:
                match_id = int(payload.split('_')[1])
                logger.debug(f"[DEEP_LINK] Extracted match_id from payload: {match_id}")
                
                # Get match
                match = await get_with_users(session, match_id)
                if not match:
                    logger.error(f"[DEEP_LINK] Match with ID {match_id} not found")
                    await message.answer("Match not found. It may have been deleted.")
                    return
                
                # Determine partner
                partner_id = match.user2_id if user.id == match.user1_id else match.user1_id
                
                # Get partner
                partner = await user_repo.get(session, partner_id)
                if not partner:
                    logger.error(f"[DEEP_LINK] Partner with ID {partner_id} not found")
                    await message.answer("Partner not found in database. They may have deleted their account.")
                    return
                
                # Create or find a chat between these users
                chat = await find_or_create_chat(session, user.id, partner_id)
                if not chat:
                    logger.error(f"[DEEP_LINK] Failed to create or find chat between users {user.id} and {partner_id}")
                    await message.answer("Error creating chat. Please try again.")
                    return
                
                # Set up state for chat
                await state.set_state(ChatState.in_chat)
                await state.update_data({
                    "chat_id": chat.id,
                    "partner_id": partner_id
                })
                
                # Get partner's nickname
                partner_name = await get_partner_nickname(session, partner_id)
                
                # Send welcome message
                await message.answer(
                    f"Connected with {partner_name}!\n\n"
                    f"Match score: {match.score:.0%}\n"
                    f"Common questions: {match.common_questions or 0}\n\n"
                    "Your messages will be forwarded to your match.",
                    reply_markup=get_in_chat_keyboard(partner_name)
                )
                logger.info(f"[DEEP_LINK] Successfully connected user {user_id} with partner {partner_id} in new chat")
                return
                
            except (ValueError, IndexError, Exception) as e:
                logger.error(f"[DEEP_LINK] Error processing match deep link: {e}")
                await message.answer("Invalid match link. Please use the link provided after finding a match.")
                return
                
        else:
            logger.error(f"[DEEP_LINK] Invalid payload format: {payload}. Expected chat_[id] or match_[id]")
            await message.answer("Invalid link format. Please use the link provided after finding a match.")
            return

    except Exception as e:
        import traceback
        logger.exception(f"[DEEP_LINK] Error in handle_start_with_link: {e}")
        logger.error(f"[DEEP_LINK] Traceback: {traceback.format_exc()}")
        await message.answer("An error occurred while setting up the chat. Please try again later.")
        return


# Start without deep link
@router.message(CommandStart(deep_link=False))
async def handle_start_without_link(
    message: Message,
    state: FSMContext = None,
    session: AsyncSession = None,
    bot: Bot = None
):
    """Handle direct start command without deep link. Shows active chats as inline buttons."""
    if not session or not state:
        logger.error("Missing required dependencies for handle_start_without_link")
        await message.answer("An error occurred. Please try again later.")
        return
        
    user = await user_repo.get_by_telegram_id(session, message.from_user.id)
    if not user:
        await message.answer("You need to register in the main bot first.")
        return
    
    # Get all active chats directly
    all_chats = await get_active_chats_for_user(session, user.id)
    logger.info(f"Found {len(all_chats)} active chats for user {user.id}")
    
    if not all_chats:
        await message.answer(
            "You don't have any active chats yet. Find a match in the main bot first!"
        )
        return
    
    # Format users for keyboard
    users_data = []
    
    for chat in all_chats:
        # Determine partner ID
        partner_id = chat.recipient_id if chat.initiator_id == user.id else chat.initiator_id
        partner = await user_repo.get(session, partner_id)
        
        if not partner:
            continue
        
        # Get unread count
        unread_count = await get_unread_message_count(session, chat.id, user.id)
        
        # Get partner nickname
        partner_name = await get_partner_nickname(session, partner_id)
        
        # Create user data entry
        users_data.append({
            "id": partner.id,
            "name": partner_name,
            "unread_count": unread_count,
            "chat_id": chat.id
        })
    
    # Sort users - unread messages first, then alphabetically
    users_data.sort(key=lambda x: (-(x['unread_count'] > 0), x['name']))
    
    # Show available chats directly
    if users_data:
        await message.answer(
            "Select a chat to start messaging:",
            reply_markup=get_chat_selection_keyboard(users_data)
        )
        await state.set_state(ChatState.selecting_chat)
    else:
        await message.answer(
            "You don't have any active chats yet. Find a match in the main bot first!"
        )


# Select chat partner
@router.message(F.text == "👥 Select user to chat")
async def show_chat_selection(message: Message, state: FSMContext, session: AsyncSession):
    """Display list of available chat partners."""
    user = await user_repo.get_by_telegram_id(session, message.from_user.id)
    if not user:
        await message.answer("You need to register in the main bot first.")
        return
    
    # Get all active chats
    all_chats = await get_active_chats_for_user(session, user.id)
    logger.info(f"Found {len(all_chats)} active chats for user {user.id}")
    
    if not all_chats:
        await message.answer(
            "You don't have any active chats yet. Find a match in the main bot first!",
            reply_markup=get_back_to_menu_keyboard()
        )
        return
    
    # Format users for keyboard
    users_data = []
    
    for chat in all_chats:
        logger.info(f"Processing chat ID {chat.id} for user {user.id}")
        
        # Determine partner ID
        partner_id = chat.recipient_id if chat.initiator_id == user.id else chat.initiator_id
        partner = await user_repo.get(session, partner_id)
        
        if not partner:
            logger.info(f"Partner with ID {partner_id} not found, skipping")
            continue
        
        # Get unread count
        unread_count = await get_unread_message_count(session, chat.id, user.id)
        
        # Get partner nickname
        partner_name = await get_partner_nickname(session, partner_id)
        
        # Get latest message preview
        latest_message = ""
        
        # Get the latest message
        recent_message = await chat_message_repo.get_latest_message(session, chat.id)
        if recent_message:
            # Format timestamp
            timestamp = recent_message.created_at.strftime("%H:%M")
            
            # Format sender
            sender_prefix = "You: " if recent_message.sender_id == user.id else ""
            
            message_text = recent_message.text_content or ""
            # Truncate long messages
            if len(message_text) > 30:
                message_text = message_text[:27] + "..."
                
            latest_message = f"{timestamp} {sender_prefix}{message_text}"
        else:
            latest_message = "No messages yet"
        
        # Create user data entry
        users_data.append({
            "id": partner.id,
            "name": partner_name,
            "unread_count": unread_count,
            "chat_id": chat.id,
            "is_group_chat": False,
            "latest_message": latest_message
        })
    
    logger.info(f"Final user data count: {len(users_data)}")
    
    # Sort users - unread messages first, then by latest activity
    users_data.sort(key=lambda x: (-(x['unread_count'] > 0), x['name']))
    
    if not users_data:
        await message.answer(
            "You don't have any active chats yet. Find a match in the main bot first!",
            reply_markup=get_back_to_menu_keyboard()
        )
        return
    
    await message.answer(
        "Select a user to chat with:",
        reply_markup=get_chat_selection_keyboard(users_data)
    )
    
    await state.set_state(ChatState.selecting_chat)


# Chat selection callback
@router.callback_query(F.data.startswith("chat:"))
async def on_chat_selected(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Handle selecting a chat partner."""
    await callback.answer()
    
    user = await user_repo.get_by_telegram_id(session, callback.from_user.id)
    if not user:
        await callback.message.answer("You need to register in the main bot first.")
        return
    
    # Parse the callback data 
    callback_parts = callback.data.split(":")
    partner_id = int(callback_parts[1])
    chat_id = int(callback_parts[2]) if len(callback_parts) > 2 else None
    
    logger.info(f"Chat selected: partner_id={partner_id}, chat_id={chat_id}")
    
    partner = await user_repo.get(session, partner_id)
    
    if not partner:
        await callback.message.answer("Partner not found.")
        return
    
    # Find or use existing chat
    if chat_id:
        # Get existing chat
        chat = await get_chat_by_id(session, chat_id)
        if not chat:
            logger.error(f"Chat with ID {chat_id} not found")
            await callback.message.answer("Chat not found.")
            return
    else:
        # Find or create a chat between these users
        chat = await find_or_create_chat(session, user.id, partner_id)
        if not chat:
            logger.error(f"Failed to create chat between users {user.id} and {partner_id}")
            await callback.message.answer("Failed to create chat. Please try again.")
            return
    
    logger.info(f"Using chat {chat.id} for users {user.id} and {partner_id}")
    
    # Mark messages as read if needed
    marked_count = await mark_messages_as_read(session, chat.id, user.id)
    logger.info(f"Marked {marked_count} messages as read for user {user.id} in chat {chat.id}")
    
    # Set up the state for chat
    await state.set_state(ChatState.in_chat)
    await state.update_data({
        "chat_id": chat.id,
        "partner_id": partner_id
    })
    
    # Get partner's display name
    partner_name = await get_partner_nickname(session, partner_id)
    
    # Edit the original message to remove selection buttons
    await callback.message.edit_text(
        f"Chat with {partner_name}",
        reply_markup=None
    )
    
    # Get recent messages
    messages_limit = 50  # Increased limit for better history
    recent_messages = await chat_message_repo.get_chat_messages(
        session, chat.id, limit=messages_limit
    )
    
    # Log message retrieval
    logger.info(f"Retrieved {len(recent_messages)} recent messages for chat {chat.id}")
    
    # Check if there are more messages
    total_messages = await chat_message_repo.count_chat_messages(session, chat.id)
    has_more_messages = total_messages > messages_limit
    
    # Send the in-chat keyboard
    keyboard_message = await callback.message.answer(
        "👇 Your keyboard 👇",
        reply_markup=get_in_chat_keyboard(partner_name)
    )
    
    # Only display the history if there are messages
    if recent_messages:
        # Format messages with timestamps
        message_history = ""
        for msg in reversed(recent_messages):  # Show in chronological order
            # Skip service messages, only show actual content
            if not msg.text_content and not msg.file_id:
                continue
                
            # Determine sender display name
            sender = "You" if msg.sender_id == user.id else partner_name
            timestamp = msg.created_at.strftime("%H:%M")
            
            # Format based on content type
            if msg.content_type == "text":
                content = msg.text_content or ""
                # Escape any HTML characters in the message content for safety
                content = content.replace("<", "&lt;").replace(">", "&gt;")
                message_history += f"[{timestamp}] <b>{sender}</b>: {content}\n\n"
            elif msg.content_type == "photo":
                caption = msg.text_content or ""
                caption = caption.replace("<", "&lt;").replace(">", "&gt;")
                message_history += f"[{timestamp}] <b>{sender}</b>: 📷 Photo{': ' + caption if caption else ''}\n\n"
            elif msg.content_type == "document":
                caption = msg.text_content or ""
                caption = caption.replace("<", "&lt;").replace(">", "&gt;")
                message_history += f"[{timestamp}] <b>{sender}</b>: 📎 Document{': ' + caption if caption else ''}\n\n"
            elif msg.content_type == "sticker":
                message_history += f"[{timestamp}] <b>{sender}</b>: 🔖 Sticker\n\n"
            elif msg.content_type == "voice":
                message_history += f"[{timestamp}] <b>{sender}</b>: 🎤 Voice message\n\n"
            else:
                message_history += f"[{timestamp}] <b>{sender}</b>: Message\n\n"
        
        # Only send message history if there's content to show
        if message_history:
            try:
                history_message = await callback.message.answer(
                    f"<b>Message History:</b>\n\n{message_history}",
                    reply_markup=get_chat_history_keyboard(
                        chat.id, 
                        0, 
                        has_more_messages
                    ),
                    parse_mode="HTML"
                )
                
                # Store history message ID for later updates
                await state.update_data({"history_message_id": history_message.message_id})
                logger.info(f"Chat history message sent, ID: {history_message.message_id}")
            except Exception as e:
                logger.error(f"Error sending chat history: {e}")
                await callback.message.answer(
                    f"Error displaying chat history. Chat is still active, you can send messages."
                )


# Stop command
@router.message(Command("stop"))
async def handle_stop(message: Message, state: FSMContext, session: AsyncSession):
    """Return to main menu."""
    await message.answer("Returning to main menu...")
    await state.clear()
    await show_main_menu(message, state, session)

# Debug command
@router.message(Command("debug"))
async def handle_debug(message: Message, state: FSMContext = None, session: AsyncSession = None, bot: Bot = None):
    """Debug command to test bot functionality."""
    user_id = message.from_user.id
    logger.info(f"Debug command received from user {user_id}")
    
    response_text = "Debug info:\n"
    response_text += f"- Your user ID: {user_id}\n"
    response_text += f"- Bot username: {bot.username if bot else 'Unknown'}\n"
    response_text += f"- Session available: {session is not None}\n"
    response_text += f"- State available: {state is not None}\n"
    
    if state:
        current_state = await state.get_state()
        state_data = await state.get_data()
        response_text += f"- Current state: {current_state}\n"
        response_text += f"- State data keys: {list(state_data.keys()) if state_data else 'None'}\n"
    
    await message.answer(response_text)

# Helper function to get chat by ID
async def get_chat_by_id(session: AsyncSession, chat_id: int) -> Chat:
    """
    Get a chat by its ID.
    
    Args:
        session: Database session
        chat_id: ID of the chat
        
    Returns:
        Chat object if found, None otherwise
    """
    query = select(Chat).where(Chat.id == chat_id)
    result = await session.execute(query)
    return result.scalar_one_or_none()

# Helper function to find or create chat
async def find_or_create_chat(session: AsyncSession, user1_id: int, user2_id: int) -> Chat:
    """
    Find an existing chat between two users or create a new one.
    
    Args:
        session: Database session
        user1_id: ID of the first user
        user2_id: ID of the second user
        
    Returns:
        Chat object if found or created, None otherwise
    """
    # Check if chat already exists
    query = select(Chat).where(
        (
            ((Chat.initiator_id == user1_id) & (Chat.recipient_id == user2_id)) |
            ((Chat.initiator_id == user2_id) & (Chat.recipient_id == user1_id))
        ) & 
        (Chat.status == "active")
    )
    result = await session.execute(query)
    existing_chat = result.scalar_one_or_none()
    
    if existing_chat:
        return existing_chat
    
    # Create new chat
    try:
        new_chat = Chat(
            initiator_id=user1_id,
            recipient_id=user2_id,
            status="active"
        )
        session.add(new_chat)
        await session.commit()
        await session.refresh(new_chat)
        return new_chat
    except Exception as e:
        logger.error(f"Error creating chat: {e}")
        return None

# Handle chat opening from notifications
@router.callback_query(F.data.startswith("open_chat:"))
async def on_open_chat_from_notification(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Handle opening a chat from a notification."""
    await callback.answer()
    
    user = await user_repo.get_by_telegram_id(session, callback.from_user.id)
    if not user:
        await callback.message.answer("You need to register in the main bot first.")
        return
    
    # Parse the callback data
    try:
        parts = callback.data.split(":")
        partner_id = int(parts[1])
        chat_id = int(parts[2])
    except (ValueError, IndexError):
        logger.error(f"Invalid callback data: {callback.data}")
        await callback.message.answer("Invalid callback data. Please try selecting a chat from the menu.")
        return
    
    # Get partner
    partner = await user_repo.get(session, partner_id)
    if not partner:
        await callback.message.answer("Partner not found.")
        return
    
    # Set up chat state
    await state.set_state(ChatState.in_chat)
    
    # Get chat
    chat = await get_chat_by_id(session, chat_id)
    if not chat:
        logger.error(f"Chat with ID {chat_id} not found when opening from notification.")
        await callback.message.answer("Chat not found.")
        return
        
    # Mark messages as read
    marked_count = await mark_messages_as_read(session, chat.id, user.id)
    logger.info(f"Marked {marked_count} messages as read for user {user.id} in chat {chat.id} when opening from notification.")
    
    # Set state data
    await state.update_data({
        "chat_id": chat.id,
        "partner_id": partner_id
    })
    
    # Get partner name
    partner_name = await get_partner_nickname(session, partner_id)
    
    # Get recent messages
    messages_limit = 20
    recent_messages = await chat_message_repo.get_chat_messages(
        session, chat.id, limit=messages_limit
    )
    
    # Log message retrieval
    logger.info(f"Retrieved {len(recent_messages)} recent messages for chat {chat.id} when opening from notification.")
    
    # Check if there are more messages
    total_messages = await chat_message_repo.count_chat_messages(session, chat.id)
    has_more_messages = total_messages > messages_limit
    
    # Format messages with timestamps
    message_history = ""
    if recent_messages:
        for msg in reversed(recent_messages):  # Show in chronological order
            sender = "You" if msg.sender_id == user.id else partner_name
            timestamp = msg.created_at.strftime("%H:%M")
            content = msg.text_content or ""
            # Escape any HTML characters in the message content for safety
            content = content.replace("<", "&lt;").replace(">", "&gt;")
            message_history += f"[{timestamp}] <b>{sender}</b>: {content}\n\n"
    else:
        message_history = "No messages yet. Start the conversation!"
    
    # Edit notification message
    await callback.message.edit_text(
        f"You are now chatting with {partner_name}. Your messages will be forwarded to them.",
        reply_markup=None
    )
    
    # Send history message
    try:
        history_message = await callback.message.answer(
            f"<b>Chat with {partner_name}</b>\n\n{message_history}",
            reply_markup=get_chat_history_keyboard(
                chat.id, 
                0, 
                has_more_messages
            ),
            parse_mode="HTML"
        )
        
        # Store history message ID for later updates
        await state.update_data({"history_message_id": history_message.message_id})
        logger.info(f"Chat history message sent from notification, ID: {history_message.message_id}.")
    except Exception as e:
        logger.error(f"Error sending chat history from notification: {e}")
    
    # Send welcome message with chat keyboard
    await callback.message.answer(
        f"Now chatting with {partner_name}. Type your message to send.",
        reply_markup=get_in_chat_keyboard(partner_name)
    )

# Handle load more messages callback
@router.callback_query(F.data.startswith("load_more:"))
async def on_load_more_messages(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """Handle loading more messages in chat history."""
    await callback.answer()
    
    # Parse callback data
    parts = callback.data.split(":")
    chat_id = int(parts[1])
    offset = int(parts[2])
    
    # Get current state
    state_data = await state.get_data()
    
    # Make sure user is in chat
    current_state = await state.get_state()
    if current_state != ChatState.in_chat:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("You're not in a chat. Please select a chat first.")
        return
    
    # Get partner info
    partner_id = state_data.get("partner_id")
    partner = await user_repo.get(session, partner_id)
    if not partner:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("Partner not found. Please select a chat from the menu.")
        return
    
    # Get partner name
    partner_name = await get_partner_nickname(session, partner_id)
    
    # Load messages with the new offset
    page_size = 20
    older_messages = await chat_message_repo.get_chat_messages(
        session, chat_id, limit=page_size, offset=offset
    )
    
    # Check if there are more messages
    total_messages = await chat_message_repo.count_chat_messages(session, chat_id)
    has_more_messages = total_messages > (offset + page_size)
    
    # Format older messages
    message_history = ""
    if older_messages:
        for msg in reversed(older_messages):  # Show in chronological order
            # Skip service messages, only show actual content
            if not msg.text_content and not msg.file_id:
                continue
                
            sender = "You" if msg.sender_id == callback.from_user.id else partner_name
            timestamp = msg.created_at.strftime("%d/%m %H:%M")
            
            # Format based on content type
            if msg.content_type == "text":
                content = msg.text_content or ""
                # Escape any HTML characters in the message content for safety
                content = content.replace("<", "&lt;").replace(">", "&gt;")
                message_history += f"<b>{sender}</b>: {content}\n\n"
            elif msg.content_type == "photo":
                caption = msg.text_content or ""
                caption = caption.replace("<", "&lt;").replace(">", "&gt;")
                message_history += f"<b>{sender}</b>: 📷 Photo{': ' + caption if caption else ''}\n\n"
            elif msg.content_type == "document":
                caption = msg.text_content or ""
                caption = caption.replace("<", "&lt;").replace(">", "&gt;")
                message_history += f"<b>{sender}</b>: 📎 Document{': ' + caption if caption else ''}\n\n"
            elif msg.content_type == "sticker":
                message_history += f"<b>{sender}</b>: 🔖 Sticker\n\n"
            elif msg.content_type == "voice":
                message_history += f"<b>{sender}</b>: 🎤 Voice message\n\n"
            else:
                message_history += f"<b>{sender}</b>: Message\n\n"
    
    # Get the current message text content
    current_text = callback.message.text or ""
    
    # Only show earlier messages if there are any
    if not message_history:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("No more messages to load.")
        return
    
    # If we're showing older messages, create a header
    history_header = f"<b>Earlier Messages:</b>\n\n{message_history}\n"
    
    # Create a separator
    separator = "<b>───────────────────</b>\n\n"
    
    # Check if the current text is too long
    # Telegram has a 4096 character limit for message text
    MAX_MSG_LENGTH = 4000  # Leave some room for formatting
    
    if len(history_header + separator + current_text) > MAX_MSG_LENGTH:
        # If too long, create a new message with just the older messages
        new_message = await callback.message.answer(
            history_header,
            reply_markup=get_chat_history_keyboard(chat_id, offset, has_more_messages),
            parse_mode="HTML"
        )
        # Keep the old message as is
        await callback.message.edit_reply_markup(reply_markup=None)
    else:
        # If we can fit everything in one message
        await callback.message.edit_text(
            history_header + separator + current_text,
            reply_markup=get_chat_history_keyboard(chat_id, offset, has_more_messages),
            parse_mode="HTML"
        )

# Handle "Switch chat" button
@router.message(F.text == "👥 Switch chat")
async def handle_switch_chat(message: Message, state: FSMContext, session: AsyncSession):
    """Handle switch chat button and show available chats."""
    user = await user_repo.get_by_telegram_id(session, message.from_user.id)
    if not user:
        await message.answer("You need to register in the main bot first.")
        return
    
    # Get all active chats
    all_chats = await get_active_chats_for_user(session, user.id)
    logger.info(f"Found {len(all_chats)} active chats for user {user.id}")
    
    if not all_chats:
        await message.answer(
            "You don't have any other active chats."
        )
        return
    
    # Format users for keyboard
    users_data = []
    
    for chat in all_chats:
        # Determine partner ID
        partner_id = chat.recipient_id if chat.initiator_id == user.id else chat.initiator_id
        partner = await user_repo.get(session, partner_id)
        
        if not partner:
            continue
        
        # Get unread count
        unread_count = await get_unread_message_count(session, chat.id, user.id)
        
        # Get partner nickname
        partner_name = await get_partner_nickname(session, partner_id)
        
        # Create user data entry
        users_data.append({
            "id": partner.id,
            "name": partner_name,
            "unread_count": unread_count,
            "chat_id": chat.id
        })
    
    # Sort users - unread messages first, then alphabetically
    users_data.sort(key=lambda x: (-(x['unread_count'] > 0), x['name']))
    
    await message.answer(
        "Select a user to chat with:",
        reply_markup=get_chat_selection_keyboard(users_data)
    )
    
    await state.set_state(ChatState.selecting_chat) 

@router.message(F.text.startswith("🙌 What's next with"))
async def handle_whats_next(message: Message, state: FSMContext, session: AsyncSession):
    """Handle the user clicking the "What's next with [partner]" button."""
    user_id = message.from_user.id
    user = await user_repo.get_by_telegram_id(session, user_id)
    
    if not user:
        await message.answer("You need to register in the main bot first.")
        return
    
    data = await state.get_data()
    partner_id = data.get("partner_id")
    
    if not partner_id:
        await message.answer("You are not connected to anyone. Select a chat first.")
        await state.clear()
        return
    
    # Get partner
    partner = await user_repo.get(session, partner_id)
    if not partner:
        await message.answer("Partner not found.")
        return
    
    # Get partner nickname
    partner_name = await get_partner_nickname(session, partner_id)
    
    await message.answer(
        f"What would you like to do with your chat with {partner_name}?",
        reply_markup=get_whats_next_keyboard(partner_id)
    ) 