# Security Guidelines for AllkindsTeamBot

This document outlines the security practices to follow when developing for the AllkindsTeamBot project.

## Credentials Management

### DO NOT:
- Hardcode credentials, API keys, tokens, or passwords directly in the code
- Store credentials in configuration files that are committed to the repository
- Log sensitive information to console or log files
- Share credentials through insecure channels

### DO:
- Use environment variables for all sensitive credentials
- Use the provided `src/core/credentials.py` module for accessing credentials
- Mask sensitive data in logs using the `mask_sensitive_data()` function
- Use `.env` files for local development (make sure they are in `.gitignore`)

## Example: Using the Credentials Module

```python
from src.core.credentials import get_api_credentials, get_database_url

# Get database connection string
db_url = get_database_url()

# Get API credentials for a service
openai_creds = get_api_credentials("openai")
api_key = openai_creds["api_key"]
```

## Environment Variables Setup

The following environment variables should be configured in your deployment environment:

- `DATABASE_URL`: Database connection string
- `BOT_TOKEN`: Telegram bot token
- `OPENAI_API_KEY`: OpenAI API key
- `PINECONE_API_KEY`: Pinecone API key
- `PINECONE_ENVIRONMENT`: Pinecone environment
- `ADMIN_IDS`: Comma-separated list of admin user IDs

## Local Development with .env

For local development, create a `.env` file in the project root with the required variables:

```
DATABASE_URL=postgresql://user:password@localhost:5432/dbname
BOT_TOKEN=123456789:ABCDefGhIJKlmnOPQRsTUVwxyZ
OPENAI_API_KEY=sk-...
PINECONE_API_KEY=...
PINECONE_ENVIRONMENT=...
ADMIN_IDS=123456789,987654321
```

**Important**: Make sure `.env` is included in `.gitignore` to prevent accidental commits.

## Reporting Security Issues

If you discover a security vulnerability in this project, please report it to [admin@allkinds.xyz](mailto:admin@allkinds.xyz).

## Security Checklist for Pull Requests

Before submitting a PR, verify:

- No credentials are hardcoded in the code
- Sensitive data is properly masked in logs
- No `.env` files or other credential files are included in the commits
- The credentials module is used for accessing sensitive information 