import asyncio
import aiohttp
import ssl
import os
from src.core.config import get_settings

async def delete_webhook(token):
    url = f"https://api.telegram.org/bot{token}/deleteWebhook?drop_pending_updates=true"
    # Create a context that doesn't verify certificates
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.get(url) as response:
            result = await response.json()
            return result

async def main():
    # Get bot tokens from settings
    settings = get_settings()
    main_bot_token = settings.BOT_TOKEN
    
    # Get communicator bot token from settings or environment
    communicator_bot_token = settings.COMMUNICATOR_BOT_TOKEN
    if not communicator_bot_token:
        communicator_bot_token = os.getenv("COMMUNICATOR_BOT_TOKEN")
        if not communicator_bot_token:
            print("Error: COMMUNICATOR_BOT_TOKEN not found in settings or environment")
            return
    
    # Reset the main bot's webhook
    print(f"Resetting main bot webhook...")
    result = await delete_webhook(main_bot_token)
    print(f"Result: {result}")
    
    # Reset the communicator bot's webhook
    print(f"Resetting communicator bot webhook...")
    result = await delete_webhook(communicator_bot_token)
    print(f"Result: {result}")
    
    print("Done! Now try running the bots again.")

if __name__ == "__main__":
    asyncio.run(main()) 