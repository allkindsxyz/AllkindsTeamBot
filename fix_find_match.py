#!/usr/bin/env python3
"""
Improve the find_matches function in match_repo.py to fix transaction handling issues.
"""

import re
import sys
from pathlib import Path

# Match repo file location
MATCH_REPO_FILE = Path("src/db/repositories/match_repo.py")

def improve_find_matches_function():
    """Updates the find_matches function to ensure proper transaction handling."""
    print(f"Updating find_matches function in {MATCH_REPO_FILE}")
    
    if not MATCH_REPO_FILE.exists():
        print(f"Error: File not found: {MATCH_REPO_FILE}")
        return False
    
    # Read the current file
    current_content = MATCH_REPO_FILE.read_text()
    
    # Create improved implementation
    improved_implementation = """@track_db
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
    find_matches_pattern = r"@track_db\nasync def find_matches\(.*?return \[\]"
    if re.search(find_matches_pattern, current_content, re.DOTALL):
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

# Define a function to improve the handler's transaction handling
def improve_handler_transaction():
    """Updates handler in start.py to fix transaction handling when finding matches."""
    print("Updating handle_find_match_message function to improve transaction handling")
    
    # Path to the start.py file
    start_py_file = Path("src/bot/handlers/start.py")
    
    if not start_py_file.exists():
        print(f"Error: File not found: {start_py_file}")
        return False
    
    # Read the file
    content = start_py_file.read_text()
    
    # Find the points deduction and match finding section
    # This is a critical part we need to reorder for safety
    deduction_pattern = r"# Deduct points from the initiating user\s+old_points = db_user\.points\s+db_user\.points -= FIND_MATCH_COST\s+session\.add\(db_user\)\s+await session\.commit\(\)\s+.*?\s+# Find matches\s+.*?\s+match_results = await find_matches\(session, db_user\.id, int\(group_id\)\)"
    
    # The improved implementation puts searching for matches before point deduction
    improved_transaction = """            # Store original points for error recovery
            old_points = db_user.points
            
            # Find matches first to avoid point deduction if no matches are found
            logger.info(f"[DEBUG] Calling find_matches for user {db_user.id} in group {group_id}")
            match_results = await find_matches(session, db_user.id, int(group_id))
            logger.info(f"[DEBUG] Match results count: {len(match_results) if match_results else 0}")
            
            if not match_results or len(match_results) == 0:
                # No matches found - no need to deduct points
                logger.info(f"[DEBUG] No matches found for user {db_user.id} in group {group_id}")
                
                # Send no matches message
                await message.answer(
                    "😔 No matches found at this time. Please try again later when more group members have answered questions."
                )
                
                # Show group menu to maintain context
                await show_group_menu(message, group_id, group.name, state, session=session)
                return
            
            # Deduct points from the initiating user - only now that we know there are matches
            db_user.points -= FIND_MATCH_COST
            session.add(db_user)
            await session.commit()
            logger.info(f"[DEBUG] Deducted {FIND_MATCH_COST} points from user {db_user.id}, new balance: {db_user.points} (was {old_points})")"""
    
    # Check if we found the pattern and can make the replacement
    if re.search(deduction_pattern, content, re.DOTALL):
        # Create backup
        backup_file = start_py_file.with_suffix('.py.bak')
        backup_file.write_text(content)
        print(f"Created backup at {backup_file}")
        
        # Only if the content matches our expectations, try to update it
        updated_content = re.sub(deduction_pattern, improved_transaction, content, flags=re.DOTALL)
        
        # Write the updated file
        start_py_file.write_text(updated_content)
        print("Successfully updated transaction handling in handle_find_match_message")
        return True
    else:
        print("Could not find the expected pattern in start.py. Cannot update safely.")
        return False

def main():
    """Main function to fix both find matches issues."""
    print("Starting fix for find matches functionality...")
    
    repo_fixed = improve_find_matches_function()
    handler_fixed = improve_handler_transaction()
    
    if repo_fixed and handler_fixed:
        print("✅ Both find_matches and handler transaction flow have been improved!")
        print("The bot should now handle matches more reliably, especially in Railway deployment.")
        return 0
    elif repo_fixed:
        print("✅ Only find_matches function was improved. Handler transaction fix failed.")
        print("The match finding should be more reliable, but transaction ordering could still be improved.")
        return 1
    elif handler_fixed:
        print("✅ Only handler transaction flow was improved. find_matches fix failed.")
        print("Match transaction ordering is improved, but additional error handling in find_matches was not added.")
        return 1
    else:
        print("❌ Could not fix either component.")
        print("Please check the files manually or contact a developer for assistance.")
        return 2

if __name__ == "__main__":
    sys.exit(main()) 