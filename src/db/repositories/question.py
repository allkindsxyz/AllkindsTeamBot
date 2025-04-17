from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from src.db.models import Question, Answer
from src.db.repositories.base import BaseRepository
from src.core.question_categorizer import categorize_question


class QuestionRepository(BaseRepository[Question]):
    def __init__(self):
        super().__init__(Question)

    async def create_question(
        self, session: AsyncSession, text: str, author_id: int, group_id: int
    ) -> Question:
        """Creates a new question with categorization."""
        # Categorize the question
        category = await categorize_question(text)
        
        question = await self.create(
            session,
            data={
                "text": text,
                "author_id": author_id,
                "group_id": group_id,
                "category": category,
                # Assuming default values for is_approved, is_active, counts etc.
            }
        )
        # Ensure the transaction is committed
        try:
            await session.commit()
        except Exception as e:
            logger.error(f"Error committing question creation transaction: {e}")
            await session.rollback()
            raise
            
        return question

    async def get_next_question_for_user(
        self, session: AsyncSession, user_id: int, group_id: int, excluded_ids: list[int] = None
    ) -> Question | None:
        """Gets the next unanswered question for a user in a group."""
        # Force a refresh of the session to ensure we have the latest data
        # This is especially important for PostgreSQL in Railway
        try:
            await session.commit()  # Commit any pending changes
        except Exception as e:
            logger.warning(f"Error committing session before get_next_question_for_user: {e}")
        
        # Initialize excluded_ids if None
        if excluded_ids is None:
            excluded_ids = []
        
        # Get all answers from this user for questions in this group
        # to find questions they haven't answered yet
        try:
            # Get the specific user's answers directly first for debugging
            user_answers_query = select(Answer).where(
                Answer.user_id == user_id
            )
            user_answers_result = await session.execute(user_answers_query)
            user_answers = user_answers_result.scalars().all()
            logger.info(f"User {user_id} has {len(user_answers)} total answers (across all groups)")
            
            # Now get specific answers for this group using an explicit join
            answered_subquery = (
                select(Answer.question_id)
                .join(Question, Question.id == Answer.question_id)
                .where(
                    Answer.user_id == user_id,
                    Question.group_id == group_id
                )
                .subquery()
            )
            
            # Log the actual answered question IDs for debugging
            answered_ids_query = select(answered_subquery.c.question_id)
            answered_ids_result = await session.execute(answered_ids_query)
            answered_ids = answered_ids_result.scalars().all()
            logger.info(f"User {user_id} has answered these questions in group {group_id}: {answered_ids}")
            
            # Combine answered IDs with explicitly excluded IDs
            all_excluded_ids = list(answered_ids) + excluded_ids
            logger.info(f"Excluding questions with IDs: {all_excluded_ids}")
            
            # Select questions that are active, in the specified group,
            # and not in the list of questions the user has already answered or excluded
            query = (
                select(Question)
                .where(
                    Question.group_id == group_id,
                    Question.is_active == True,
                    ~Question.id.in_(all_excluded_ids)
                )
                .order_by(Question.created_at.asc())  # Show questions by creation date (oldest first)
                .limit(1)  # Just get one question
            )
            
            result = await session.execute(query)
            question = result.scalar_one_or_none()
            
            # Extra safety check to ensure we don't return an already answered question
            if question and question.id in answered_ids:
                logger.error(f"CRITICAL: Question {question.id} was already answered but was selected as next question. Returning None instead.")
                return None
                
            logger.info(f"Found next question for user {user_id} in group {group_id}: {question.id if question else None}")
            return question
            
        except Exception as e:
            logger.error(f"Error in get_next_question_for_user: {e}", exc_info=True)
            # In case of error, return None rather than raising an exception
            return None

    async def get_group_questions(self, session: AsyncSession, group_id: int) -> list[Question]:
        """Get all questions for a specific group."""
        # Make sure we're retrieving ALL active questions for the group
        # with a clear, explicit query that doesn't depend on any user-specific filters
        query = select(Question).where(
            Question.group_id == group_id,
            Question.is_active == True
        ).order_by(Question.created_at.asc())  # Changed to ascending order (oldest first)
        
        result = await session.execute(query)
        questions = result.scalars().all()
        
        # Log the retrieval for debugging
        logger.info(f"Retrieved {len(questions)} active questions for group {group_id}")
        return questions

    async def get_all_active(self, session: AsyncSession) -> list[Question]:
        """Get all active questions across all groups."""
        query = select(Question).where(
            Question.is_active == True
        ).order_by(Question.created_at.desc())
        
        result = await session.execute(query)
        return result.scalars().all()

    async def mark_inactive(self, session: AsyncSession, question_id: int) -> bool:
        """Mark a question as inactive (soft delete)."""
        question = await self.get(session, question_id)
        if not question:
            return False
            
        # Update the question to set is_active = False
        updated = await self.update(session, question_id, {"is_active": False})
        return updated is not None

    async def mark_deleted(self, session: AsyncSession, question_id: int) -> bool:
        """Mark a question as deleted via Telegram (soft delete)."""
        # Simply use the mark_inactive method since they do the same thing
        return await self.mark_inactive(session, question_id)

    async def get_questions_by_ids(self, session: AsyncSession, question_ids: list[int]) -> list[Question]:
        """Get multiple questions by their IDs, sorted by creation date (oldest first)."""
        if not question_ids:
            return []
            
        query = select(Question).where(
            Question.id.in_(question_ids),
            Question.is_active == True
        ).order_by(Question.created_at.asc())  # Consistent with other functions - show oldest first
        
        result = await session.execute(query)
        questions = result.scalars().all()
        
        logger.info(f"Retrieved {len(questions)} questions by IDs (requested {len(question_ids)})")
        return questions


question_repo = QuestionRepository() 