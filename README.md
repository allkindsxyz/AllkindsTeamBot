# Allkinds Team Bot

A Telegram bot that connects people based on shared values through customized questions and answers.

## Features

- Create and join teams
- Add yes/no questions 
- Answer questions with Agree/Disagree options (Strong No, No, Yes, Strong Yes)
- Skip questions
- Delete your own questions
- View question feed with all team questions

## Tech Stack

- Python 3.9+
- [Aiogram 3](https://docs.aiogram.dev/en/latest/) for Telegram Bot API
- SQLAlchemy for database ORM
- SQLite for local storage
- OpenAI integration for content moderation

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/allkinds-team-bot.git
cd allkinds-team-bot
```

2. Set up a virtual environment and install dependencies:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Create a `.env` file based on `.env.example`:
```
BOT_TOKEN=your_telegram_bot_token
OPENAI_API_KEY=your_openai_api_key
ADMIN_IDS=your_telegram_id
```

4. Run the bot:
```bash
python run.py
```

## Development

This project uses:
- Poetry for dependency management
- SQLAlchemy for database models and migrations
- Loguru for logging

## License

MIT License 