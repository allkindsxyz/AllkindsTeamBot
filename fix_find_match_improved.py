#!/usr/bin/env python3
"""
Improve the find_matches function in match_repo.py to fix transaction handling issues,
and also modify handlers to find matches before deducting points.
"""

import re
import sys
from pathlib import Path

# Path to files
MATCH_REPO_FILE = Path("src/db/repositories/match_repo.py")
START_PY_FILE = Path("src/bot/handlers/start.py")

def improve_find_matches_function():
    """Updates the find_matches function to ensure proper session handling."""
    print(f"Updating find_matches function in {MATCH_REPO_FILE}")
    
    if not MATCH_REPO_FILE.exists():
        print(f"Error: File not found: {MATCH_REPO_FILE}")
        return False
    
    # Read the current file
    current_content = MATCH_REPO_FILE.read_text()
    
    # Create improved implementation
    improved_implementation = """@track_db
@with_retry(max_attempts=3, base_delay=0.5, max_delay=5.0)
async def find_matches(session: AsyncSession, user_id: int, group_id: int) -> list:
    print(f"DEBUG_MATCH: find_matches called with user_id={user_id}, group_id={group_id}")
    logger.info(f"DEBUG_MATCH: find_matches called with user_id={user_id}, group_id={group_id}")
    \"\"\"
    Find potential matches for a user in a group.
    
    Args:
        session: Database session
        user_id: ID of the user to find matches for
        group_id: ID of the group to find matches in
        
    Returns:
        A list of tuples containing (matched_user_id, cohesion_score, common_questions, category_scores, category_counts)
        The list is sorted by cohesion_score in descending order.
    \"\"\"
    logger.info(f"[DEBUG_MATCH_DB] find_matches called with user_id={user_id}, group_id={group_id}")
    
    # For Railway debugging, log the session state
    if IS_RAILWAY:
        logger.info(f"RAILWAY DB DEBUG: Session info - id={id(session)}, is_active={session.is_active}")
    
    try:
        from src.db.models import GroupMember, User
        from src.bot.utils.matching import calculate_cohesion_scores
        
        logger.info(f"Starting find_matches for user {user_id} in group {group_id}")
        
        # Ensure we have a clean session state - commit any pending changes
        try:
            if session.is_active:
                await session.commit()
                logger.info("Session committed before starting match search")
        except Exception as commit_error:
            logger.error(f"Error committing session before match search: {commit_error}")
        
        # Get all other active users in the same group
        query = (
            select(User.id)
            .join(GroupMember, GroupMember.user_id == User.id)
            .where(
                GroupMember.group_id == group_id,
                GroupMember.user_id != user_id,
                User.is_active == True
            )
        )
        
        try:
            result = await session.execute(query)
            potential_matches = result.scalars().all()
            
            logger.info(f"Found {len(potential_matches)} potential matches for user {user_id} in group {group_id}")
            
            # Extra Railway logging
            if IS_RAILWAY:
                logger.info(f"RAILWAY DB DEBUG: potential_matches query SQL = {str(query)}")
                logger.info(f"RAILWAY DB DEBUG: potential_matches = {potential_matches}")
                
        except Exception as db_error:
            logger.error(f"Database error when finding potential matches: {str(db_error)}")
            if IS_RAILWAY:
                logger.error(f"RAILWAY DB ERROR: {str(db_error)}")
                logger.error(f"Traceback: {traceback.format_exc()}")
            return []
        
        # If no potential matches, return early
        if not potential_matches:
            logger.info(f"No potential matches found for user {user_id} in group {group_id}")
            return []
            
        # Calculate cohesion scores with each potential match
        match_results = []
        for potential_match_id in potential_matches:
            try:
                # Ensure session is active before calculating cohesion
                session = await ensure_active_session(session)
                
                cohesion_score, common_questions, category_scores, category_counts = await calculate_cohesion_scores(
                    session, user_id, potential_match_id, group_id
                )
                
                # Only include if they have common questions and meet minimum threshold
                if common_questions >= 3:  # Using the same threshold as MIN_SHARED_QUESTIONS
                    match_results.append((
                        potential_match_id,  # matched user ID
                        cohesion_score,      # overall cohesion score
                        common_questions,    # number of common questions
                        category_scores,     # dictionary of category scores
                        category_counts      # dictionary of question counts per category
                    ))
                    logger.debug(f"Match with user {potential_match_id}: score={cohesion_score}, questions={common_questions}")
            except Exception as e:
                logger.error(f"Error calculating cohesion with user {potential_match_id}: {e}")
                if IS_RAILWAY:
                    logger.error(f"RAILWAY ERROR in calculate_cohesion_scores: {str(e)}")
                    logger.error(f"Traceback: {traceback.format_exc()}")
                continue
        
        # Sort by cohesion score (highest first)
        match_results.sort(key=lambda x: x[1], reverse=True)
        
        logger.info(f"Found {len(match_results)} valid matches for user {user_id} in group {group_id}")
        return match_results
    except Exception as e:
        logger.error(f"Error in find_matches: {e}")
        if IS_RAILWAY:
            logger.error(f"RAILWAY ERROR in find_matches: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
        return []"""
    
    # Replace the find_matches function 
    find_matches_pattern = r"@track_db\n@with_retry\(max_attempts=3,.*?return \[\]"
    if re.search(find_matches_pattern, current_content, flags=re.DOTALL):
        updated_content = re.sub(find_matches_pattern, improved_implementation, current_content, flags=re.DOTALL)
        
        # Back up the original file
        backup_file = MATCH_REPO_FILE.with_suffix('.py.bak')
        backup_file.write_text(current_content)
        print(f"Created backup at {backup_file}")
        
        # Write the updated content
        MATCH_REPO_FILE.write_text(updated_content)
        print("Successfully updated find_matches function")
        return True
    else:
        print("Could not find the find_matches function in the file")
        return False


