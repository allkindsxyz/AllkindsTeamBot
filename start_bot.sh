#!/bin/bash

# First kill all existing bot instances
echo "=== Running kill_all_bots.sh to ensure clean environment ==="
./kill_all_bots.sh

# Start the bot in the foreground
echo "=== Starting new bot instance ==="
poetry run python -m src.main 