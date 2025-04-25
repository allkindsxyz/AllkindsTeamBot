# Railway Deployment Guide for Allkinds Bot

## Deployment Steps

### 1. Set Up Railway Project

1. Create a new project in Railway
2. Link your GitHub repository
3. Enable automatic deployments

### 2. Configure Environment Variables

Set the following required environment variables:

```
TELEGRAM_BOT_TOKEN=your_bot_token
WEBHOOK_DOMAIN=your_railway_public_url
ADMIN_IDS=comma_separated_telegram_ids
OPENAI_API_KEY=your_openai_api_key
RAILWAY_ENVIRONMENT=production
```

### 3. Add Database

1. Add PostgreSQL as a service
2. Railway will automatically add the `DATABASE_URL` variable

### 4. Deploy

1. Push your code to trigger a deployment
2. Railway will run `railway_start.sh` automatically

## Troubleshooting Railway Deployment

### 1. Verify Webhook Setup

If the bot is not responding to messages on Telegram:

1. Check webhook status:
   ```
   curl -X GET https://api.telegram.org/bot<your_token>/getWebhookInfo
   ```

2. Verify the webhook URL matches your Railway deployment:
   ```
   https://<your-railway-domain>/webhook/<your_token>
   ```

3. Check Railway logs for webhook errors:
   ```
   WEBHOOK REQUEST: method=POST, ip=...
   ```

4. Reset webhook if needed:
   ```
   curl -X POST https://api.telegram.org/bot<your_token>/setWebhook?url=https://<your-railway-domain>/webhook/<your_token>
   ```

### 2. Database Issues

If database operations are failing:

1. Check connection in Railway logs for errors like:
   ```
   Error committing session
   Database connection attempt failed
   ```

2. Verify the PostgreSQL service is running
3. Check that migrations completed successfully (look for "Database initialization complete")
4. Try reconnecting the database service in Railway dashboard

### 3. Performance Issues

If the bot is slow or unresponsive:

1. Use the `/railway_diagnostics` command to check metrics
2. Check for slow operations in logs (operations taking >1s)
3. Look for memory issues or CPU spikes in Railway dashboard
4. Consider scaling up your instances if needed

### 4. Command Execution Issues

If specific commands aren't working:

1. Look for command errors in logs:
   ```
   COMMAND ERROR in cmd_questions: ...
   ```

2. Check if the same command works locally
3. Trace the specific function execution using our diagnostic tools

### 5. Using Diagnostics Tools

For real-time diagnostics:

1. Use `/railway_diagnostics` command (admin only)
2. Check the web endpoint: `https://<your-railway-domain>/diagnostics`
3. Download logs and run `python analyze_railway_logs.py railway_logs.txt`

### 6. Common Errors and Solutions

#### Webhook Issues:

```
Failed to set webhook to ...
```

Solution:
- Check if the domain is accessible
- Verify TLS/SSL is working
- Make sure the path is correct

#### Database Connection Errors:

```
Error in get_next_question_for_user: ...
```

Solution:
- Check DATABASE_URL
- Ensure the database is not at connection limit
- Look for transaction locks

#### Aiogram Errors:

```
TelegramConflictError: Conflict: terminated by other getUpdates request
```

Solution:
- Make sure only one instance is running
- Delete webhook and set it again
- Check for other bots using the same token

## Monitoring

1. Set up Railway alerts for:
   - Deployment failures
   - High CPU/memory usage
   - Service downtime

2. Use the diagnostics endpoint to periodically check:
   - Webhook calls
   - Error rates
   - Command execution

3. Set up a monitoring system (e.g., UptimeRobot) to ping your health endpoint:
   ```
   https://<your-railway-domain>/health
   ```

## Rolling Back

If a deployment fails:

1. Use Railway dashboard to roll back to the previous version
2. Check logs to identify the issue
3. Fix the issue locally and test before redeploying

## Resources

- [Railway Documentation](https://docs.railway.app)
- [Aiogram Documentation](https://docs.aiogram.dev/en/latest/)
- [Telegram Bot API](https://core.telegram.org/bots/api)
- [Diagnostics Tools](DIAGNOSTICS.md) 