#!/usr/bin/env python3
"""
Reddit to Telegram Forwarder Bot

A Telegram bot that scrapes Reddit posts and forwards them to channels after admin approval.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.bot import RedditTelegramBot
from src.config import Config
from src.utils.logging_setup import setup_logging


async def main():
    """Main entry point for the bot."""
    try:
        # Setup logging
        setup_logging()
        logger = logging.getLogger(__name__)
        
        # Load configuration
        config = Config()
        
        # Create bot instance
        bot = RedditTelegramBot(config)
        
        # Start the bot
        logger.info("Starting Reddit Telegram Forwarder Bot...")
        await bot.start()
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
