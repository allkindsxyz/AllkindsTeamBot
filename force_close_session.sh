#!/bin/bash

# Bot tokens
MAIN_BOT_TOKEN="8155919814:AAEMO6RHdkcBErONs70UNjBw4XEvN2vqJuo"
COMMUNICATOR_BOT_TOKEN="7858378825:AAHz8Jz89EHCqxI81GScL77ZjCBHCSVC3cQ"

# Kill any existing bots
echo "Killing any running bots..."
pkill -f "python3 -m src.bot.main" || true
pkill -f "python3 -m src.communicator_bot.main" || true
sleep 2

# Close the session for main bot by using getUpdates with timeout=0
echo "Closing main bot session..."
curl -s "https://api.telegram.org/bot$MAIN_BOT_TOKEN/getUpdates?timeout=0&offset=-1"
echo -e "\n"

# Close the session for communicator bot
echo "Closing communicator bot session..."
curl -s "https://api.telegram.org/bot$COMMUNICATOR_BOT_TOKEN/getUpdates?timeout=0&offset=-1"
echo -e "\n"

# Delete webhook for main bot
echo "Resetting main bot webhook..."
curl -s "https://api.telegram.org/bot$MAIN_BOT_TOKEN/deleteWebhook?drop_pending_updates=true"
echo -e "\n"

# Delete webhook for communicator bot
echo "Resetting communicator bot webhook..."
curl -s "https://api.telegram.org/bot$COMMUNICATOR_BOT_TOKEN/deleteWebhook?drop_pending_updates=true"
echo -e "\n"

echo "Done! Now try running the bots again." 