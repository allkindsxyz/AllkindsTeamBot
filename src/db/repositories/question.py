from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from src.db.models import Question
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
        self, session: AsyncSession, user_id: int, group_id: int
    ) -> Question | None:
        """Gets the next unanswered question for a user in a group."""
        # TODO: Implement logic to find next question
        # (e.g., hasn't answered, hasn't skipped recently, ordered by popularity/date)
        stmt = select(Question).where(Question.group_id == group_id).limit(1) # Very basic placeholder
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

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


question_repo = QuestionRepository() 