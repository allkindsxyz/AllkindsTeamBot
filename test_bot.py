#!/usr/bin/env python3
import asyncio
import logging
import base64
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Create bot and dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Handle the /start command"""
    logger.info(f"Received /start command from user {message.from_user.id}")
    
    args = message.text.split()[1:] if len(message.text.split()) > 1 else None
    
    if args:
        arg = args[0]
        logger.info(f"Command has args: {arg}")
        
        # Try to decode as base64
        try:
            decoded = base64.b64decode(arg).decode('utf-8')
            logger.info(f"Decoded from base64: {decoded}")
            
            if decoded.startswith('g') and decoded[1:].isdigit():
                group_id = int(decoded[1:])
                await message.answer(f"Deep link detected! Would you like to join group {group_id}?")
                return
        except Exception as e:
            logger.info(f"Not base64: {e}")
        
        # Try direct format
        if arg.startswith('g') and arg[1:].isdigit():
            group_id = int(arg[1:])
            await message.answer(f"Direct group link detected! Would you like to join group {group_id}?")
            return
            
        await message.answer(f"Received args: {arg}")
    else:
        await message.answer("Welcome to the bot! Send /start ZzE to test deep link.")

@dp.message()
async def echo(message: types.Message):
    """Echo all messages except commands"""
    logger.info(f"Received message: {message.text}")
    await message.answer(f"You said: {message.text}")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    logger.info("Starting test bot...")
    asyncio.run(main()) 