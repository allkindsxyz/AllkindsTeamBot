# Polling Mode Guide for Allkinds Bot

This guide explains how to fix the issue of bots not responding despite setting `USE_WEBHOOK=false`.

## The Problem

You've set `USE_WEBHOOK=false` but the bots are still not responding. The logs show:

```
2025-04-30 09:37:16.666 | INFO     | __main__:get_webhook_url:63 - Using webhook host from environment: allkindsteambot-production.up.railway.app
```

This indicates that the bot is still trying to use webhooks despite the setting.

## Root Causes

After analysis, we found several issues:

1. **Configuration Inconsistency**: The `USE_WEBHOOK` setting wasn't being properly applied throughout the codebase.
2. **Webhook Persistence**: Even with `USE_WEBHOOK=false`, the webhook wasn't being properly deleted.
3. **Communicator Bot Token**: The communicator bot token appears to be invalid, causing 401 Unauthorized errors.
4. **Railway Configuration**: The Railway deployment wasn't properly configured for polling mode.

## Solution Overview

We've created several scripts to address these issues:

1. `fix_polling_mode.py` - Comprehensive fix that modifies all relevant files
2. `check_tokens.py` - Validates both bot tokens and helps update invalid ones
3. `create_railway_polling_config.py` - Creates optimized Railway configuration for polling

## Step-by-Step Instructions

### 1. Verify and Fix Bot Tokens

The communicator bot token appears to be invalid. Run:

```bash
python3 check_tokens.py --fix
```

This will:
- Validate both bot tokens
- Prompt you to enter a new token if one is invalid
- Update your `.env` file with the correct tokens

### 2. Apply Polling Mode Fixes

Run the comprehensive fix script:

```bash
python3 fix_polling_mode.py
```

This script:
- Updates configuration in `src/core/config.py` to force polling mode
- Modifies `src/main.py` to ensure webhook settings are not applied
- Enhances `src/bot/main.py` with improved webhook deletion and polling
- Updates `src/communicator_bot/main.py` to use polling instead of webhook
- Updates your `.env` file with `USE_WEBHOOK=false`

### 3. Configure Railway for Polling

For Railway deployments, run:

```bash
python3 create_railway_polling_config.py
```

This creates a `railway.toml` file that:
- Sets `USE_WEBHOOK=false` for all environments
- Configures optimized health checks
- Sets appropriate restart policies
- Provides placeholders for tokens

### 4. Deployment

After applying these fixes:

1. **Local Development**:
   - Simply run `python -m src.main`
   - Both bots should start in polling mode

2. **Railway Deployment**:
   - Commit your changes: `git add . && git commit -m "Switch to polling mode"`
   - Push to your repository
   - Update your bot tokens in Railway dashboard if needed
   - Trigger a new deployment

## Understanding the Changes

### Config Updates

The following key files were modified:

- `src/core/config.py`: Webhook configuration now defaults to `False`
- `src/main.py`: Environment variable `USE_WEBHOOK` is forced to `"false"`
- `src/bot/main.py`: Enhanced webhook deletion with retries
- `src/communicator_bot/main.py`: Uses polling instead of webhook server

### Token Management

For token validation and management, use:

```bash
python3 check_tokens.py --fix
```

This will help you diagnose and fix token issues.

## Troubleshooting

If issues persist:

1. **Check Logs**: Look for errors related to token authentication or webhook deletion
2. **Verify Tokens**: Ensure both bot tokens are valid using `check_tokens.py`
3. **Manual Reset**: Try manually resetting the webhook:
   ```
   curl -X POST https://api.telegram.org/bot<YOUR_TOKEN>/deleteWebhook
   ```
4. **Railway Dashboard**: Ensure all environment variables are correctly set
5. **Bot Status**: Check if your bots are active in BotFather

## Additional Resources

- [Telegram Bot API - getWebhookInfo](https://core.telegram.org/bots/api#getwebhookinfo)
- [Telegram Bot API - deleteWebhook](https://core.telegram.org/bots/api#deletewebhook)
- [Railway Documentation](https://docs.railway.app/) 