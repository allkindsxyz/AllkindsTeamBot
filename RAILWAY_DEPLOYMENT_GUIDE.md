# Railway Deployment Guide for Allkinds Bot

This guide provides detailed instructions for deploying and configuring the Allkinds Bot on Railway.app.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Configuration](#configuration)
3. [Deployment](#deployment)
4. [Troubleshooting](#troubleshooting)
5. [Monitoring](#monitoring)

## Prerequisites

- Railway.app account
- GitHub repository with the Allkinds Bot code
- Telegram bot token(s)
- Database credentials

## Configuration

### Environment Variables

Configure the following environment variables in the Railway dashboard:

```
BOT_TOKEN=your_main_bot_token
COMMUNICATOR_BOT_TOKEN=your_communicator_bot_token
COMMUNICATOR_BOT_USERNAME=AllkindsCommunicatorBot
DATABASE_URL=postgresql://username:password@hostname:port/database
ADMIN_IDS=12345678,87654321
OPENAI_API_KEY=your_openai_api_key
```

### Railway Configuration Files

The repository includes two important configuration files:

1. `railway.toml` - Contains build and deployment settings
2. `railway.yml` - Defines the service structure for multi-service deployments

#### railway.toml

```toml
[build]
builder = "nixpacks"
buildCommand = "pip install -r requirements.txt && python check_dependencies.py || echo 'Dependency check failed but continuing build'"

[deploy]
startCommand = "python -m src.main"
healthcheckPath = "/health"
healthcheckTimeout = 30
restartPolicy = "on-failure"
restartPolicyMaxRetries = 10

[nixpacks]
pkgs = ["python310", "gcc", "build-essential", "curl", "python310Packages.pip"]
```

#### railway.yml (Optional for multi-service setup)

```yml
# Railway configuration
version: 2
services:
  allkinds-bot:
    dockerfilePath: ./Dockerfile
    startCommand: python3 -m src.main
    healthcheckPath: /health
    healthcheckTimeout: 30
    healthcheckInterval: 30
    envVars:
      - key: PYTHON_VERSION
        value: 3.10.0
```

## Deployment

### Method 1: Direct Railway Deployment

1. Connect your GitHub repository to Railway
2. Configure the environment variables in the Railway dashboard
3. Deploy the main branch

### Method 2: GitHub Actions

For automated deployment, set up GitHub Actions with the following workflow:

```yml
name: Deploy to Railway

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v3

      - name: Install Railway CLI
        run: npm i -g @railway/cli

      - name: Deploy to Railway
        run: railway up
        env:
          RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}
```

## Troubleshooting

### Common Issues

#### Webhook Issues

If the bot isn't receiving messages, the webhook might not be correctly set. Fix with:

```bash
python fix_railway_deployment.py
```

This script:
- Ensures proper webhook configuration
- Fixes COMMUNICATOR_BOT_USERNAME environment variable
- Optimizes database connection for Railway
- Configures health checks

#### Database Connection Problems

Railway uses PostgreSQL in a cloud environment. The connection string should be in the format:

```
postgresql://username:password@hostname:port/database
```

If experiencing database issues, check logs for connection errors and ensure:
1. Your DATABASE_URL environment variable is correct
2. The database is accessible from Railway's IP range
3. The script `fix_railway_deployment.py` has been run to optimize connection settings

#### Health Check Failures

Railway uses health checks to determine if your service is running properly. If health checks fail:

1. Verify the `/health` endpoint is accessible
2. Check that `healthcheckPath` is set to `/health` in railway.toml
3. Ensure the health check service in `src/health.py` is running correctly
4. Verify the `healthcheckTimeout` value (30 seconds recommended)

### Debugging Tools

Use these scripts to diagnose and fix issues:

1. `check_env.py` - Verifies environment variables
2. `fix_railway_deployment.py` - Fixes common deployment issues
3. `update_railway_config.py` - Updates Railway configuration files

## Monitoring

### Health Check Endpoint

The application provides a health check endpoint at `/health` which returns status information:

```json
{
  "status": "ok",
  "service": "allkinds",
  "environment": "production",
  "bots": {
    "main_bot": "running",
    "communicator_bot": "running"
  },
  "version": "1.1.0",
  "webhook_host": "https://your-app.railway.app"
}
```

### Logs

Access logs through the Railway dashboard under the "Logs" tab. Important log messages include:

- `Setting webhook URL: https://...` - Confirms webhook setup
- `Webhook set successfully` - Indicates successful webhook configuration
- `Starting Allkinds Team Bot...` - Main bot startup
- `Starting Communicator Bot...` - Communicator bot startup
- `Database setup completed` - Successful database connection

### Performance Monitoring

Railway provides basic metrics for CPU and memory usage. For more detailed monitoring:

1. Use the `/health` endpoint which includes memory and uptime information
2. Set up periodic health checks from external monitoring services
3. Implement custom metrics collection in the application

## Advanced Configuration

### Custom Domains

To use a custom domain for your bot:

1. Configure a custom domain in Railway dashboard
2. Set the `WEBHOOK_HOST` environment variable to your custom domain
3. Run `fix_railway_deployment.py` to update webhook configuration

### Scaling

For handling increased traffic:

1. Increase the instance size in Railway dashboard
2. Optimize database queries and connection pooling
3. Consider adding caching with Redis for frequently accessed data 