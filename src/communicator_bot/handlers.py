from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from loguru import logger
from aiogram.fsm.storage.base import StorageKey
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from .states import ChatState
from .repositories import user_repo, get_by_session_id, update_status

# Simple in-memory storage for POC
# In production, use a database
user_nicknames = {} # user_id: nickname
active_chats = {} # user_id: partner_id

router = Router()

# TODO: Implement handlers:
# 1. /start command handler
# 2. Nickname processing handler
# 3. Message relay handler
# 4. /stop command handler

@router.message(CommandStart(deep_link=True))
async def handle_start_with_link(message: Message, state: FSMContext, bot: Bot):
    """Handles the /start command with a deep link payload (e.g., from matching)."""
    user_id = message.from_user.id
    payload = message.text.split(' ')[1] # Get the payload after /start
    logger.info(f"User {user_id} started communicator bot with payload: {payload}")

    if user_id in active_chats:
        await message.reply("You are already in a chat. Send /stop to leave.")
        return

    if not payload.startswith("match_"):
        logger.warning(f"User {user_id} started with unknown payload format: {payload}")
        await message.reply("Invalid link format. Please use the link provided after finding a match.")
        await state.clear()
        return

    try:
        _, user1_id_str, user2_id_str = payload.split('_')
        user1_id = int(user1_id_str)
        user2_id = int(user2_id_str)
    except ValueError:
        logger.error(f"Failed to parse user IDs from payload: {payload}")
        await message.reply("Invalid link data. Please use the link provided after finding a match.")
        await state.clear()
        return

    # Determine partner ID
    if user_id == user1_id:
        partner_id = user2_id
    elif user_id == user2_id:
        partner_id = user1_id
    else:
        logger.error(f"User {user_id} clicked link with payload {payload}, but is neither user1 nor user2.")
        await message.reply("There seems to be an issue with this chat link. Please try matching again.")
        await state.clear()
        return

    # --- Coordination Logic using FSM Data --- #
    # We use FSM data associated with the *pair* (identified by the lower user ID)
    # to coordinate the connection.
    pair_key = f"pending_pair_{min(user1_id, user2_id)}_{max(user1_id, user2_id)}"
    pair_data = await state.storage.get_data(bot=bot, key=StorageKey(bot.id, user_id, user_id)) # Use own chat/user ID for temp storage
    pending_pair_info = pair_data.get(pair_key)

    if pending_pair_info:
        # The other user already clicked the link
        other_user_activated = pending_pair_info.get("activated_user_id")
        if other_user_activated == partner_id:
            logger.info(f"User {user_id} is the second user to activate link for pair ({user1_id}, {user2_id}). Connecting.")
            # Clean up pending data
            await state.storage.set_data(bot=bot, key=StorageKey(bot.id, user_id, user_id), data={})

            # Fetch nicknames (these should ideally be passed via payload or another mechanism)
            # For POC, let's assign temporary names or prompt again if needed.
            # Let's assign temporary ones for now.
            user_nicknames[user_id] = f"User_{user_id % 1000}"
            user_nicknames[partner_id] = f"User_{partner_id % 1000}"
            your_nickname = user_nicknames[user_id]
            partner_nickname = user_nicknames[partner_id]

            # Connect users
            active_chats[user_id] = partner_id
            active_chats[partner_id] = user_id
            await state.set_state(ChatState.in_chat)

            # Set partner's state
            partner_state = FSMContext(storage=state.storage, key=StorageKey(bot.id, partner_id, partner_id))
            try:
                await partner_state.set_state(ChatState.in_chat)
                # Send connection messages
                await bot.send_message(partner_id, f"You've been connected with '{your_nickname}'! Start chatting.")
                await message.reply(f"You've been connected with '{partner_nickname}'! Start chatting.")
                logger.info(f"Successfully connected pair ({user1_id}, {user2_id}).")
            except Exception as e:
                 logger.error(f"Failed to set partner state or notify partner {partner_id}: {e}. Disconnecting.")
                 active_chats.pop(user_id, None)
                 active_chats.pop(partner_id, None)
                 user_nicknames.pop(user_id, None)
                 user_nicknames.pop(partner_id, None)
                 await state.clear()
                 await message.reply("An error occurred connecting you. Please try again.")
                 try: await partner_state.clear() # Attempt cleanup
                 except: pass
        else:
             # Should not happen if logic is correct, but handle defensively
             logger.error(f"State mismatch for pair key {pair_key}. Expected {partner_id}, found {other_user_activated}. Resetting.")
             await state.storage.set_data(bot=bot, key=StorageKey(bot.id, user_id, user_id), data={})
             await message.reply("There was a state mismatch. Please try the link again.")
             await state.clear()

    else:
        # This is the first user to click the link for this pair
        logger.info(f"User {user_id} is the first user to activate link for pair ({user1_id}, {user2_id}). Waiting.")
        new_pair_data = {pair_key: {"activated_user_id": user_id}}
        await state.storage.set_data(bot=bot, key=StorageKey(bot.id, user_id, user_id), data=new_pair_data)
        await state.set_state(ChatState.waiting_for_link_activation)
        await message.reply("Waiting for your match to join the chat...")


