# Railway Deployment Guide for AllkindsTeamBot

This guide provides step-by-step instructions for deploying the AllkindsTeamBot (including both the main bot and communicator bot) on Railway.

## Prerequisites

1. A Railway account
2. Git repository connected to Railway
3. Telegram bot tokens for both bots

## Environment Variables

Set the following environment variables in the Railway project settings:

- `BOT_TOKEN` - Your main Telegram bot token
- `COMMUNICATOR_BOT_TOKEN` - Your communicator bot token
- `COMMUNICATOR_BOT_USERNAME` - Username of your communicator bot (without @)
- `DATABASE_URL` - PostgreSQL connection string (automatically set by Railway if using their PostgreSQL plugin)
- `ADMIN_IDS` - Comma-separated list of admin Telegram IDs
- `OPENAI_API_KEY` - Your OpenAI API key

## Deployment Steps

1. Create a new Railway project
2. Add a PostgreSQL database using Railway's plugin
3. Connect your GitHub repository to the project
4. Set all the required environment variables
5. Deploy the application

## Troubleshooting

If you encounter any issues:

1. Check the application logs in Railway's dashboard
2. Verify all environment variables are set correctly
3. Restart the deployment if necessary
4. Make sure both bots are properly registered and active on Telegram

## Health Checks

Both bots expose a `/health` endpoint that Railway uses to monitor their status. If the health check fails, Railway will automatically restart the service.

## Database Maintenance

Railway's PostgreSQL database may require occasional maintenance:

1. Backups are handled automatically by Railway
2. Consider setting up periodic data exports for additional safety
3. Monitor database usage through Railway's dashboard