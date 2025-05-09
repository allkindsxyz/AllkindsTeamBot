"""
Question display handlers and utilities for the bot
"""

import logging
import time
from aiogram import types
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.db.models import Question, AnswerType
from src.db.repositories import question_repo, answer_repo
from src.bot.utils.group_utils import can_delete_question

logger = logging.getLogger(__name__)

async def display_single_question(message: types.Message, question, db_user, session: AsyncSession, state: FSMContext = None) -> None:
    """Display a single question to the user."""
    question_text = question.text
    
    # Check if the user can delete this question
    can_delete = await can_delete_question(db_user.id, question, session)
    
    # Create keyboard with answer options
    answer_buttons = [
        types.InlineKeyboardButton(
            text="👎👎",
            callback_data=f"answer:{question.id}:{AnswerType.STRONG_NO.value}"
        ),
        types.InlineKeyboardButton(
            text="👎",
            callback_data=f"answer:{question.id}:{AnswerType.NO.value}"
        ),
        types.InlineKeyboardButton(
            text="⏭️",
            callback_data=f"skip_question:{question.id}"
        ),
        types.InlineKeyboardButton(
            text="👍",
            callback_data=f"answer:{question.id}:{AnswerType.YES.value}"
        ),
        types.InlineKeyboardButton(
            text="👍👍",
            callback_data=f"answer:{question.id}:{AnswerType.STRONG_YES.value}"
        )
    ]
    
    # Create a row for actions
    action_buttons = []
    
    # Delete button (for authors or group creators)
    if can_delete:
        action_buttons.append(
            types.InlineKeyboardButton(
                text="🗑️ Delete",
                callback_data=f"delete_question:{question.id}"
            )
        )
    
    # Create keyboard with answer options in first row and actions in second row
    keyboard_rows = [answer_buttons]
    if action_buttons:
        keyboard_rows.append(action_buttons)
        
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    
    try:
        # Send the question and get the sent message object
        sent_msg = await message.answer(question_text, reply_markup=keyboard)
        logger.info(f"Successfully displayed question {question.id} for user {db_user.id}, message ID: {sent_msg.message_id}")
        
        # Store the message ID in state for future reference
        if state:
            await state.update_data(
                last_question_message_id=sent_msg.message_id,
                current_displayed_question_id=question.id
            )
        
        return sent_msg
    except Exception as e:
        logger.error(f"Error displaying question {question.id} to user {db_user.id}: {e}", exc_info=True)
        return None


async def cleanup_previous_questions(message: types.Message, state: FSMContext) -> None:
    """Clean up previously displayed unanswered question messages from the chat."""
    data = await state.get_data()
    last_question_message_id = data.get("last_question_message_id")
    last_answered_msg_id = data.get("last_answered_msg_id")  # We don't want to delete this
    
    # Only delete if it exists and is not the most recently answered question
    if last_question_message_id and last_question_message_id != last_answered_msg_id:
        try:
            await message.bot.delete_message(
                chat_id=message.chat.id,
                message_id=last_question_message_id
            )
            logger.info(f"Deleted previous unanswered question message {last_question_message_id}")
        except Exception as e:
            logger.warning(f"Failed to delete message {last_question_message_id}: {e}")