def fix_first_handler_transaction():
    """Updates the first handler (around line 9807) to fix the transaction order."""
    print("Updating first handle_find_match_message function to improve transaction handling")
    
    if not START_PY_FILE.exists():
        print(f"Error: File not found: {START_PY_FILE}")
        return False
    
    # Read the file
    content = START_PY_FILE.read_text()
    
    # Pattern to identify the point deduction section in the first handler
    deduction_pattern = r'(# Get count of other users in the group for logging.*?logger\.info\(f\"Group \{group_id\} has \{other_members_count\} other members besides user \{db_user\.id\}\"\))\s+# Deduct points from the initiating user\s+db_user\.points -= FIND_MATCH_COST\s+session\.add\(db_user\)\s+await session\.commit\(\)\s+logger\.info\(f\"Deducted \{FIND_MATCH_COST\} points from user \{db_user\.id\}, new balance: \{db_user\.points\}\"\)\s+(# Find matches\s+logger\.info\(f\"Calling find_matches for user \{db_user\.id\} in group \{group_id\}\"\))'
    
    # Replacement with corrected order and match checking
    replacement = r'''\1

        # Find matches first to avoid point deduction if no matches are found
        \2
        try:
            match_results = await find_matches(session, db_user.id, int(group_id))
            logger.info(f"Found {len(match_results)} potential matches for user {db_user.id} in group {group_id}")
        except Exception as match_error:
            logger.error(f"Error in find_matches call: {str(match_error)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            
            await message.answer("❌ An error occurred while finding matches. Please try again later.")
            await show_group_menu(message, group_id, group.name, state, session=session)
            return
        
        if not match_results or len(match_results) == 0:
            # No matches found - no need to deduct points
            logger.info(f"No matches found for user {db_user.id} in group {group_id}")
            
            try:
                # Send no matches message
                await message.answer(
                    "😔 No matches found at this time. Please try again later when more group members have answered questions."
                )
                
                # Show group menu to maintain context
                await show_group_menu(message, group_id, group.name, state, session=session)
            except Exception as menu_error:
                logger.error(f"Error showing group menu after no matches: {menu_error}")
                await message.answer("Please use /start to return to the main menu.")
            
            return
        
        # Deduct points from the initiating user - only now that we know there are matches
        old_points = db_user.points
        db_user.points -= FIND_MATCH_COST
        session.add(db_user)
        await session.commit()
        logger.info(f"Deducted {FIND_MATCH_COST} points from user {db_user.id}, new balance: {db_user.points} (was {old_points})")'''
    
    # Check if the pattern is found
    if re.search(deduction_pattern, content, flags=re.DOTALL):
        # Replace the pattern
        updated_content = re.sub(deduction_pattern, replacement, content, flags=re.DOTALL)
        
        # Write it back
        START_PY_FILE.write_text(updated_content)
        print("Successfully updated first handle_find_match_message function (line ~9807)")
        return True
    else:
        print("Could not find the transaction pattern in the first handler. Cannot update safely.")
        return False


