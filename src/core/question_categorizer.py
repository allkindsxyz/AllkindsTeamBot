from loguru import logger
from src.core.config import get_settings

# Custom categories based on our actual questions
CUSTOM_CATEGORIES = {
    "🏀 sports & activities": ["nba", "snooker", "hoops", "soccer", "fishing", "surfing", "jogging", "jog", "exercise", "walk", "marathon", "sport"],
    "🌍 travel & location": ["travel", "us", "bali", "mount batur", "location", "country", "city", "place"],
    "🎶 hobbies & interests": ["instrument", "music", "read", "book", "herman hesse", "foodie", "hobby", "interest"],
    "🧘 lifestyle & beliefs": ["meditate", "vegetarian", "smoke", "religious", "religion", "alive", "lifestyle", "belief", "value"],
    "🌐 politics & society": ["trump", "news", "politics", "lgbt", "society", "government", "social issue"],
    "❤️ relationships & personal": ["sex", "date", "cheat", "parents", "parent", "children", "child", "kids", "relationship", "love", "family"],
    "💬 languages & communication": ["speak", "russian", "language", "communication"],
    "📱 technology & online": ["instagram", "social media", "ai", "technology", "online", "internet", "digital"],
    "🎄 culture & holidays": ["christmas", "xmas", "holiday", "culture", "tradition", "celebrate"]
}

async def categorize_question(question_text: str) -> str:
    """
    Extract a natural category from the question itself using OpenAI.
    
    Args:
        question_text: The text of the question to categorize
        
    Returns:
        A string with the dynamically extracted category with emoji
    """
    settings = get_settings()
    
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        
        prompt = f"""
        Extract a single, short category (1-3 words) that best represents what this question is about.
        The category should be concise and descriptive.
        Include an appropriate emoji at the beginning of the category.
        
        Question: "{question_text}"
        
        Category with emoji:
        """
        
        response = await client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that extracts categories from questions."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=15
        )
        
        category = response.choices[0].message.content.strip()
        logger.info(f"Extracted category '{category}' for question: {question_text[:30]}...")
        return category
    except Exception as e:
        logger.error(f"Error extracting category: {e}")
        return "❓ Other" 