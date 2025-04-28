#!/usr/bin/env python3
"""
Fix indentation error in start.py
"""

import re
from pathlib import Path

# Path to start.py
START_PY_FILE = Path("src/bot/handlers/start.py")

def fix_indentation():
    """Fix the indentation error in handle_add_question_message function"""
    print(f"Attempting to fix indentation in {START_PY_FILE}")
    
    if not START_PY_FILE.exists():
        print(f"Error: File not found: {START_PY_FILE}")
        return False
    
    # Read the file content
    content = START_PY_FILE.read_text()
    
    # Find the problematic function definition
    pattern = r"async def handle_add_question_message\(message: types\.Message, state: FSMContext, session: AsyncSession = None\) -> None:\nfrom"
    
    if re.search(pattern, content):
        print("Found problematic function definition!")
        
        # Create a backup
        backup_file = START_PY_FILE.with_suffix('.py.bak2')
        backup_file.write_text(content)
        print(f"Created backup at {backup_file}")
        
        # Replace the function definition with a proper one
        replacement = """async def handle_add_question_message(message: types.Message, state: FSMContext, session: AsyncSession = None) -> None:
    \"\"\"Handle the 'Add Question' button from the reply keyboard.\"\"\"
    logger.info(f"User {message.from_user.id} pressed Add Question button")
    
    # Get current data
    data = await state.get_data()
    group_id = data.get("current_group_id")
    
    if not group_id:
        await message.answer("Please select a group first.")
        return
        
    # Get the user from the database
    user_tg = message.from_user
    db_user = await user_repo.get_by_telegram_id(session, user_tg.id)
    
    if not db_user:
        logger.error(f"User with Telegram ID {user_tg.id} not found in database")
        await message.answer("Error: Your user account was not found. Please try /start again.")
        return
    
    # Get the group from the database
    group = await group_repo.get(session, int(group_id))
    if not group:
        logger.error(f"Group {group_id} not found in database")
        await message.answer("Group not found. Please restart by clicking on the group link.")
        return
    
    # Set state to QuestionFlow.waiting_for_question
    await state.set_state(QuestionFlow.waiting_for_question)
    
    # Store group_id in state
    await state.update_data(current_group_id=group_id)
    
    # Send instructions
    await message.answer(
        "Please enter your yes/no question.\\n\\n"
        "Good questions should be:\\n"
        "• Clear and concise\\n"
        "• Answerable with yes/no\\n"
        "• Related to values or preferences\\n\\n"
        "Example: \\"Do you believe in giving second chances?\\"\\n\\n"
        "Type /cancel to cancel."
    )

from"""
        
        fixed_content = re.sub(pattern, replacement, content)
        
        # Write the fixed content back to the file
        START_PY_FILE.write_text(fixed_content)
        print("Successfully fixed indentation in file!")
        return True
    else:
        print("Could not find the problematic function definition.")
        return False

if __name__ == "__main__":
    if fix_indentation():
        print("✅ Indentation fixed successfully!")
    else:
        print("❌ Failed to fix indentation.") 