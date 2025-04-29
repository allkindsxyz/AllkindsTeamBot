#!/usr/bin/env python
"""Script to delete all groups from the database."""

import asyncio
import sys
import os

# Add the parent directory to the path so we can import the src module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import delete, select
from loguru import logger

from src.db.base import async_session_factory
from src.db.models import Group, GroupMember, Question, Answer


async def delete_all_groups():
    """Delete all groups and related data from the database."""
    async with async_session_factory() as session:
        try:
            # First delete related records
            # Delete answers related to questions in groups
            delete_answers = delete(Answer).where(
                Answer.question_id.in_(
                    select(Question.id).where(Question.group_id.is_not(None))
                )
            )
            answers_result = await session.execute(delete_answers)
            
            # Delete questions related to groups
            delete_questions = delete(Question).where(Question.group_id.is_not(None))
            questions_result = await session.execute(delete_questions)
            
            # Delete group members
            delete_members = delete(GroupMember)
            members_result = await session.execute(delete_members)
            
            # Now delete groups
            delete_groups = delete(Group)
            groups_result = await session.execute(delete_groups)
            
            await session.commit()
            
            logger.info(f"Deleted {groups_result.rowcount} groups")
            logger.info(f"Deleted {members_result.rowcount} group members")
            logger.info(f"Deleted {questions_result.rowcount} questions")
            logger.info(f"Deleted {answers_result.rowcount} answers")
            
            return groups_result.rowcount
            
        except Exception as e:
            await session.rollback()
            logger.error(f"Error deleting groups: {e}")
            raise


if __name__ == "__main__":
    logger.info("Deleting all groups from the database...")
    groups_deleted = asyncio.run(delete_all_groups())
    logger.info(f"Successfully deleted {groups_deleted} groups and related data.") 