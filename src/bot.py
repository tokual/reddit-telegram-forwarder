"""Main Reddit Telegram Bot class."""

import asyncio
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters

from .config import Config
from .database import Database
from .reddit_scraper import RedditScraper
from .handlers import CommandHandlers

logger = logging.getLogger(__name__)


class RedditTelegramBot:
    """Main Reddit Telegram Bot class."""
    
    def __init__(self, config: Config):
        """Initialize the bot."""
        self.config = config
        self.db = Database(config.database_path)
        self.reddit_scraper = RedditScraper(
            client_id=config.reddit_client_id or "",
            client_secret=config.reddit_client_secret or "",
            user_agent=config.reddit_user_agent,
            temp_dir=config.temp_files_dir,
            config=config
        )
        
        # Initialize Telegram bot application
        self.application = Application.builder().token(config.telegram_bot_token).build()
        
        # Initialize command handlers
        self.command_handlers = CommandHandlers(self.db, self.config, self)
        
        # Setup handlers
        self._setup_handlers()
        
        # Task tracking
        self._running_tasks = set()
        self._scraper_task = None
        
        logger.info("Reddit Telegram Bot initialized")
    
    def _setup_handlers(self):
        """Setup Telegram bot handlers."""
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.command_handlers.start_command))
        self.application.add_handler(CommandHandler("help", self.command_handlers.help_command))
        self.application.add_handler(CommandHandler("add_rule", self.command_handlers.add_rule_command))
        self.application.add_handler(CommandHandler("list_rules", self.command_handlers.list_rules_command))
        self.application.add_handler(CommandHandler("status", self.command_handlers.status_command))
        
        # Callback query handler for inline keyboards
        self.application.add_handler(CallbackQueryHandler(self.command_handlers.handle_callback_query))
        
        # Text message handler for rule creation
        self.application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self.command_handlers.handle_text_input
        ))
        
        logger.info("Bot handlers configured")
    
    async def start(self):
        """Start the bot."""
        try:
            # Initialize database
            await self.db.init_db()
            logger.info("Database initialized")
            
            # Start the Telegram bot
            await self.application.initialize()
            await self.application.start()
            
            # Setup bot commands menu and info
            await self._setup_bot_commands()
            await self._setup_bot_info()
            
            # Setup bot commands menu
            await self._setup_bot_commands()
            
            # Setup bot description and info
            await self._setup_bot_info()
            
            # Start the scraper task
            self._scraper_task = asyncio.create_task(self._scraper_loop())
            self._running_tasks.add(self._scraper_task)
            
            # Start polling for Telegram updates
            logger.info("Starting bot polling...")
            await self.application.updater.start_polling(
                drop_pending_updates=True,
                allowed_updates=Update.ALL_TYPES
            )
            
            # Keep the bot running
            await asyncio.Event().wait()
            
        except KeyboardInterrupt:
            logger.info("Bot interrupted by user")
        except Exception as e:
            logger.error(f"Error starting bot: {e}", exc_info=True)
        finally:
            await self.stop()
    
    async def stop(self):
        """Stop the bot gracefully."""
        logger.info("Stopping bot...")
        
        # Cancel all running tasks
        for task in self._running_tasks:
            if not task.done():
                task.cancel()
        
        # Wait for tasks to complete
        if self._running_tasks:
            await asyncio.gather(*self._running_tasks, return_exceptions=True)
        
        # Stop Telegram bot
        if self.application.updater and self.application.updater.running:
            await self.application.updater.stop()
        
        if self.application.running:
            await self.application.stop()
        
        await self.application.shutdown()
        
        logger.info("Bot stopped")
    
    async def _scraper_loop(self):
        """Main scraper loop that checks for new posts."""
        logger.info("Starting Reddit scraper loop")
        
        while True:
            try:
                await self._check_all_rules()
                
                # Wait for the next check interval
                await asyncio.sleep(self.config.check_interval_minutes * 60)
                
            except asyncio.CancelledError:
                logger.info("Scraper loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in scraper loop: {e}", exc_info=True)
                # Wait a bit before retrying
                await asyncio.sleep(60)
    
    async def _check_all_rules(self):
        """Check all active rules for new posts."""
        rules = await self.db.get_active_rules()
        
        if not rules:
            logger.debug("No active rules to check")
            return
        
        logger.info(f"Checking {len(rules)} active rules")
        
        for rule in rules:
            try:
                await self._check_rule(rule)
            except Exception as e:
                logger.error(f"Error checking rule {rule['id']}: {e}", exc_info=True)
    
    async def _check_rule(self, rule: Dict[str, Any]):
        """Check a specific rule for new posts."""
        rule_id = rule['id']
        admin_id = rule['admin_id']
        
        # Check if it's time to check this rule
        if not self._should_check_rule(rule):
            return
        
        logger.info(f"Checking rule {rule_id}: r/{rule['subreddit']} ({rule['sort_type']})")
        
        # Scrape Reddit posts
        posts = await self.reddit_scraper.scrape_subreddit(
            subreddit_name=rule['subreddit'],
            sort_type=rule['sort_type'],
            time_filter=rule.get('time_filter', 'day'),
            limit=self.config.max_posts_per_check
        )
        
        # Process new posts
        new_posts_count = 0
        for post_data in posts:
            # Check if post already exists
            if await self.db.post_exists(post_data['id']):
                continue
            
            # Download media first
            file_path = await self.reddit_scraper.download_media(post_data)
            if file_path:
                post_data['file_path'] = file_path
                
                # Add post to database with file path
                if await self.db.add_post(post_data):
                    await self._send_for_approval(post_data, admin_id, rule_id)
                    new_posts_count += 1
            else:
                logger.warning(f"Failed to download media for post {post_data['id']}")
                # Still add to database to avoid reprocessing, but mark as failed
                post_data['file_path'] = None
                await self.db.add_post(post_data)
        
        # Update rule's last check time
        await self.db.update_rule_last_check(rule_id)
        
        if new_posts_count > 0:
            logger.info(f"Found {new_posts_count} new posts for rule {rule_id}")
        else:
            logger.debug(f"No new posts found for rule {rule_id}")
    
    def _should_check_rule(self, rule: Dict[str, Any]) -> bool:
        """Check if a rule should be checked based on its frequency."""
        if not rule['last_check']:
            return True
        
        last_check = datetime.fromisoformat(rule['last_check'])
        frequency_hours = rule['frequency_hours']
        next_check = last_check + timedelta(hours=frequency_hours)
        
        return datetime.now() >= next_check
    
    async def _send_for_approval(self, post_data: Dict[str, Any], admin_id: int, rule_id: int):
        """Send a post to admin for approval."""
        try:
            # Prepare post information
            title = post_data['title']
            subreddit = post_data['subreddit']
            author = post_data['author']
            score = post_data['score']
            permalink = post_data['permalink']
            file_path = post_data['file_path']
            media_type = post_data['media_type']
            
            # Create approval message
            caption = f"""🔍 New Post for Approval

📝 Title: {title}
📍 Subreddit: r/{subreddit}
👤 Author: u/{author}
⬆️ Score: {score}
🔗 View on Reddit: {permalink}

Approve this post?"""
            
            # Create approval buttons
            keyboard = [
                [
                    InlineKeyboardButton("✅ Approve", callback_data=f"approve_{post_data['id']}"),
                    InlineKeyboardButton("❌ Reject", callback_data=f"reject_{post_data['id']}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Send the media with approval buttons
            sent_message = None
            
            if media_type == 'image':
                with open(file_path, 'rb') as photo:
                    sent_message = await self.application.bot.send_photo(
                        chat_id=admin_id,
                        photo=photo,
                        caption=caption,
                        reply_markup=reply_markup
                    )
            elif media_type in ['video', 'gifv']:
                # Regular video files (including converted GIFV)
                with open(file_path, 'rb') as video:
                    sent_message = await self.application.bot.send_video(
                        chat_id=admin_id,
                        video=video,
                        caption=caption,
                        reply_markup=reply_markup
                    )
            elif media_type == 'gif':
                # GIF files - send as animation for better Telegram display
                with open(file_path, 'rb') as animation:
                    sent_message = await self.application.bot.send_animation(
                        chat_id=admin_id,
                        animation=animation,
                        caption=caption,
                        reply_markup=reply_markup
                    )
            
            if sent_message:
                # Add to pending approvals
                await self.db.add_pending_approval(
                    post_id=post_data['id'],
                    admin_id=admin_id,
                    rule_id=rule_id,
                    message_id=sent_message.message_id
                )
                
                logger.info(f"Sent post {post_data['id']} for approval to admin {admin_id}")
            
        except Exception as e:
            logger.error(f"Error sending post for approval: {e}", exc_info=True)
    
    async def cleanup_old_files(self):
        """Clean up old temporary files."""
        try:
            self.reddit_scraper.cleanup_temp_files(max_age_hours=24)
        except Exception as e:
            logger.error(f"Error cleaning up files: {e}")
    
    def get_bot_info(self) -> Dict[str, Any]:
        """Get bot information."""
        return {
            'bot_username': self.application.bot.username if self.application.bot else None,
            'active_rules_count': len(asyncio.create_task(self.db.get_active_rules()).result() or []),
            'admins_count': len(self.config.admins)
        }
    
    async def _setup_bot_commands(self):
        """Setup bot commands menu for Telegram."""
        try:
            # Define the bot commands that will appear in the menu
            commands = [
                ("start", "Welcome message and bot overview"),
                ("help", "Show detailed help and instructions"),
                ("add_rule", "Create a new forwarding rule"),
                ("list_rules", "View and manage your existing rules"),
                ("status", "Show bot status and statistics"),
            ]
            
            # Convert to BotCommand objects
            bot_commands = [BotCommand(command, description) for command, description in commands]
            
            # Set the commands for the bot
            await self.application.bot.set_my_commands(bot_commands)
            logger.info(f"Bot commands menu set successfully with {len(bot_commands)} commands")
            
        except Exception as e:
            logger.error(f"Error setting bot commands: {e}")

    async def _setup_bot_info(self):
        """Setup bot description and other info."""
        try:
            # Set bot description (shows in bot info)
            description = ("🤖 Reddit to Telegram Forwarder Bot\n\n"
                         "I help you forward Reddit posts to Telegram channels after your approval. "
                         "Create forwarding rules, review posts, and manage your content flow.\n\n"
                         "Use /start to begin or /help for detailed instructions.")
            
            await self.application.bot.set_my_description(description)
            
            # Set short description (shows in bot list)
            short_description = "Forward Reddit posts to Telegram channels with approval workflow"
            await self.application.bot.set_my_short_description(short_description)
            
            logger.info("Bot description and info set successfully")
            
        except Exception as e:
            logger.error(f"Error setting bot info: {e}")
