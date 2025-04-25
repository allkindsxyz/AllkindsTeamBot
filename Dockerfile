FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y \
    zlib1g-dev \
    libpq-dev \
    gcc \
    python3-dev \
    curl \
    iputils-ping \
    net-tools \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Make the startup script executable
RUN chmod +x railway_start.sh

# Add a script to properly prepare environment at runtime
RUN echo '#!/bin/bash' > /app/prepare_env.sh && \
    echo 'echo "BOT_TOKEN=$BOT_TOKEN" > /app/.env' >> /app/prepare_env.sh && \
    echo 'echo "COMMUNICATOR_BOT_TOKEN=$COMMUNICATOR_BOT_TOKEN" >> /app/.env' >> /app/prepare_env.sh && \
    echo 'echo "ADMIN_IDS=$ADMIN_IDS" >> /app/.env' >> /app/prepare_env.sh && \
    echo 'echo "DATABASE_URL=$DATABASE_URL" >> /app/.env' >> /app/prepare_env.sh && \
    echo 'echo "DATABASE_URL set to: $DATABASE_URL"' >> /app/prepare_env.sh && \
    echo 'exec "$@"' >> /app/prepare_env.sh && \
    chmod +x /app/prepare_env.sh

# Run the prepare environment script before the main command
ENTRYPOINT ["/app/prepare_env.sh"]
CMD ["./railway_start.sh"]
# Comment out or remove the test CMD line:
# CMD ["sh", "-c", "pwd && ls -la && echo --- Running Python Directly --- && python3 -m src.bot.main"] 