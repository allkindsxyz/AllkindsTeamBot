#!/usr/bin/env python3
import re

with open('src/bot/handlers/start.py', 'r') as f:
    content = f.read()

pattern = r'(# Find matches for the user in this group.*?logger\.info\(f\"Finding matches for user \{db_user\.id\} in group \{group_id\}\"\))\s+# Deduct points from the initiating user\s+db_user\.points -= FIND_MATCH_COST\s+session\.add\(db_user\)\s+await session\.commit\(\)\s+logger\.info\(f\"Deducted \{FIND_MATCH_COST\} points from user \{db_user\.id\}, new balance: \{db_user\.points\}\"\)\s+(# Find matches\s+match_results = await find_matches\(session, db_user\.id, int\(group_id\)\))'

replacement = r'''\1

        # Find matches first to avoid point deduction if no matches are found
        \2
        
        if not match_results or len(match_results) == 0:
            # No matches found - no need to deduct points
            await message.reply(
                "😔 No matches found at this time. Please try again later when more group members have answered questions."
            )
            return
        
        # Deduct points from the initiating user - only now that we know there are matches
        old_points = db_user.points
        db_user.points -= FIND_MATCH_COST
        session.add(db_user)
        await session.commit()
        logger.info(f"Deducted {FIND_MATCH_COST} points from user {db_user.id}, new balance: {db_user.points} (was {old_points})")'''

updated_content = re.sub(pattern, replacement, content, flags=re.DOTALL)

with open('src/bot/handlers/start.py', 'w') as f:
    f.write(updated_content)

print("Updated on_find_match function successfully") 