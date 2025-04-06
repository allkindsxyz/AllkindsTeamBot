from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.db.models import Answer, Question
from src.db.repositories.base import BaseRepository


class AnswerRepository(BaseRepository[Answer]):
    def __init__(self):
        super().__init__(Answer)

    async def save_answer(
        self, session: AsyncSession, user_id: int, question_id: int, answer_type: str, value: int
    ) -> Answer:
        """Saves or updates a user's answer to a question."""
        # Check if answer already exists
        existing_answer = await self.get_by_attribute(
            session, 
            expression=(Answer.user_id == user_id) & (Answer.question_id == question_id)
        ) # Need to adjust get_by_attribute for complex conditions or create a specific method

        data = {
            "user_id": user_id,
            "question_id": question_id,
            "answer_type": answer_type,
            "value": value
        }

        if existing_answer:
            # Update existing answer
            updated_answer = await self.update(session, existing_answer.id, data)
            if not updated_answer: # Handle potential update failure
                 raise Exception("Failed to update existing answer")
            return updated_answer
        else:
            # Create new answer
            return await self.create(session, data)

    async def get_user_answers_for_group(self, session: AsyncSession, user_id: int, group_id: int) -> list[Answer]:
        """Get all answers from a user for questions in a specific group."""
        query = select(Answer).join(
            Question, Answer.question_id == Question.id
        ).where(
            Answer.user_id == user_id,
            Question.group_id == group_id
        ).order_by(Answer.created_at.desc())
        
        result = await session.execute(query)
        return result.scalars().all()

    async def get_answers_for_user_in_group(self, session: AsyncSession, user_id: int, group_id: int) -> list[Answer]:
        """Alias for get_user_answers_for_group for backward compatibility."""
        return await self.get_user_answers_for_group(session, user_id, group_id)

answer_repo = AnswerRepository() 