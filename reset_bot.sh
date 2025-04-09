#!/bin/bash

# Note: These tokens are now also available in .env file
# If you need to change them, update the .env file instead
# Bot tokens
MAIN_BOT_TOKEN="8155919814:AAEMO6RHdkcBErONs70UNjBw4XEvN2vqJuo"
COMMUNICATOR_BOT_TOKEN="7858378825:AAHz8Jz89EHCqxI81GScL77ZjCBHCSVC3cQ"

# Delete webhook and pending updates for main bot
echo "Resetting main bot webhook..."
curl -s "https://api.telegram.org/bot$MAIN_BOT_TOKEN/deleteWebhook?drop_pending_updates=true"
echo -e "\n"

# Delete webhook and pending updates for communicator bot
echo "Resetting communicator bot webhook..."
curl -s "https://api.telegram.org/bot$COMMUNICATOR_BOT_TOKEN/deleteWebhook?drop_pending_updates=true"
echo -e "\n"

# Get webhook info for main bot
echo "Main bot webhook info:"
curl -s "https://api.telegram.org/bot$MAIN_BOT_TOKEN/getWebhookInfo"
echo -e "\n"

# Get webhook info for communicator bot
echo "Communicator bot webhook info:"
curl -s "https://api.telegram.org/bot$COMMUNICATOR_BOT_TOKEN/getWebhookInfo"
echo -e "\n"

echo "Done! Now try running the bots again." 