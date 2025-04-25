# Troubleshooting Guide

This document provides solutions for common issues encountered while working with the Allkinds Team Bot.

## Deployment Issues

### Database Connection Errors

#### SQLAlchemy/asyncpg Connection Error with Railway PostgreSQL

**Problem:**
When deploying to Railway, the application crashes with a SQLAlchemy pool connection error:

```
File "/usr/local/lib/python3.10/site-packages/sqlalchemy/pool/base.py", line 713, in checkout
  rec = pool._do_get()
File "/usr/local/lib/python3.10/site-packages/sqlalchemy/pool/impl.py", line 179, in _do_get
  with util.safe_reraise():
File "/usr/local/lib/python3.10/site-packages/sqlalchemy/util/langhelpers.py", line 146, in __exit__
  raise exc_value.with_traceback(exc_tb)
```

**Solution:**
The issue is caused by overriding the host in the database connection configuration. Railway provides its own internal hostnames for the database that should not be overridden.

To fix:
1. Remove any `"host": "127.0.0.1"` overrides in `connect_args` in `src/db/base.py` and `src/db/init_db.py`
2. Remove any code that attempts to replace Railway hostnames with localhost in `process_database_url`
3. Remove any `/etc/hosts` entries that map Railway internal hostnames to localhost in `Dockerfile`

**Diagnostic Steps:**
1. Run the `db_connection_test.py` script to identify connection issues
2. Check the Railway logs for detailed error messages
3. Verify that the DATABASE_URL is correctly set in Railway variables

## Webhook Issues

### Bot Not Responding to Commands

**Problem:**
The bot is deployed successfully but doesn't respond to commands like `/start`.

**Solution:**
The issue is typically with the webhook setup. Use the `check_webhook.py` script to diagnose and fix webhook issues:

```bash
python check_webhook.py        # Check the current webhook status
python check_webhook.py --reset # Delete and set a new webhook
```

**Diagnostic Steps:**
1. Run `check_webhook.py` to see the current webhook configuration
2. Verify that the webhook URL matches your Railway public URL
3. Check if there are pending updates that should be cleared
4. Use `test_telegram.py` to verify the bot can send messages

## Health Check Issues

If the health check endpoint returns errors but the bot seems to be working:

1. Use `curl` to manually test the health endpoint:
   ```
   curl https://your-railway-url.up.railway.app/health
   ```

2. Check if the health check port is correctly configured (default: 8080)

3. Run the following command to check the bot's running processes:
   ```
   railway run ps
   ```

## Logs Analysis

To analyze Railway logs for issues:

```bash
python check_logs.py         # Analyze the last 200 log lines
python check_logs.py --lines 500  # Analyze the last 500 log lines
```

This will extract relevant information about webhooks, errors, and database connections from the logs. 