@router.message(CommandStart(deep_link=False))
async def handle_start_without_link(message: Message, state: FSMContext):
    """Handles the /start command without deep link (direct start)."""
    user_id = message.from_user.id
    current_state = await state.get_state()
    logger.info(f"User {user_id} started communicator bot directly (no link). State: {current_state}")

    if user_id in active_chats:
        await message.reply("You are already in a chat. Send /stop to leave.")
        return
    if current_state == ChatState.waiting_for_link_activation:
        await message.reply("Waiting for your match to join the chat...")
        return

    # For now, direct start doesn't do anything in the matched chat context
    # Could potentially add back the nickname/random pairing later if desired
    await message.reply("Please use the invite link provided by the main bot after finding a match.")
    await state.clear()


@router.message(Command('stop'))
async def handle_stop(message: Message, state: FSMContext, bot: Bot):
    """Handles the /stop command to disconnect users or cancel waiting."""
    user_id = message.from_user.id
    current_state = await state.get_state()

    # Check if user was waiting for link activation
    if current_state == ChatState.waiting_for_link_activation:
        logger.info(f"User {user_id} stopped while waiting for link activation.")
        # Need to find the pair key to clean up
        # This is complex without knowing the partner ID easily.
        # Simplification: Just clear current user state. The pending data might become stale.
        # A better approach needs robust pending match management (e.g., DB table, Redis with TTL).
        await state.clear()
        await message.reply("You have stopped waiting for the match.")
        return

    partner_id = active_chats.pop(user_id, None)
    if partner_id:
        active_chats.pop(partner_id, None) # Remove partner's entry too
        partner_nickname = user_nicknames.pop(partner_id, "User")
        your_nickname = user_nicknames.pop(user_id, "You")
        logger.info(f"User {user_id} ({your_nickname}) disconnected from {partner_id} ({partner_nickname}).")
        try:
            # Try to clear partner state
            partner_state = FSMContext(storage=state.storage, key=StorageKey(bot.id, partner_id, partner_id))
            await partner_state.clear()
            await bot.send_message(partner_id, "Your chat partner has disconnected. You can find a new match in the main bot.")
        except Exception as e:
            logger.warning(f"Could not notify or clear state for partner {partner_id} about disconnection: {e}")
        await message.reply("You have been disconnected. You can find a new match in the main bot.")
    else:
        await message.reply("You are not currently in a chat.")

    await state.clear()


@router.message(ChatState.in_chat, F.text)
async def relay_message(message: Message, state: FSMContext, bot: Bot, session: AsyncSession):
    """Relays messages between paired users."""
    user_id = message.from_user.id
    data = await state.get_data()
    chat_session_id = data.get("chat_session_id")
    partner_id = data.get("partner_id")
    
    if not chat_session_id or not partner_id:
        logger.warning(f"User {user_id} in state in_chat but no chat_session_id or partner_id found in state.")
        await message.reply("You are not connected to anyone. Try finding a match in the main bot.")
        await state.clear()
        return
    
    # Get chat session
    chat_session = await get_by_session_id(session, data.get("session_id"))
    if not chat_session or chat_session.status != "active":
        await message.reply("This chat is no longer active.")
        await state.clear()
        return
    
    # Get partner
    partner = await user_repo.get(session, partner_id)
    if not partner or not partner.telegram_id:
        await message.reply("Cannot find your chat partner. They may have left.")
        return
    
    # Handle special commands
    if message.text == "🔍 Reveal Identity":
        # Handle identity revelation
        user = await user_repo.get_by_telegram_id(session, user_id)
        reveal_message = f"Your chat partner has revealed their identity:\n\n" \
                        f"Name: {user.first_name} {user.last_name or ''}\n" \
                        f"Username: @{user.username or 'N/A'}"
        
        await bot.send_message(chat_id=partner.telegram_id, text=reveal_message)
        await message.answer("You've revealed your identity to your chat partner.")
        return
        
    elif message.text == "❌ End Chat":
        # Handle chat ending
        await end_chat(message, state, session, bot)
        return
    
    # Regular message - forward it
    try:
        await bot.send_message(chat_id=partner.telegram_id, text=message.text)
        
        # Update last activity
        chat_session.last_activity = datetime.utcnow()
        await session.commit()
        
    except Exception as e:
        logger.error(f"Error forwarding message: {e}")
        await message.answer("Failed to send your message. The recipient may have blocked the bot.")
        # End the chat for this user as well
        await end_chat(message, state, session, bot)


async def end_chat(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    """End the anonymous chat session."""
    # Get state data
    data = await state.get_data()
    chat_session_id = data.get("chat_session_id")
    partner_id = data.get("partner_id")
    
    if not chat_session_id:
        await message.answer("No active chat found.")
        await state.clear()
        return
    
    # Get chat session
    chat_session = await get_by_session_id(session, data.get("session_id"))
    if not chat_session:
        await message.answer("Chat session not found.")
        await state.clear()
        return
    
    # Mark chat as ended
    chat_session = await update_status(session, chat_session.id, "ended", set_ended=True)
    
    # Notify current user
    keyboard = types.ReplyKeyboardRemove()
    await message.answer(
        "Chat has been ended. You can start a new chat from the main bot.",
        reply_markup=keyboard
    )
    
    # Notify partner if available
    if partner_id:
        partner = await user_repo.get(session, partner_id)
        if partner and partner.telegram_id:
            try:
                await bot.send_message(
                    chat_id=partner.telegram_id,
                    text="Your chat partner has ended the conversation.",
                    reply_markup=types.ReplyKeyboardRemove()
                )
            except Exception as e:
                logger.error(f"Failed to notify partner about chat end: {e}")
    
    # Clear state
    await state.clear()


def register_handlers(dp: Dispatcher):
    dp.include_router(router) 