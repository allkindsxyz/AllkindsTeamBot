import os
import sys
import asyncio
from collections import defaultdict
import difflib
from sqlalchemy import select, func, text
from loguru import logger

# Add project root to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.db.base import async_session_factory
from src.db.models.question import Question
from src.db.models.group import Group

async def analyze_duplicate_questions():
    """Analyze and report potential duplicate questions in the database."""
    async with async_session_factory() as session:
        # Get all active questions
        query = select(Question).where(Question.is_active == True)
        result = await session.execute(query)
        questions = result.scalars().all()
        
        print(f"\nTotal active questions: {len(questions)}")
        
        # 1. Check for exact duplicates (case insensitive)
        exact_duplicates = defaultdict(list)
        for q in questions:
            normalized_text = q.text.lower().strip()
            exact_duplicates[normalized_text].append(q)
        
        # Filter to keep only those with multiple entries
        exact_duplicates = {text: qs for text, qs in exact_duplicates.items() if len(qs) > 1}
        
        if exact_duplicates:
            print("\n===== EXACT DUPLICATES =====")
            for text, duplicates in exact_duplicates.items():
                print(f"\nDuplicate text: \"{text}\"")
                for q in duplicates:
                    # Get group name
                    group_query = select(Group).where(Group.id == q.group_id)
                    group_result = await session.execute(group_query)
                    group = group_result.scalar_one_or_none()
                    group_name = group.name if group else "Unknown Group"
                    
                    print(f"  ID: {q.id}, Group: {group_name} (ID: {q.group_id}), Author: {q.author_id}, Created: {q.created_at}")
        else:
            print("\nNo exact duplicates found.")
        
        # 2. Check for similar questions (fuzzy matching)
        similarity_threshold = 0.85  # Adjust as needed
        similar_questions = []
        
        # Compare each question with all others
        for i, q1 in enumerate(questions):
            for j, q2 in enumerate(questions[i+1:], i+1):
                # Skip same questions or questions from different groups
                if q1.id == q2.id or q1.group_id != q2.group_id:
                    continue
                
                # Calculate similarity ratio
                similarity = difflib.SequenceMatcher(None, 
                                                    q1.text.lower().strip(), 
                                                    q2.text.lower().strip()).ratio()
                
                if similarity >= similarity_threshold:
                    similar_questions.append((q1, q2, similarity))
        
        if similar_questions:
            print("\n===== SIMILAR QUESTIONS =====")
            for q1, q2, similarity in sorted(similar_questions, key=lambda x: x[2], reverse=True):
                # Get group name
                group_query = select(Group).where(Group.id == q1.group_id)
                group_result = await session.execute(group_query)
                group = group_result.scalar_one_or_none()
                group_name = group.name if group else "Unknown Group"
                
                print(f"\nSimilarity: {similarity:.2f} in group: {group_name} (ID: {q1.group_id})")
                print(f"  Question 1 (ID: {q1.id}): \"{q1.text}\"")
                print(f"  Question 2 (ID: {q2.id}): \"{q2.text}\"")
        else:
            print("\nNo similar questions found.")
        
        # 3. Analyze questions by group
        group_query = select(Group)
        group_result = await session.execute(group_query)
        groups = group_result.scalars().all()
        
        print("\n===== QUESTIONS BY GROUP =====")
        for group in groups:
            # Count questions in this group
            count_query = select(func.count()).select_from(Question).where(
                Question.group_id == group.id,
                Question.is_active == True
            )
            count_result = await session.execute(count_query)
            question_count = count_result.scalar_one()
            
            print(f"\nGroup: {group.name} (ID: {group.id})")
            print(f"  Questions: {question_count}")

if __name__ == "__main__":
    asyncio.run(analyze_duplicate_questions()) 