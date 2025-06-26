#!/usr/bin/env python3
"""
Setup verification script for Reddit Telegram Forwarder Bot
Tests Reddit API, configuration, and dependencies.
"""

import asyncio
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    from src.config import Config
    from src.reddit_scraper import RedditScraper
    from src.database import Database
    import praw
    import telegram
    print("✅ All imports successful")
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure you've run: ./bot_manager.sh setup")
    sys.exit(1)


async def test_reddit_api():
    """Test Reddit API connection."""
    print("\n🔍 Testing Reddit API...")
    
    try:
        config = Config()
        scraper = RedditScraper(
            client_id=config.reddit_client_id or "",
            client_secret=config.reddit_client_secret or "",
            user_agent=config.reddit_user_agent,
            temp_dir=config.temp_files_dir,
            config=config
        )
        
        # Test by fetching a few posts from a popular subreddit
        posts = await scraper.scrape_subreddit('pics', 'hot', 'day', 3)
        
        if posts:
            print(f"✅ Reddit API working! Found {len(posts)} posts from r/pics")
            for i, post in enumerate(posts[:2], 1):
                print(f"   {i}. {post['title'][:60]}...")
        else:
            print("⚠️  Reddit API connected but no media posts found")
            
    except Exception as e:
        print(f"❌ Reddit API error: {e}")
        return False
    
    return True


async def test_telegram_bot():
    """Test Telegram bot token."""
    print("\n🤖 Testing Telegram Bot...")
    
    try:
        config = Config()
        bot = telegram.Bot(token=config.telegram_bot_token)
        
        # Get bot info
        bot_info = await bot.get_me()
        print(f"✅ Telegram bot connected!")
        print(f"   Bot name: @{bot_info.username}")
        print(f"   Bot ID: {bot_info.id}")
        
    except Exception as e:
        print(f"❌ Telegram bot error: {e}")
        return False
    
    return True


async def test_database():
    """Test database initialization."""
    print("\n🗄️  Testing Database...")
    
    try:
        config = Config()
        db = Database(config.database_path)
        await db.init_db()
        print("✅ Database initialized successfully")
        
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False
    
    return True


def test_config():
    """Test configuration loading."""
    print("\n⚙️  Testing Configuration...")
    
    try:
        config = Config()
        
        # Check required fields
        required_fields = [
            ('telegram_bot_token', config.telegram_bot_token),
            ('reddit_client_id', config.reddit_client_id),
            ('reddit_client_secret', config.reddit_client_secret),
        ]
        
        missing_fields = []
        for field_name, field_value in required_fields:
            if not field_value or (isinstance(field_value, str) and (
                field_value.startswith('your_') or 
                field_value == 'your_reddit_client_id' or 
                field_value == 'your_reddit_client_secret' or
                field_value == 'your_bot_token_here'
            )):
                missing_fields.append(field_name)
        
        if missing_fields:
            print(f"❌ Missing configuration: {', '.join(missing_fields)}")
            print("   Please update your .env file with actual values")
            return False
        
        print("✅ Configuration loaded successfully")
        print(f"   Admin count: {len(config.admins)}")
        print(f"   Database path: {config.database_path}")
        print(f"   Log level: {config.log_level}")
        
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        return False
    
    return True


async def main():
    """Run all verification tests."""
    print("🚀 Reddit Telegram Forwarder Bot - Setup Verification")
    print("=" * 60)
    
    # Test configuration
    config_ok = test_config()
    
    if not config_ok:
        print("\n❌ Configuration test failed. Please fix and try again.")
        return False
    
    # Test database
    db_ok = await test_database()
    
    # Test Reddit API
    reddit_ok = await test_reddit_api()
    
    # Test Telegram bot
    telegram_ok = await test_telegram_bot()
    
    print("\n" + "=" * 60)
    
    if all([config_ok, db_ok, reddit_ok, telegram_ok]):
        print("🎉 All tests passed! Your bot is ready to run.")
        print("\nNext steps:")
        print("1. Add your Telegram user ID to admins.txt")
        print("   - Message @userinfobot on Telegram to get your user ID")
        print("   - Add the number to admins.txt")
        print("2. Start the bot: ./bot_manager.sh start")
        print("3. Message your bot on Telegram with /start")
        return True
    else:
        print("❌ Some tests failed. Please fix the issues and try again.")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
