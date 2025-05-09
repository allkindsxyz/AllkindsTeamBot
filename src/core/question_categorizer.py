from loguru import logger
from src.core.config import get_settings
import random
import os

# Define our 4 fixed categories
MAIN_CATEGORIES = [
    "🧠 Worldview & Beliefs",
    "❤️ Relationships & Family",
    "🌍 Lifestyle & Society",
    "🎯 Career & Ambitions"
]

# Keywords mapping for fallback categorization
CATEGORY_KEYWORDS = {
    "🧠 Worldview & Beliefs": ["belief", "opinion", "think", "religion", "god", "spiritual", "value", "philosophy", "politics", "moral", "ethics"],
    "❤️ Relationships & Family": ["relationship", "family", "love", "partner", "marriage", "date", "child", "parent", "friend", "dating", "romantic"],
    "🌍 Lifestyle & Society": ["hobby", "travel", "food", "social", "lifestyle", "sport", "activity", "entertainment", "culture", "media", "society"],
    "🎯 Career & Ambitions": ["career", "job", "work", "education", "goal", "ambition", "money", "business", "study", "school", "finance", "future"]
}

async def categorize_question(question_text: str) -> str:
    """
    Extract a natural category from the question itself using OpenAI.
    Categorizes into one of four fixed categories.
    
    Args:
        question_text: The text of the question to categorize
        
    Returns:
        A string with one of the four main categories with emoji
    """
    settings = get_settings()
    
    # Check if we have a valid OpenAI API key
    openai_api_key = os.environ.get("OPENAI_API_KEY") or getattr(settings, "openai_api_key", None)
    if not openai_api_key or openai_api_key == "sk-placeholder" or len(openai_api_key) < 20:
        logger.warning("No valid OpenAI API key found. Using keyword-based categorization.")
        return keyword_based_categorization(question_text)
    
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=openai_api_key)
        
        prompt = f"""
        Categorize this question into EXACTLY ONE of these four categories:
        1. 🧠 Worldview & Beliefs (philosophy, values, opinions, religion, politics)
        2. ❤️ Relationships & Family (dating, marriage, children, friends)
        3. 🌍 Lifestyle & Society (hobbies, travel, food, social issues)
        4. 🎯 Career & Ambitions (work, education, goals, money)

        Question: "{question_text}"

        Category (just return the category with emoji, nothing else):
        """
        
        response = await client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that categorizes questions."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=15
        )
        
        category = response.choices[0].message.content.strip()
        
        # Ensure the category is one of our main categories
        for main_cat in MAIN_CATEGORIES:
            if main_cat in category:
                logger.info(f"Categorized as '{main_cat}': {question_text[:30]}...")
                return main_cat
                
        # If OpenAI returns something not in our list, try to map it
        if "world" in category.lower() or "belief" in category.lower() or "opinion" in category.lower():
            return MAIN_CATEGORIES[0]
        elif "relation" in category.lower() or "family" in category.lower() or "love" in category.lower():
            return MAIN_CATEGORIES[1]
        elif "life" in category.lower() or "society" in category.lower() or "hobby" in category.lower():
            return MAIN_CATEGORIES[2]
        elif "career" in category.lower() or "ambit" in category.lower() or "work" in category.lower():
            return MAIN_CATEGORIES[3]
            
        # Fallback to keyword matching
        return keyword_based_categorization(question_text)
        
    except Exception as e:
        logger.error(f"Error extracting category with OpenAI: {e}")
        return keyword_based_categorization(question_text)

def keyword_based_categorization(question_text: str) -> str:
    """Categorize a question based on simple keyword matching without using OpenAI."""
    text_lower = question_text.lower()
    
    # Check each category's keywords
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in text_lower for keyword in keywords):
            logger.info(f"Keyword matched as '{category}': {question_text[:30]}...")
            return category
    
    # If no keywords matched, return a random category
    random_category = random.choice(MAIN_CATEGORIES)
    logger.info(f"No keywords matched, randomly assigned '{random_category}': {question_text[:30]}...")
    return random_category 