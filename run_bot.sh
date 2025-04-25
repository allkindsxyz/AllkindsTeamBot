#!/bin/bash

# Allkinds Team Bot Runner
# This script provides a simple interface to start and stop the bot

# Colors for better readability
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}===== ALLKINDS TEAM BOT RUNNER =====${NC}"
echo ""

# Function to show usage
show_usage() {
  echo -e "Usage: ./run_bot.sh [command]"
  echo ""
  echo -e "Commands:"
  echo -e "  ${GREEN}start${NC}    Start the bot"
  echo -e "  ${RED}stop${NC}     Stop the bot"
  echo -e "  ${BLUE}status${NC}   Check if the bot is running"
  echo ""
}

# No arguments, show usage
if [ $# -eq 0 ]; then
  show_usage
  exit 1
fi

# Process commands
case "$1" in
  start)
    echo -e "${GREEN}Starting the bot...${NC}"
    python3 start_bot.py
    ;;
  stop)
    echo -e "${RED}Stopping the bot...${NC}"
    python3 stop_bot.py
    ;;
  status)
    echo -e "${BLUE}Checking bot status...${NC}"
    if [ -f "bot.pid" ]; then
      PID=$(cat bot.pid)
      if ps -p $PID > /dev/null; then
        echo -e "${GREEN}Bot is running with PID: $PID${NC}"
      else
        echo -e "${RED}Bot PID file exists but process is not running.${NC}"
      fi
    else
      echo -e "${RED}Bot is not running.${NC}"
    fi
    ;;
  *)
    echo -e "${RED}Unknown command: $1${NC}"
    show_usage
    exit 1
    ;;
esac

exit 0 