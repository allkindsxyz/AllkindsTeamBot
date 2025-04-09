import asyncio
import logging
import traceback
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

# Completely disable all SQL logs
logging.getLogger('sqlalchemy.engine').setLevel(logging.CRITICAL)
logging.getLogger('sqlalchemy').setLevel(logging.CRITICAL)
logging.getLogger('aiosqlite').setLevel(logging.CRITICAL)

# Import after logging setup to avoid any logger configuration from these imports
from src.db.base import async_session_factory, Base
from src.db.models import User, Group, Answer, Question, GroupMember
from src.db.repositories.group import group_repo
from src.db.repositories.user import user_repo
from src.db.repositories.answer import answer_repo
from src.bot.utils.matching import find_best_match, calculate_cosine_similarity

async def test_match():
    print("\n===== STARTING MATCH TEST =====")
    try:
        async with async_session_factory() as session:
            # Fetch all groups
            print("\n1. Fetching all groups...")
            result = await session.execute(select(Group))
            groups = result.scalars().all()
            
            if not groups:
                print("No groups found in the database.")
                return
            
            print(f"Found {len(groups)} groups.")
            
            # Select the first group for testing
            group = groups[0]
            print(f"Using group: ID {group.id}, Name: {group.name}")
            
            # Get members of the group
            members = await group_repo.get_group_members(session, group.id)
            print(f"Group has {len(members)} members.")
            
            if len(members) < 2:
                print("Need at least 2 members in the group to test matching.")
                return
            
            # Select the first user as our test subject
            user_id = members[0].user_id
            print(f"\n2. Testing matches for User {user_id}...")
            
            # Get user details
            user = await user_repo.get(session, user_id)
            print(f"User: {user.first_name} {user.last_name or ''} (TG ID: {user.telegram_id})")
            
            # Get user answers
            query = select(Answer).join(
                Question, Answer.question_id == Question.id
            ).where(
                Answer.user_id == user_id,
                Question.group_id == group.id
            )
            result = await session.execute(query)
            user_answers = result.scalars().all()
            print(f"User has {len(user_answers)} answers.")
            
            # Find the best match
            print("\n3. Finding best match...")
            match_result = await find_best_match(session, user_id, group.id)
            
            # Display results
            if not match_result:
                print("No match found.")
                return
                
            match_id, score, common_questions, category_scores, category_counts = match_result
            score_percentage = score * 100
            
            # Get match user details
            match_user = await user_repo.get(session, match_id)
            
            print("\n=== MATCH RESULTS ===")
            print(f"Best match: User {match_id} ({match_user.first_name} {match_user.last_name or ''}, TG ID: {match_user.telegram_id})")
            print(f"Raw similarity score: {score}")
            print(f"Converted percentage: {int(score_percentage)}%")
            print(f"Common questions: {len(common_questions)}")
            
            print("\nCategory scores:")
            for category, cat_score in category_scores.items():
                cat_percentage = int((cat_score + 1) * 50)
                question_count = category_counts.get(category, 0)
                print(f"• {category}: {cat_percentage}% ({question_count} questions)")
            
            # Detailed answer comparison
            print("\n=== DETAILED ANSWER COMPARISON ===")
            all_agreements = []
            all_disagreements = []
            
            # Get user and match answers for common questions
            for q_id in common_questions:
                # Get question details
                query = select(Question).where(Question.id == q_id)
                result = await session.execute(query)
                question = result.scalar_one_or_none()
                
                # Get user's answer
                query = select(Answer).where(
                    Answer.user_id == user_id,
                    Answer.question_id == q_id
                )
                result = await session.execute(query)
                user_answer = result.scalar_one_or_none()
                
                # Get match's answer
                query = select(Answer).where(
                    Answer.user_id == match_id,
                    Answer.question_id == q_id
                )
                result = await session.execute(query)
                match_answer = result.scalar_one_or_none()
                
                if user_answer and match_answer:
                    user_val = user_answer.value
                    match_val = match_answer.value
                    
                    # Compare answers (convert to binary for easier comparison)
                    user_binary = 1 if user_val > 0 else -1
                    match_binary = 1 if match_val > 0 else -1
                    
                    if user_binary == match_binary:
                        all_agreements.append((q_id, question.text if question else f"Question {q_id}", user_val, match_val))
                    else:
                        all_disagreements.append((q_id, question.text if question else f"Question {q_id}", user_val, match_val))
            
            # Display agreements
            print(f"AGREEMENTS ({len(all_agreements)}/{len(all_agreements) + len(all_disagreements)}, {int(len(all_agreements) / (len(all_agreements) + len(all_disagreements)) * 100)}%):")
            for i, (q_id, q_text, user_val, match_val) in enumerate(all_agreements, 1):
                user_binary = "+1" if user_val > 0 else "-1"
                match_binary = "+1" if match_val > 0 else "-1"
                print(f"{i}. Q{q_id}: \"{q_text}\"")
                print(f"   User's answer: {user_val} ({user_binary})")
                print(f"   Match's answer: {match_val} ({match_binary})")
            
            # Display disagreements
            print(f"\nDISAGREEMENTS ({len(all_disagreements)}/{len(all_agreements) + len(all_disagreements)}, {int(len(all_disagreements) / (len(all_agreements) + len(all_disagreements)) * 100)}%):")
            for i, (q_id, q_text, user_val, match_val) in enumerate(all_disagreements, 1):
                user_binary = "+1" if user_val > 0 else "-1"
                match_binary = "+1" if match_val > 0 else "-1"
                print(f"{i}. Q{q_id}: \"{q_text}\"")
                print(f"   User's answer: {user_val} ({user_binary})")
                print(f"   Match's answer: {match_val} ({match_binary})")
            
            # Verification
            print("\n=== VERIFICATION ===")
            # Manually verify the score calculation
            user_vectors = []
            match_vectors = []
            
            for q_id in common_questions:
                # Get user's answer
                query = select(Answer).where(
                    Answer.user_id == user_id,
                    Answer.question_id == q_id
                )
                result = await session.execute(query)
                user_answer = result.scalar_one_or_none()
                
                # Get match's answer
                query = select(Answer).where(
                    Answer.user_id == match_id,
                    Answer.question_id == q_id
                )
                result = await session.execute(query)
                match_answer = result.scalar_one_or_none()
                
                if user_answer and match_answer:
                    # Convert to binary for similarity calculation
                    user_binary = 1 if user_answer.value > 0 else -1
                    match_binary = 1 if match_answer.value > 0 else -1
                    
                    user_vectors.append(user_binary)
                    match_vectors.append(match_binary)
            
            # Calculate similarity manually
            manual_similarity = calculate_cosine_similarity(user_vectors, match_vectors)
            manual_percentage = manual_similarity * 100
            
            print(f"Manually calculated similarity: {manual_similarity}")
            print(f"Manually calculated percentage: {int(manual_percentage)}%")
            print(f"Match from function: {score} ({int(score_percentage)}%)")
            
            # Display what would be shown to the user in the app
            print("\n=== WHAT THE USER SEES ===")
            cohesion_percentage = int(score * 100)
            match_text = (
                f"🎉 <b>Found your most resonating team member!</b>\n\n"
                f"<b>Cohesion Score: {cohesion_percentage}%</b>\n"
                f"You share perspectives on <b>{len(common_questions)} questions</b>.\n\n"
            )
            
            # Add category breakdown
            match_text += "<b>Category Breakdown:</b>\n"
            for category, cat_score in category_scores.items():
                cat_percentage = int(cat_score * 100)  # Convert to percentage
                question_count = category_counts.get(category, 0)
                match_text += f"• <b>{category}</b>: {cat_percentage}% ({question_count} questions)\n"
            
            print(match_text)
            print("\n========== TEST COMPLETE ==========")
            
    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_match()) 