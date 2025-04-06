from typing import Dict, List, Tuple

from openai import AsyncOpenAI
from loguru import logger

from src.core.config import get_settings
from src.db.repositories import question_repo

settings = get_settings()

client = AsyncOpenAI(api_key=settings.openai_api_key)

async def check_spelling(text: str) -> Tuple[bool, str]:
    """Check for spelling errors in the text and return corrected version.
    
    Returns:
        A tuple of (has_errors, corrected_text)
    """
    if not settings.openai_api_key:
        logger.warning("OpenAI API key not set. Skipping spelling check.")
        return False, text
    
    try:
        logger.info(f"Checking spelling for: '{text[:30]}...'")
        
        messages = [
            {"role": "system", "content": "You are a helpful assistant that checks for spelling errors in questions."},
            {"role": "user", "content": f"""Check the following question for spelling errors. Return a JSON response with the corrected version and whether there were errors.

Question: "{text}"

Respond in JSON format:
{{
    "has_spelling_errors": true/false,
    "corrected_text": "the corrected question text"
}}

Preserve all capitalization and punctuation in the original. Only correct actual spelling errors.
"""}
        ]
        
        response = await client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.2
        )
        
        result = response.choices[0].message.content
        logger.debug(f"OpenAI spelling check response: {result}")
        
        # Parse JSON response
        import json
        parsed = json.loads(result)
        has_errors = parsed.get("has_spelling_errors", False)
        corrected_text = parsed.get("corrected_text", text)
        
        return has_errors, corrected_text
        
    except Exception as e:
        logger.error(f"Error in OpenAI spelling check: {e}")
        return False, text

async def is_yes_no_question(text: str) -> Tuple[bool, str]:
    """Check if the text is a yes/no question using OpenAI.
    
    Returns:
        A tuple of (is_valid, reason) where reason explains any issues if not valid
    """
    if not settings.openai_api_key:
        logger.warning("OpenAI API key not set. Skipping yes/no check.")
        return True, ""  # Default to True if API key is missing
    
    try:
        logger.info(f"Checking if question is yes/no: '{text[:30]}...'")
        
        messages = [
            {"role": "system", "content": "You are a helpful assistant that evaluates if a question is a yes/no question that can be answered with yes, no, or a degree of yes/no."},
            {"role": "user", "content": f"""Analyze if the following question is a proper yes/no question that can be answered with: strongly disagree, disagree, agree, or strongly agree.

Question: "{text}"

Respond in JSON format:
{{
    "is_yes_no_question": true/false,
    "reason": "Brief explanation if it's not a yes/no question"
}}"""}
        ]
        
        response = await client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.2
        )
        
        result = response.choices[0].message.content
        logger.debug(f"OpenAI yes/no check response: {result}")
        
        # Parse JSON response
        import json
        parsed = json.loads(result)
        is_valid = parsed.get("is_yes_no_question", False)
        reason = parsed.get("reason", "Not a yes/no question")
        
        return is_valid, reason if not is_valid else ""
        
    except Exception as e:
        logger.error(f"Error in OpenAI yes/no check: {e}")
        return True, ""  # Default to True on error

async def check_duplicate_question(text: str, group_id: int, session) -> Tuple[bool, str, int]:
    """Check for duplicate questions within a group using OpenAI.
    
    Returns:
        A tuple of (is_duplicate, similar_question_text, similar_question_id)
    """
    if not settings.openai_api_key:
        logger.warning("OpenAI API key not set. Skipping duplicate check.")
        return False, "", 0
    
    try:
        # First, get all existing questions in the group
        existing_questions = await question_repo.get_group_questions(session, group_id)
        if not existing_questions:
            return False, "", 0
            
        # Create a list of existing question texts
        question_texts = [q.text for q in existing_questions]
        question_ids = [q.id for q in existing_questions]
        
        logger.info(f"Checking for duplicate among {len(existing_questions)} questions in group {group_id}")
        
        messages = [
            {"role": "system", "content": "You are a helpful assistant that detects duplicate or very similar questions."},
            {"role": "user", "content": f"""Determine if the following new question is a duplicate or very similar to any existing questions.
            
New question: "{text}"

Existing questions:
{chr(10).join([f'{i+1}. "{q}"' for i, q in enumerate(question_texts)])}

Respond in JSON format:
{{
    "is_duplicate": true/false,
    "duplicate_index": null or the 1-based index of the duplicate question,
    "reason": "Brief explanation of similarity if found"
}}

Only mark as duplicate if the questions are asking essentially the same thing, not just on the same topic."""}
        ]
        
        response = await client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.2
        )
        
        result = response.choices[0].message.content
        logger.debug(f"OpenAI duplicate check response: {result}")
        
        # Parse JSON response
        import json
        parsed = json.loads(result)
        is_duplicate = parsed.get("is_duplicate", False)
        duplicate_index = parsed.get("duplicate_index")
        reason = parsed.get("reason", "")
        
        if is_duplicate and duplicate_index is not None and 1 <= duplicate_index <= len(question_texts):
            # Convert 1-based index from GPT to 0-based index
            idx = duplicate_index - 1
            return True, question_texts[idx], question_ids[idx]
            
        return False, "", 0
        
    except Exception as e:
        logger.error(f"Error in OpenAI duplicate check: {e}")
        return False, "", 0

async def get_text_embedding(text: str) -> List[float]:
    """Generate text embedding using OpenAI."""
    if not settings.openai_api_key:
        logger.warning("OpenAI API key not set. Returning empty embedding.")
        return []
        
    logger.info("Generating text embedding (placeholder)...")
    # TODO: Implement actual OpenAI embedding generation
    # response = await client.embeddings.create(input=text, model="text-embedding-ada-002")
    # return response.data[0].embedding
    return [0.0] * 1536 # Placeholder dimension 