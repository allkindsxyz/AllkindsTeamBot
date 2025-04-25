# Railway Diagnostics Tools

This document explains the diagnostic tools available for troubleshooting Railway deployment issues for the Allkinds bot.

## Diagnostic Features

The bot now includes the following diagnostic capabilities:

1. **Enhanced Logging**: Advanced logging in Railway environment with detailed error tracking
2. **Webhook Tracking**: Monitoring of all webhook calls to identify issues
3. **Command Tracking**: Tracking of all command executions  
4. **Database Operation Tracking**: Monitoring of critical database operations
5. **Diagnostics Report**: Real-time reporting of bot status and metrics
6. **Log Analysis**: Tools to analyze Railway logs for patterns and issues

## Using the Diagnostic Tools

### 1. In-Bot Diagnostics

The bot has a special command `/railway_diagnostics` that can be used by admins to get real-time diagnostics:

1. Make sure your Telegram user ID is in the `ADMIN_IDS` environment variable (comma-separated list)
2. Send the command `/railway_diagnostics` to the bot
3. The bot will respond with a diagnostics report showing call counts, errors, and timing

### 2. Web Diagnostics Endpoint

A web endpoint is available at `/diagnostics` which returns the same information:

```
https://[your-railway-url]/diagnostics
```

### 3. Log Analysis

After downloading logs from Railway, you can analyze them using the provided tool:

```bash
python analyze_railway_logs.py path/to/railway_logs.txt
```

This will generate a detailed report showing:
- Error patterns and frequencies
- Webhook call statistics
- Slow operations
- Database operation statistics
- Timeline analysis

For a detailed report file:

```bash
python analyze_railway_logs.py path/to/railway_logs.txt --output report.txt
```

## Common Issues and Solutions

### 1. Webhook Configuration

If webhooks aren't working:
- Check that `WEBHOOK_DOMAIN` is correctly set in Railway environment variables
- Verify the bot token is valid
- Check for networking issues between Railway and Telegram

### 2. Database Issues

Database connection problems might be indicated by:
- High number of database operation errors
- Slow database operations (>1s)
- Connection timeouts

Solutions:
- Check DATABASE_URL environment variable
- Ensure database is properly provisioned and accessible
- Look for transaction conflicts or locks

### 3. Telegram API Issues

Problems with the Telegram API might appear as:
- Webhook failures
- Message sending errors
- API rate limiting

Solutions:
- Check bot token
- Verify webhook URL
- Review API usage patterns

## Environment Variable Configuration

Ensure the following environment variables are set in Railway:

- `TELEGRAM_BOT_TOKEN`: Your bot token
- `WEBHOOK_DOMAIN`: The public domain of your Railway deployment
- `ADMIN_IDS`: Comma-separated list of Telegram user IDs of administrators
- `DATABASE_URL`: PostgreSQL connection string
- `RAILWAY_ENVIRONMENT`: Set to "production" for production deployment 