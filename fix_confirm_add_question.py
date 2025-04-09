#!/usr/bin/env python3
import re
from pathlib import Path

def fix_file():
    file_path = Path("src/bot/handlers/start.py")
    print(f"Processing {file_path}...")
    
    # Read the file
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Create a backup
    backup_path = f"{file_path}.bak.add_question_fix"
    with open(backup_path, 'w') as f:
        f.write(content)
    print(f"Created backup at {backup_path}")
    
    # Define the properly indented function
    correct_function = """async def on_confirm_add_question(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    \"\"\"Handle confirmation of adding a new question.\"\"\"
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
        
        # Delete any validation message if it exists
        if validation_msg_id:
            try:
                await callback.bot.delete_message(
                    chat_id=callback.message.chat.id,
                    message_id=validation_msg_id
                )
            except Exception as e:
                logger.warning(f"Failed to delete validation message: {e}")
        
        # Get group to include in notification
        group = await group_repo.get(session, group_id)
        if not group:
            logger.error(f"Group {group_id} not found when adding question {new_question.id}")
            return
            
        # Send a notification about this question to all group members
        await send_question_notification(callback.bot, new_question.id, group_id, session)
        
        # Also send a confirmation to the author (this message will remain)
        confirm_text = f"✅ Your question has been added to {group.name}."
        
        # Create a keyboard that lets them view their question now
        keyboard = get_answer_keyboard_with_skip(new_question.id)
        
        # Get the current keyboard (if any) and add a "Back to menu" button
        current_rows = keyboard.inline_keyboard if keyboard else []
        current_rows.append([
            types.InlineKeyboardButton(
                text="◀️ Back to Menu",
                callback_data="show_start_menu"
            )
        ])
        
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=current_rows)
        
        await callback.bot.send_message(
            chat_id=callback.message.chat.id,
            text=confirm_text + "\\n\\n" + question_text,
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error(f"Error adding question: {e}")
        await callback.answer("Error adding question. Please try again.", show_alert=True)
        # Don't change state if there's an error
"""

    # Find all instances of the function and replace them
    pattern = r"async def on_confirm_add_question\(callback: types\.CallbackQuery, state: FSMContext, session: AsyncSession\) -> None:[\s\S]+?(?=\n\n\n|\n\n#|\nasync def)"
    
    # Count occurrences and replace
    matches = re.findall(pattern, content)
    if matches:
        print(f"Found {len(matches)} instances of on_confirm_add_question")
        content = re.sub(pattern, correct_function, content)
        
        # Write the fixed content
        with open(file_path, 'w') as f:
            f.write(content)
        
        print(f"Fixed {len(matches)} instances of on_confirm_add_question")
    else:
        print("No instances of on_confirm_add_question found!")

if __name__ == "__main__":
    fix_file()
    print("Done!") 