async def check_and_display_next_question(message: types.Message, db_user, group_id: int, state: FSMContext, session: AsyncSession) -> bool:
    """
    Check if there are unanswered questions for the user and display the next one.
    Returns True if a question was displayed, False otherwise.
    """
    try:
        # Get user state data
        data = await state.get_data()
        last_displayed_question_id = data.get("last_displayed_question_id")
        recently_shown_questions = data.get("recently_shown_questions", [])
        no_questions_shown = data.get("no_questions_shown", False)
        no_questions_msg_id = data.get("no_questions_msg_id")
        session_id = data.get("session_id", f"{db_user.id}_{group_id}_{int(time.time())}")
        
        # Ensure we have a session ID for tracking purposes
        if "session_id" not in data:
            await state.update_data(session_id=session_id)
            logger.info(f"Created new session ID {session_id} for user {db_user.id}")
        
        # Log the current session state for debugging
        logger.info(f"Session {session_id}: User {db_user.id} in group {group_id}")
        logger.info(f"Session {session_id}: Last displayed question: {last_displayed_question_id}")
        logger.info(f"Session {session_id}: Recently shown questions: {recently_shown_questions}")
        
        # Ensure any pending changes are committed to avoid inconsistent state
        try:
            await session.commit()
            await session.flush()  # Extra flush to ensure all pending changes are processed
        except Exception as e:
            logger.error(f"Error committing session in check_and_display_next_question: {e}")
            
        # Get user's current answers to make sure we have up-to-date data
        # This is critical for PostgreSQL to avoid caching issues
        try:
            current_answers = await answer_repo.get_answers_for_user_in_group(session, db_user.id, group_id)
            answered_ids = [a.question_id for a in current_answers]
        except Exception as e:
            logger.error(f"Error getting user answers in check_and_display_next_question: {e}")
            answered_ids = []
        
        logger.info(f"Session {session_id}: User has answered {len(answered_ids)} questions in group {group_id}")
        logger.info(f"Session {session_id}: Answered question IDs: {answered_ids}")
        
        # Get the total number of available questions for user in this group
        try:
            all_questions_query = select(Question).where(
                Question.group_id == group_id,
                Question.is_active == True
                # is_deleted filter removed temporarily while database is being migrated
            )
            all_questions_result = await session.execute(all_questions_query)
            all_questions = all_questions_result.scalars().all()
            all_question_ids = [q.id for q in all_questions]
            
            total_questions = len(all_questions)
            unanswered_questions = [q for q in all_questions if q.id not in answered_ids]
            total_available = len(unanswered_questions)
            
            logger.info(f"Session {session_id}: Total active questions: {total_questions}")
            logger.info(f"Session {session_id}: Total unanswered questions: {total_available}")
            logger.info(f"Session {session_id}: All active question IDs: {all_question_ids}")
        except Exception as e:
            logger.error(f"Error getting all questions in check_and_display_next_question: {e}")
            total_available = 0  # Assume no questions to be safe
        
        # If we've shown all questions or our list is getting too long, reset it
        if (len(recently_shown_questions) >= total_available) or (len(recently_shown_questions) > 100):
            recently_shown_questions = []
            if last_displayed_question_id is not None:
                recently_shown_questions = [last_displayed_question_id]  # Keep only the most recent one
            logger.info(f"Session {session_id}: Reset recently shown questions list, new list: {recently_shown_questions}")
        
        # Add any already answered questions to our exclusion list to be super safe
        exclusion_list = list(set(recently_shown_questions + answered_ids))
        if last_displayed_question_id is not None and last_displayed_question_id not in exclusion_list:
            exclusion_list.append(last_displayed_question_id)
            
        logger.info(f"Session {session_id}: Using exclusion list: {exclusion_list}")
        
        # If there are no more unanswered questions, show "No more questions" message
        if total_available == 0:
            # Clean up previous messages
            await cleanup_previous_questions(message, state)
            
            # Only show the message if we haven't shown it before
            if not no_questions_shown:
                try:
                    no_questions_msg = await message.answer("❗ No more questions from people at the moment. Create your own question or wait for new ones to appear.")
                    # Store the message ID so we can delete it later if needed
                    await state.update_data(
                        no_questions_msg_id=no_questions_msg.message_id,
                        no_questions_shown=True
                    )
                    logger.info(f"Session {session_id}: No more questions available, displayed 'no questions' message")
                except Exception as e:
                    logger.error(f"Error sending 'no questions' message: {e}")
            else:
                logger.info(f"Session {session_id}: No more questions available, 'no questions' message already shown")
            
            return False
            
        # Get the next unanswered question, excluding recently shown ones
        try:
            next_question = await question_repo.get_next_question_for_user(
                session,
                db_user.id,
                group_id,
                excluded_ids=exclusion_list
            )
        except Exception as e:
            logger.error(f"Error in get_next_question_for_user: {e}", exc_info=True)
            next_question = None
        
        # If we found a question, display it
        if next_question:
            # Double check it's not already answered (extreme caution)
            if next_question.id in answered_ids:
                logger.error(f"Session {session_id}: CRITICAL: Question {next_question.id} was already answered but was selected for display. Skipping it.")
                # Try to recover by updating our state and returning False
                await state.update_data(
                    recently_shown_questions=exclusion_list + [next_question.id]
                )
                return False
                
            # Reset the "no questions shown" flag since we have a question to show
            if no_questions_shown:
                # Try to delete the "no more questions" message if it exists
                if no_questions_msg_id:
                    try:
                        await message.bot.delete_message(
                            chat_id=message.chat.id,
                            message_id=no_questions_msg_id
                        )
                        logger.info(f"Deleted 'no more questions' message {no_questions_msg_id}")
                    except Exception as e:
                        logger.warning(f"Failed to delete 'no more questions' message {no_questions_msg_id}: {e}")
                
                await state.update_data(no_questions_shown=False, no_questions_msg_id=None)
                
            # Clean up previous unanswered question messages to avoid having multiple unanswered questions
            await cleanup_previous_questions(message, state)
                
            try:
                await display_single_question(message, next_question, db_user, session, state)
                logger.info(f"Session {session_id}: Successfully displayed question {next_question.id} for user {db_user.id}")
            except Exception as e:
                logger.error(f"Error displaying question {next_question.id}: {e}", exc_info=True)
                await message.answer("An error occurred while displaying the question. Please try again.")
                return False
            
            # Update recently shown questions
            if next_question.id not in recently_shown_questions:
                recently_shown_questions.append(next_question.id)
            
            # Update state with the question we just displayed and update recently shown
            await state.update_data(
                last_displayed_question_id=next_question.id,
                recently_shown_questions=recently_shown_questions,
                current_question_id=next_question.id  # Explicit tracking of current question
            )
            
            return True
        else:
            # No more questions to answer
            # Clean up previous messages
            await cleanup_previous_questions(message, state)
            
            # Only show the message if we haven't shown it before
            if not no_questions_shown:
                try:
                    no_questions_msg = await message.answer("❗ No more questions from people at the moment. Create your own question or wait for new ones to appear.")
                    # Store the message ID so we can delete it later if needed
                    await state.update_data(
                        no_questions_msg_id=no_questions_msg.message_id,
                        no_questions_shown=True
                    )
                    logger.info(f"Session {session_id}: No more questions available, displayed 'no questions' message")
                except Exception as e:
                    logger.error(f"Error sending 'no questions' message: {e}")
            else:
                logger.info(f"Session {session_id}: No more questions available, 'no questions' message already shown")
            
            return False
    except Exception as e:
        logger.error(f"Unexpected error in check_and_display_next_question for user {db_user.id}: {e}", exc_info=True)
        try:
            await message.answer("An error occurred while loading questions. Please try again.")
        except Exception as send_error:
            logger.error(f"Could not send error message: {send_error}")
        return False

def register_handlers(dp):
    """Register question display handlers."""
    # No specific handlers to register since these are utility functions
    # Used by other handlers
    pass 