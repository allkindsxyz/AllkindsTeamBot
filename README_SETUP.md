# Allkinds Bot Setup Instructions

This document contains instructions for setting up and running both the main Allkinds Bot and the Communicator Bot.

## Prerequisites

- Python 3.8 or higher
- Poetry (dependency management)
- SQLite database

## Environment Setup

1. Ensure you have the necessary environment variables set (or create a `.env` file):
   - `TELEGRAM_BOT_TOKEN` - Token for the main bot
   - `COMMUNICATOR_BOT_TOKEN` - Token for the communicator bot

## Database Migrations

The system requires several database tables to function correctly. You should run migrations before starting the bots.

### Main Bot Migrations

For the main bot, run:

```bash
python3 2024_08_create_anonymous_chat_sessions.py
python3 2024_08_create_chat_messages_table.py
```

These scripts create the necessary tables for chat sessions and messages.

### Communicator Bot Migrations

The communicator bot migrations are now automatically run when you start the communicator bot, but you can also run them manually:

```bash
python3 run_communicator_migrations.py
```

## Starting the Bots

### Main Bot

To start the main Allkinds bot:

```bash
python3 start_bot.py
```

### Communicator Bot

To start the Communicator bot:

```bash
python3 start_communicator_bot.py
```

This script:
1. Runs necessary database migrations
2. Resets the Telegram webhook
3. Kills any existing instances of the bot
4. Starts a new instance of the communicator bot

## Logs

Logs are stored in the following files:
- Main bot: `logs/bot_*.log` (where * is a timestamp)
- Communicator bot: `communicator_bot_new.log`

## Troubleshooting

If you encounter issues:

1. Check the log files for errors
2. Ensure all migrations have run successfully
3. Verify that both bots have the correct tokens
4. Make sure only one instance of each bot is running

## Database Structure

The key tables used by the communicator bot are:

- `anonymous_chat_sessions` - Stores chat sessions between users
- `chat_messages` - Stores messages sent in anonymous chats
- `users` - User information
- `matches` - Matches between users (used to create chat sessions)

## Commands

- `/start` - Initialize both bots
- `/menu` - Open the main menu in the communicator bot
- `/help` - Display help information 