import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from src.db.models import User, Answer, GroupMember, Question

MIN_SHARED_QUESTIONS = 3  # Reduced from 10 to match the requirement in the handler

def calculate_cosine_similarity(vec_a: list[int | float], vec_b: list[int | float]) -> float | None:
    """Calculates cosine similarity between two vectors."""
    vec_a_np = np.array(vec_a)
    vec_b_np = np.array(vec_b)

    dot_product = np.dot(vec_a_np, vec_b_np)
    norm_a = np.linalg.norm(vec_a_np)
    norm_b = np.linalg.norm(vec_b_np)

    if norm_a == 0 or norm_b == 0:
        logger.warning(f"Cannot calculate cosine similarity for zero vector(s).")
        return 0.0 # Or None, depending on how you want to handle this edge case

    similarity = dot_product / (norm_a * norm_b)
    return float(similarity)

def calculate_cohesion_score(user1_answers: dict, user2_answers: dict) -> float:
    """
    Calculate cohesion score between two users based on normalized distances.
    
    Args:
        user1_answers: Dict of {question_id: answer_value} for user 1
        user2_answers: Dict of {question_id: answer_value} for user 2
        
    Returns:
        Cohesion score between 0 and 1, where 1 is perfect cohesion
    """
    # Find common questions
    common_question_ids = set(user1_answers.keys()) & set(user2_answers.keys())
    
    if not common_question_ids:
        return 0.0
    
    # Calculate normalized distances
    total_penalty = 0.0
    
    for q_id in common_question_ids:
        # Calculate absolute difference between answers
        abs_diff = abs(user1_answers[q_id] - user2_answers[q_id])
        
        # Normalize by max possible difference (4: from -2 to 2)
        normalized_penalty = abs_diff / 4.0
        
        # Add to total penalty
        total_penalty += normalized_penalty
    
    # Calculate average penalty
    avg_penalty = total_penalty / len(common_question_ids)
    
    # Calculate cohesion score (1 - penalty, so 1 is perfect match)
    cohesion_score = 1.0 - avg_penalty
    
    return cohesion_score

async def find_best_match(session: AsyncSession, user_id: int, group_id: int):
    """
    Find the best match for a user in a group based on their question answers.
    
    Returns:
        Tuple of (matched_user_id, cohesion_score, common_question_ids, category_scores, category_counts)
        or None if no match found.
    """
    logger.info(f"Starting match search for user {user_id} in group {group_id}")
    
    # Get the user's answers in this group
    query = select(Answer.question_id, Answer.value)\
        .join(Question, Question.id == Answer.question_id)\
        .where(Answer.user_id == user_id, Question.group_id == group_id)
    
    result = await session.execute(query)
    user_answers = {row[0]: row[1] for row in result.all()}
    
    logger.info(f"User {user_id} has {len(user_answers)} answers in group {group_id}")
    
    if not user_answers:
        logger.warning(f"User {user_id} has no answers in group {group_id}")
        return None
    
    # Get all other users in this group
    query = select(GroupMember.user_id)\
        .where(GroupMember.group_id == group_id, GroupMember.user_id != user_id)
    
    result = await session.execute(query)
    other_users = [row[0] for row in result.all()]
    
    logger.info(f"Found {len(other_users)} other users in group {group_id} for matching")
    
    if not other_users:
        logger.warning(f"No other users in group {group_id} to match with")
        return None
    
    # Find best match
    best_match = None
    best_cohesion = -1.0
    best_common_questions = []
    
    for other_user_id in other_users:
        # Get other user's answers
        query = select(Answer.question_id, Answer.value)\
            .join(Question, Question.id == Answer.question_id)\
            .where(Answer.user_id == other_user_id, Question.group_id == group_id)
        
        result = await session.execute(query)
        other_user_answers = {row[0]: row[1] for row in result.all()}
        
        logger.debug(f"Checking match with user {other_user_id} who has {len(other_user_answers)} answers in group {group_id}")
        
        # Find common questions
        common_questions = set(user_answers.keys()) & set(other_user_answers.keys())
        
        logger.debug(f"Users {user_id} and {other_user_id} share {len(common_questions)} questions in group {group_id}")
        
        if len(common_questions) < MIN_SHARED_QUESTIONS:  # Need minimum number of common questions
            continue
        
        # Calculate cohesion score using normalized differences
        cohesion = calculate_cohesion_score(user_answers, other_user_answers)
        
        logger.debug(f"Cohesion between {user_id} and {other_user_id}: {cohesion:.4f} over {len(common_questions)} questions")
        
        if cohesion > best_cohesion:
            logger.debug(f"New best match candidate for {user_id}: {other_user_id} with cohesion {cohesion:.4f} over {len(common_questions)} questions.")
            best_match = other_user_id
            best_cohesion = cohesion
            best_common_questions = list(common_questions)
    
    if best_match is None:
        logger.warning(f"No suitable match found for user {user_id} in group {group_id}")
        return None
    
    logger.info(f"Best match found for user {user_id}: {best_match} with cohesion score {best_cohesion} over {len(best_common_questions)} questions")
    
    # Process category-specific scores
    # Get all categories for common questions
    question_categories = {}
    category_questions = {}
    category_scores = {}
    
    # Get category data for all common questions
    for q_id in best_common_questions:
        query = select(Question.id, Question.category).where(Question.id == q_id)
        result = await session.execute(query)
        row = result.fetchone()
        if row:
            category = row[1] or "❓ Other"
            question_categories[q_id] = category
            
            if category not in category_questions:
                category_questions[category] = []
            category_questions[category].append(q_id)
    
    # Calculate cohesion for each category
    for category, q_ids in category_questions.items():
        if len(q_ids) < 1:
            continue
            
        # Create filtered answer dictionaries for this category
        user_category_answers = {q_id: user_answers[q_id] for q_id in q_ids}
        other_user_category_answers = {}
        
        for q_id in q_ids:
            # Get the other user's answers
            query = select(Answer.value).where(
                Answer.user_id == best_match, 
                Answer.question_id == q_id
            )
            other_result = await session.execute(query)
            other_value = other_result.scalar()
            if other_value is not None:
                other_user_category_answers[q_id] = other_value
        
        # Calculate cohesion for this category
        if other_user_category_answers:
            category_cohesion = calculate_cohesion_score(
                user_category_answers, 
                other_user_category_answers
            )
            category_scores[category] = category_cohesion
    
    # Get top categories by number of questions (top 4)
    top_categories = sorted(
        category_questions.keys(), 
        key=lambda c: len(category_questions[c]), 
        reverse=True
    )[:4]  # Top 4 categories
    
    # Create final category data for top categories
    final_category_scores = {cat: category_scores.get(cat, 0.0) for cat in top_categories if cat in category_questions}
    final_category_counts = {cat: len(category_questions[cat]) for cat in top_categories if cat in category_questions}
    
    # Combine remaining categories into "Other"
    remaining_categories = set(category_questions.keys()) - set(top_categories)
    if remaining_categories:
        # Gather all questions from non-top categories
        other_questions = []
        for cat in remaining_categories:
            other_questions.extend(category_questions[cat])
            
        if other_questions:
            # Create filtered answer dictionaries for "Other" category
            user_other_answers = {q_id: user_answers[q_id] for q_id in other_questions}
            other_user_other_answers = {}
            
            for q_id in other_questions:
                query = select(Answer.value).where(
                    Answer.user_id == best_match, 
                    Answer.question_id == q_id
                )
                other_result = await session.execute(query)
                other_value = other_result.scalar()
                if other_value is not None:
                    other_user_other_answers[q_id] = other_value
            
            # Calculate cohesion for "Other" category
            if other_user_other_answers:
                other_cohesion = calculate_cohesion_score(
                    user_other_answers,
                    other_user_other_answers
                )
                final_category_scores["❓ Other"] = other_cohesion
                final_category_counts["❓ Other"] = len(other_questions)
    
    # Return the match result with category data
    return (best_match, best_cohesion, best_common_questions, final_category_scores, final_category_counts)