def fix_second_handler_transaction():
    """Updates the second handler (around line 15289) to fix the transaction order."""
    print("Updating second handle_find_match_message function to improve transaction handling")
    
    if not START_PY_FILE.exists():
        print(f"Error: File not found: {START_PY_FILE}")
        return False
    
    # Read the file
    content = START_PY_FILE.read_text()
    
    # Pattern for the second handler - adjusted to match the actual pattern
    second_handler_pattern = r'(# Get count of other users in the group for logging.*?logger\.info\(f\"Group \{group_id\} has \{other_members_count\} other members besides user \{db_user\.id\}\"\))\s+# Deduct points from the initiating user\s+db_user\.points -= FIND_MATCH_COST\s+session\.add\(db_user\)\s+await session\.commit\(\)\s+logger\.info\(f\"Deducted \{FIND_MATCH_COST\} points from user \{db_user\.id\}, new balance: \{db_user\.points\}\"\)\s+# Find matches'
    
    # Improved implementation
    second_handler_replacement = r'''\1
        
        # Find matches first to avoid point deduction if no matches are found
        logger.info(f"Calling find_matches for user {db_user.id} in group {group_id}")
        try:
            match_results = await find_matches(session, db_user.id, int(group_id))
            logger.info(f"Found {len(match_results)} potential matches for user {db_user.id} in group {group_id}")
        except Exception as match_error:
            logger.error(f"Error in find_matches call: {str(match_error)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            
            await message.answer("❌ An error occurred while finding matches. Please try again later.")
            await show_group_menu(message, group_id, group.name, state, session=session)
            return
        
        if not match_results or len(match_results) == 0:
            # No matches found - no need to deduct points
            logger.info(f"No matches found for user {db_user.id} in group {group_id}")
            
            try:
                # Send no matches message
                await message.answer(
                    "😔 No matches found at this time. Please try again later when more group members have answered questions."
                )
                
                # Show group menu to maintain context
                await show_group_menu(message, group_id, group.name, state, session=session)
            except Exception as menu_error:
                logger.error(f"Error showing group menu after no matches: {menu_error}")
                await message.answer("Please use /start to return to the main menu.")
            
            return
        
        # Get the top match
        matched_user_id, cohesion_score, common_questions, category_scores, category_counts = match_results[0]
            
        # Check if there is an existing match record
        existing_match = await get_match(session, db_user.id, matched_user_id, int(group_id))
        
        # Check if there is an existing chat session
        existing_chat = await get_chat_by_participants(
            session, db_user.id, matched_user_id, int(group_id)
        )
        
        # If no existing match or chat, create a new match record
        if not existing_match:
            match_record = Match(
                user1_id=db_user.id,
                user2_id=matched_user_id,
                group_id=int(group_id),
                score=cohesion_score,
                common_questions=common_questions,
                created_at=datetime.now()
            )
            session.add(match_record)
            await session.commit()
            logger.info(f"Created new match record for users {db_user.id} and {matched_user_id} in group {group_id}")
        else:
            logger.info(f"Using existing match record between users {db_user.id} and {matched_user_id}")
        
        # Deduct points from the initiating user - only now that we know there are matches
        old_points = db_user.points
        db_user.points -= FIND_MATCH_COST
        session.add(db_user)
        await session.commit()
        logger.info(f"Deducted {FIND_MATCH_COST} points from user {db_user.id}, new balance: {db_user.points} (was {old_points})")'''
    
    # Check if the pattern is found
    if re.search(second_handler_pattern, content, flags=re.DOTALL):
        # Replace the pattern
        updated_content = re.sub(second_handler_pattern, second_handler_replacement, content, flags=re.DOTALL)
        
        # Write it back
        START_PY_FILE.write_text(updated_content)
        print("Successfully updated second handle_find_match_message function (line ~15289)")
        return True
    else:
        print("Could not find the transaction pattern in the second handler. Cannot update safely.")
        return False


def main():
    """Main function to fix all matching issues."""
    print("Starting comprehensive fix for match finding functionality...")
    
    # Back up the file before making changes
    backup_file = START_PY_FILE.with_suffix('.py.bak')
    if not backup_file.exists():
        backup_content = START_PY_FILE.read_text()
        backup_file.write_text(backup_content)
        print(f"Created backup of start.py at {backup_file}")
    
    repo_fixed = improve_find_matches_function()
    first_handler_fixed = fix_first_handler_transaction()
    second_handler_fixed = fix_second_handler_transaction()
    
    if repo_fixed and first_handler_fixed and second_handler_fixed:
        print("✅ All components successfully fixed!")
        print("The bot should now handle matches more reliably, especially in Railway deployment.")
        return 0
    elif not repo_fixed and not first_handler_fixed and not second_handler_fixed:
        print("❌ Could not fix any component.")
        print("Please check the files manually or contact a developer for assistance.")
        return 2
    else:
        print("⚠️ Partial fix applied:")
        if repo_fixed:
            print("  ✅ find_matches function was improved")
        if first_handler_fixed:
            print("  ✅ First handler transaction flow was improved")
        if second_handler_fixed:
            print("  ✅ Second handler transaction flow was improved")
        print("The matching functionality should work better but may still have issues.")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 