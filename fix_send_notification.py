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
    backup_path = f"{file_path}.bak.notification_fix"
    with open(backup_path, 'w') as f:
        f.write(content)
    print(f"Created backup at {backup_path}")
    
    # Define the properly indented function
    correct_function = """async def send_question_notification(bot: Bot, question_id: int, group_id: int, session: AsyncSession) -> None:
    \"\"\"Send a notification about a new question to all group members.\"\"\"
    question = await question_repo.get(session, question_id)
    if not question:
        logger.error(f"Question {question_id} not found for notification")
        return
        
    group = await group_repo.get(session, group_id)
    if not group:
        logger.error(f"Group {group_id} not found for notification")
        return
    
    # Get all group members
    group_members = await group_repo.get_group_members(session, group_id)
    logger.info(f"Sending notification about question {question_id} to {len(group_members)} group members")
    
    # Format the notification message with plain question text
    notification_text = (
        f"<b>📝 New Question in {group.name}</b>\\n\\n"
        f"{question.text}"
    )
    
    # Add answer buttons
    keyboard = get_answer_keyboard_with_skip(question_id)
    
    # Send to each member except the author
    notify_count = 0
    for member in group_members:
        if member.user_id != question.author_id:
            try:
                # Get user's Telegram ID
                user = await user_repo.get(session, member.user_id)
                if user and user.telegram_id:
                    logger.debug(f"Sending notification for question {question_id} to user {user.telegram_id} (ID: {user.id})")
                    sent_message = await bot.send_message(
                        chat_id=user.telegram_id,
                        text=notification_text,
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
                    if sent_message:
                        notify_count += 1
                        logger.info(f"Successfully sent question notification to user {user.telegram_id}")
                    else:
                        logger.warning(f"Failed to send notification to user {user.telegram_id} - message not returned")
            except Exception as e:
                logger.error(f"Failed to send question notification to user {member.user_id}: {e}")
    
    logger.info(f"Completed sending notifications: {notify_count} of {len(group_members)-1} users notified about question {question_id}")
"""

    # Find all instances of the function and replace them
    pattern = r"async def send_question_notification\(bot: Bot, question_id: int, group_id: int, session: AsyncSession\) -> None:[\s\S]+?(?=\n\n\n|\n\n#)"
    
    # Count occurrences and replace
    matches = re.findall(pattern, content)
    if matches:
        print(f"Found {len(matches)} instances of send_question_notification")
        content = re.sub(pattern, correct_function, content)
        
        # Write the fixed content
        with open(file_path, 'w') as f:
            f.write(content)
        
        print(f"Fixed {len(matches)} instances of send_question_notification")
    else:
        print("No instances of send_question_notification found!")

if __name__ == "__main__":
    fix_file()
    print("Done!") 