# Allkinds Team Bot Architecture

## System Overview

The Allkinds Team Bot is a Telegram-based service designed to connect people based on shared values through customized questions and answers. The system consists of two main components:

1. **Main Bot**: Handles user interaction, questions, answers, and match finding
2. **Communicator Bot**: Manages anonymous communication between matched users

## Core Components

### 1. Bots and Handlers
- `src/bot/`: Main bot functionality and handlers
- `src/communicator_bot/`: Secondary bot for anonymous communication 
- Primary interaction via Telegram Bot API using Aiogram 3

### 2. Database Layer
- `src/db/`: Database models, repositories, and utilities
- SQLAlchemy ORM with async support
- PostgreSQL in production, SQLite for development
- Key models: Users, Groups, Questions, Answers, Matches, ChatSessions

### 3. Core Services
- `src/core/`: Core functionality and shared services
- Configuration, logging, moderation, and utility functions

## Critical Subsystems

### 1. Matching System
- Located in `src/bot/utils/matching.py` and `src/db/repositories/match_repo.py`
- Finds users with similar answers to questions
- Calculates cohesion scores based on answer similarity
- Manages point deduction for match requests

### 2. Chat Session Management
- Anonymous chat sessions between matched users
- Deep link generation for communication initiation
- Message forwarding with anonymized identities

### 3. Group Management
- Team creation and joining via invite codes
- Team member management and permissions
- Question moderation within groups

## Database Schema

### Key Tables
1. `users`: User accounts and profiles
2. `groups`: Teams/communities
3. `group_members`: User membership in groups
4. `questions`: Questions created by users
5. `answers`: User responses to questions
6. `matches`: Records of matched users
7. `anonymous_chat_sessions`: Chat sessions between users
8. `chat_messages`: Messages in anonymous chats

## Design Principles

1. **Asynchronous First**: All I/O operations are asynchronous for scalability
2. **Separation of Concerns**: Clear boundaries between components
3. **Repository Pattern**: Database access through repositories
4. **Dependency Injection**: Session handling and configuration passing
5. **Error Encapsulation**: Proper error handling at appropriate levels

## Critical Workflows

### Match Finding
1. User requests to find a match in a group
2. System validates user has enough points and questions answered
3. System finds potential matches based on answer similarity
4. Points are deducted only if matches are found
5. Match details are presented to the user with option to chat

### Anonymous Chat Initiation
1. User clicks "Start Anonymous Chat" on a match
2. System creates/updates chat session record
3. Deep link to communicator bot is generated
4. User is redirected to communicator bot
5. Identity remains hidden until users choose to reveal

## Configuration and Environment Variables

Critical configuration parameters include:
- `TELEGRAM_BOT_TOKEN`: Main bot token
- `COMMUNICATOR_BOT_TOKEN`: Communicator bot token
- `COMMUNICATOR_BOT_USERNAME`: Communicator bot username
- `DATABASE_URL`: Database connection string
- `OPENAI_API_KEY`: OpenAI API key for moderation
- `WEBHOOK_DOMAIN`: Domain for webhook in production

## Deployment Architecture

### Development
- Local SQLite database
- Polling mode for bot updates
- Direct console logs

### Production (Railway)
- PostgreSQL database
- Webhook mode for bot updates
- Health check endpoint on port 8080
- Railway's CI/CD pipeline
- Log capture and analysis

## Common Issues and Solutions

1. **Database Connection Issues**
   - Connection pool exhaustion
   - Transaction management
   - Session handling across async operations

2. **Match Finding Logic**
   - Point deduction timing
   - Error handling during match search
   - Session state management

3. **Webhook Configuration**
   - Proper domain and path setup
   - SSL requirements
   - Telegram API limitations

## System Evolution and Maintenance

This document should be updated when:
1. New subsystems are added
2. Database schema changes
3. Critical workflows are modified
4. Deployment architecture changes
5. Major bug fixes that affect architecture

_Last updated: [Current Date]_ 