async def calculate_cohesion_scores(session: AsyncSession, user1_id: int, user2_id: int, group_id: int):
    """
    Calculate cohesion scores between two users in a group.
    
    Args:
        session: Database session
        user1_id: ID of the first user
        user2_id: ID of the second user
        group_id: ID of the group
        
    Returns:
        Tuple of (cohesion_score, common_questions, category_scores, category_counts)
        where:
        - cohesion_score is a float between 0 and 1
        - common_questions is the number of questions both users have answered
        - category_scores is a dict of {category: score}
        - category_counts is a dict of {category: count}
    """
    try:
        # Get user1's answers
        query = select(Answer.question_id, Answer.value)\
            .join(Question, Question.id == Answer.question_id)\
            .where(Answer.user_id == user1_id, Question.group_id == group_id)
        
        result = await session.execute(query)
        user1_answers = {row[0]: row[1] for row in result.all()}
        
        # Get user2's answers
        query = select(Answer.question_id, Answer.value)\
            .join(Question, Question.id == Answer.question_id)\
            .where(Answer.user_id == user2_id, Question.group_id == group_id)
        
        result = await session.execute(query)
        user2_answers = {row[0]: row[1] for row in result.all()}
        
        # Find common questions
        common_question_ids = set(user1_answers.keys()) & set(user2_answers.keys())
        common_questions = len(common_question_ids)
        
        if common_questions < MIN_SHARED_QUESTIONS:
            return 0.0, 0, {}, {}
        
        # Calculate overall cohesion score
        cohesion_score = calculate_cohesion_score(user1_answers, user2_answers)
        
        # Process category-specific scores
        # Get all categories for common questions
        question_categories = {}
        category_questions = {}
        category_scores = {}
        
        # Get category data for all common questions
        for q_id in common_question_ids:
            query = select(Question.id, Question.category).where(Question.id == q_id)
            result = await session.execute(query)
            row = result.fetchone()
            if row:
                category = row[1] or "❓ Other"
                question_categories[q_id] = category
                
                if category not in category_questions:
                    category_questions[category] = []
                category_questions[category].append(q_id)
        
        # Calculate cohesion for each category
        for category, q_ids in category_questions.items():
            if len(q_ids) < 1:
                continue
                
            # Create filtered answer dictionaries for this category
            user1_category_answers = {q_id: user1_answers[q_id] for q_id in q_ids if q_id in user1_answers}
            user2_category_answers = {q_id: user2_answers[q_id] for q_id in q_ids if q_id in user2_answers}
            
            # Calculate cohesion for this category
            if user1_category_answers and user2_category_answers:
                category_cohesion = calculate_cohesion_score(
                    user1_category_answers, 
                    user2_category_answers
                )
                category_scores[category] = category_cohesion
        
        # Get counts for each category
        category_counts = {cat: len(questions) for cat, questions in category_questions.items()}
        
        return cohesion_score, common_questions, category_scores, category_counts
    except Exception as e:
        logger.error(f"Error in calculate_cohesion_scores: {e}")
        # Return a safe fallback
        return 0.0, 0, {}, {} 