
# Railway Deployment Troubleshooting Guide

## Common Issues and Solutions

### 1. Database Connection Issues

If you see database connection errors in the logs:

- Check that DATABASE_URL is set correctly in Railway's environment variables
- Ensure PostgreSQL addon is properly attached to your project
- Try the following in Railway's shell:
  ```
  python -c "import asyncio, asyncpg; asyncio.run(asyncpg.connect(os.environ['DATABASE_URL']))"
  ```

### 2. Bot Token Verification Failed

If you see "Bot verification failed" in the logs:

- Verify BOT_TOKEN and COMMUNICATOR_BOT_TOKEN are set correctly
- Check that the bots are active in BotFather
- Try accessing the Telegram API directly in Railway's shell:
  ```
  curl -X POST https://api.telegram.org/bot$BOT_TOKEN/getMe
  ```

### 3. Webhook Conflict

If you see "Conflict: terminated by other getUpdates request" or webhook errors:

- The bot might be running in multiple instances or have a webhook set
- Run this in Railway's shell to clear webhooks:
  ```
  curl -X POST https://api.telegram.org/bot$BOT_TOKEN/deleteWebhook?drop_pending_updates=true
  ```

### 4. Port Binding Issues

If you see "Address already in use" errors:

- Change the PORT environment variable in Railway to a different value
- Ensure you're not binding to the same port multiple times

### 5. Memory or CPU Usage Issues

If the app keeps crashing or restarting:

- Check Railway usage metrics
- Consider optimizing your code or adjusting pool sizes in database configuration
- Add memory limits to Railway configuration

## Accessing Logs

To view detailed logs in Railway:

1. Go to your project in the Railway dashboard
2. Click on the "Deployments" tab
3. Select the current deployment
4. Click on "Logs" to see real-time logs

## Support

If you continue to experience issues, please:

1. Export the logs from Railway
2. Create an issue on the project repository with the logs attached
3. Include details of your deployment environment
