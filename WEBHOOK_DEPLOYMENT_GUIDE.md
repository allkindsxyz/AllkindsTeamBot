# Webhook Deployment Guide for Allkinds Bot

This guide explains how to properly configure your bots to use webhook mode on Railway.

## The Problem

The Telegram bots aren't responding to commands even though they're running on Railway. The logs show they may be configured for webhooks but not properly handling the webhook setup.

## Webhook Mode Overview

Webhook mode allows Telegram to send updates to your bot by calling a URL when new messages arrive, rather than your bot asking Telegram for updates (polling). This is more efficient and recommended for production deployments.

For webhook mode to work properly, you need:

1. A public HTTPS URL (provided by Railway)
2. Proper webhook registration with Telegram
3. Different webhook paths for each bot to avoid conflicts
4. Correct environment configurations

## Solution Process

We've created a comprehensive script to fix all webhook-related issues:

```bash
python3 fix_webhook_mode.py
```

This script:

1. Updates all configuration files for proper webhook handling
2. Sets up distinct webhook paths for each bot
3. Registers webhooks with Telegram directly
4. Creates an optimized Railway deployment config

## Step-by-Step Instructions

### 1. Run the Fix Script Locally

```bash
python3 fix_webhook_mode.py
```

This will:
- Update your local codebase with proper webhook configurations
- Set webhooks directly with Telegram API
- Create a Railway configuration file

### 2. Commit and Push Changes

```bash
git add .
git commit -m "Fix webhook configuration for both bots"
git push origin main
```

### 3. Verify Railway Deployment

1. Go to your Railway dashboard
2. Check the deployment logs
3. Verify both bots are running
4. Try sending commands to both bots

## What Changed

### 1. Webhooks Setup

- **Main Bot**: Uses `/webhook` path
- **Communicator Bot**: Uses `/comm_webhook` path (to avoid conflicts)

### 2. File Changes

- **src/core/config.py**: Ensures webhook mode is enabled on Railway
- **src/main.py**: Properly sets environment variables for both bots
- **src/bot/main.py**: Enhanced webhook handling and error recovery
- **src/communicator_bot/main.py**: Uses a distinct webhook path and improved error handling

### 3. Railway Configuration

A new `railway.toml` file ensures:
- Proper webhook mode activation
- Health check configuration
- Restart policies
- Environment variable definitions

## Troubleshooting

If issues persist:

### 1. Check Bot Tokens

Verify both bot tokens are valid:
```bash
python3 check_tokens.py
```

### 2. Manually Set Webhooks

For the main bot:
```
curl -F "url=https://YOUR_RAILWAY_URL/webhook" https://api.telegram.org/botYOUR_BOT_TOKEN/setWebhook
```

For the communicator bot:
```
curl -F "url=https://YOUR_RAILWAY_URL/comm_webhook" https://api.telegram.org/botYOUR_COMMUNICATOR_BOT_TOKEN/setWebhook
```

### 3. Check Webhook Status

For the main bot:
```
curl https://api.telegram.org/botYOUR_BOT_TOKEN/getWebhookInfo
```

For the communicator bot:
```
curl https://api.telegram.org/botYOUR_COMMUNICATOR_BOT_TOKEN/getWebhookInfo
```

### 4. Check Railway Logs

Look for errors related to:
- Webhook setup
- HTTP handling
- Telegram API responses

### 5. Restart Deployment

Sometimes a clean restart can help:
1. Go to Railway dashboard
2. Find your service
3. Click "Restart" button

## Best Practices

1. **Always Use HTTPS**: Telegram only accepts webhook URLs with HTTPS.
2. **Unique Webhook Paths**: Each bot should have its own webhook path.
3. **Error Handling**: Properly handle and log webhook errors.
4. **Health Checks**: Use Railway's health checks to monitor your bots.
5. **Validate Responses**: Check that webhook responses are correctly sent back to Telegram.

## Additional Resources

- [Telegram Bot API - Webhooks](https://core.telegram.org/bots/api#setwebhook)
- [Railway Documentation](https://docs.railway.app/)
- [HTTPS Requirements for Telegram Bots](https://core.telegram.org/bots/webhooks) 