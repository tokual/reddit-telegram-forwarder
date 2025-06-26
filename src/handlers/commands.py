"""Telegram bot command handlers."""

import logging
import aiosqlite
from typing import Dict, Any, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import BadRequest

from ..database import Database

logger = logging.getLogger(__name__)


class CommandHandlers:
    """Telegram bot command handlers."""
    
    def __init__(self, database: Database, config, bot_instance=None):
        """Initialize command handlers."""
        self.db = database
        self.config = config
        self.bot = bot_instance
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        user = update.effective_user
        
        if not self.config.is_admin(user.id, user.username):
            await update.message.reply_text(
                "🚫 You are not authorized to use this bot."
            )
            return
        
        welcome_text = """🤖 Reddit to Telegram Forwarder Bot

Welcome! This bot helps you forward Reddit posts to Telegram channels after your approval.

Commands:
/start - Show this message
/add_rule - Add a new forwarding rule
/list_rules - Show your current rules
/help - Show detailed help

To get started, use /add_rule to create your first forwarding rule!"""
        
        await update.message.reply_text(welcome_text)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        user = update.effective_user
        
        if not self.config.is_admin(user.id, user.username):
            await update.message.reply_text("🚫 You are not authorized to use this bot.")
            return
        
        help_text = """📖 Bot Help

How it works:
1. Create a forwarding rule with /add_rule
2. The bot will scrape Reddit posts from your specified subreddit
3. New posts will be sent to you for approval
4. Approved posts are forwarded to your target channel

Commands:
• /start - Welcome message
• /add_rule - Create a new forwarding rule
• /list_rules - View and manage your rules
• /help - This help message

Adding Rules:
When you use /add_rule, you'll be guided through:
- Choosing a subreddit (e.g., "funny", "pics")
- Selecting sort type (hot, new, top, rising)
- Setting time filter (for "top" sort)
- Setting check frequency (in hours)
- Specifying target channel

Requirements:
- The bot must be an admin in your target channel
- Only image and video posts are forwarded
- Duplicate posts are automatically filtered out

Note: Make sure to add this bot as an admin to your target channel before creating rules!"""
        
        await update.message.reply_text(help_text)
    
    async def add_rule_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /add_rule command - start the rule creation process."""
        user = update.effective_user
        
        if not self.config.is_admin(user.id, user.username):
            await update.message.reply_text("🚫 You are not authorized to use this bot.")
            return
        
        # Start the rule creation process
        context.user_data['rule_creation'] = {'step': 'subreddit', 'admin_id': user.id}
        
        await update.message.reply_text(
            "🎯 Create New Forwarding Rule\n\n"
            "Step 1/5: Enter the subreddit name (without r/)\n"
            "Example: funny or pics or aww"
        )
    
    async def list_rules_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /list_rules command."""
        user = update.effective_user
        
        if not self.config.is_admin(user.id, user.username):
            await update.message.reply_text("🚫 You are not authorized to use this bot.")
            return
        
        rules = await self.db.get_admin_rules(user.id)
        
        if not rules:
            await update.message.reply_text(
                "📋 You don't have any forwarding rules yet.\n\n"
                "Use /add_rule to create your first rule!"
            )
            return
        
        text = "📋 Your Forwarding Rules:\n\n"
        
        for i, rule in enumerate(rules, 1):
            status = "✅ Active" if rule['active'] else "⏸️ Inactive"
            text += f"{i}. r/{rule['subreddit']}\n"
            text += f"   • Sort: {rule['sort_type']}"
            if rule['time_filter']:
                text += f" ({rule['time_filter']})"
            text += f"\n   • Frequency: every {rule['frequency_hours']} hours\n"
            text += f"   • Target: {rule['target_channel']}\n"
            text += f"   • Status: {status}\n\n"
        
        # Add management buttons
        keyboard = []
        for rule in rules:
            button_text = f"🗑️ Delete r/{rule['subreddit']}"
            keyboard.append([InlineKeyboardButton(
                button_text, 
                callback_data=f"delete_rule_{rule['id']}"
            )])
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        
        await update.message.reply_text(
            text, 
            reply_markup=reply_markup
        )
    
    async def handle_text_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text input during rule creation."""
        user = update.effective_user
        
        if not self.config.is_admin(user.id, user.username):
            return
        
        # Check if we're in rule creation mode
        if 'rule_creation' not in context.user_data:
            return
        
        rule_data = context.user_data['rule_creation']
        text = update.message.text.strip()
        
        if rule_data['step'] == 'subreddit':
            # Validate subreddit name
            subreddit = text.replace('r/', '').replace('/', '')
            if not subreddit or len(subreddit) < 2:
                await update.message.reply_text("❌ Invalid subreddit name. Please try again.")
                return
            
            rule_data['subreddit'] = subreddit
            rule_data['step'] = 'sort_type'
            
            # Show sort type selection
            keyboard = [
                [InlineKeyboardButton("🔥 Hot", callback_data="sort_hot"),
                 InlineKeyboardButton("🆕 New", callback_data="sort_new")],
                [InlineKeyboardButton("📈 Top", callback_data="sort_top"),
                 InlineKeyboardButton("📊 Rising", callback_data="sort_rising")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"✅ Subreddit: r/{subreddit}\n\n"
                "Step 2/5: Choose sort type:",
                reply_markup=reply_markup
            )
        
        elif rule_data['step'] == 'frequency':
            # Validate frequency
            try:
                frequency = int(text)
                if frequency < 1 or frequency > 168:  # Max 1 week
                    await update.message.reply_text(
                        "❌ Frequency must be between 1 and 168 hours. Please try again."
                    )
                    return
            except ValueError:
                await update.message.reply_text(
                    "❌ Please enter a valid number of hours."
                )
                return
            
            rule_data['frequency_hours'] = frequency
            rule_data['step'] = 'channel'
            
            await update.message.reply_text(
                f"✅ Check frequency: every {frequency} hours\n\n"
                "Step 5/5: Enter the target channel\n"
                "Format: @channelname or channel ID\n"
                "Example: @mychannel"
            )
        
        elif rule_data['step'] == 'channel':
            # Validate channel format
            if not (text.startswith('@') or text.lstrip('-').isdigit()):
                await update.message.reply_text(
                    "❌ Invalid channel format. Use @channelname or channel ID."
                )
                return
            
            rule_data['target_channel'] = text
            
            # Create the rule
            await self._create_rule(update, context, rule_data)
    
    async def _create_rule(self, update: Update, context: ContextTypes.DEFAULT_TYPE, rule_data: Dict[str, Any]):
        """Create the forwarding rule in the database."""
        try:
            rule_id = await self.db.add_forwarder_rule(
                admin_id=rule_data['admin_id'],
                subreddit=rule_data['subreddit'],
                sort_type=rule_data['sort_type'],
                time_filter=rule_data.get('time_filter') or 'day',
                frequency_hours=rule_data['frequency_hours'],
                target_channel=rule_data['target_channel']
            )
            
            if rule_id:
                summary = f"""✅ Rule Created Successfully!

📌 Summary:
• Subreddit: r/{rule_data['subreddit']}
• Sort: {rule_data['sort_type']}"""
                
                if rule_data.get('time_filter'):
                    summary += f" ({rule_data['time_filter']})"
                
                summary += f"""
• Frequency: every {rule_data['frequency_hours']} hours
• Target: {rule_data['target_channel']}

The bot will start checking for new posts and send them to you for approval.

Note: Make sure this bot is an admin in the target channel!"""
                
                await update.message.reply_text(summary)
                logger.info(f"Created rule {rule_id} for admin {rule_data['admin_id']}")
                
                # Execute the rule immediately if bot instance is available
                if self.bot:
                    await update.message.reply_text("🔄 Checking for posts immediately...")
                    await self._execute_rule_immediately(rule_id, update)
            else:
                await update.message.reply_text(
                    "❌ Failed to create rule. Please try again later."
                )
            
        except Exception as e:
            logger.error(f"Error creating rule: {e}")
            await update.message.reply_text(
                "❌ An error occurred while creating the rule. Please try again."
            )
        finally:
            # Clean up user data
            context.user_data.pop('rule_creation', None)
    
    async def _execute_rule_immediately(self, rule_id: int, update: Update):
        """Execute a newly created rule immediately."""
        try:
            # Get the rule details
            rule = await self.db.get_rule_by_id(rule_id)
            if not rule:
                await update.message.reply_text("❌ Could not retrieve rule details")
                return
            
            # Execute the rule using the bot's method
            logger.info(f"Executing rule {rule_id} immediately after creation")
            if hasattr(self.bot, '_check_rule'):
                await self.bot._check_rule(rule)
                await update.message.reply_text("✅ Initial check completed! Any new posts found will be sent for approval.")
            else:
                await update.message.reply_text("⚠️ Immediate execution not available. Rule will be checked during the next scheduled cycle.")
            
        except Exception as e:
            logger.error(f"Error executing rule immediately: {e}")
            await update.message.reply_text(
                "⚠️ Rule created successfully, but initial check failed. "
                "The rule will be checked during the next scheduled cycle."
            )

    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries from inline keyboards."""
        query = update.callback_query
        user = query.from_user
        
        if not self.config.is_admin(user.id, user.username):
            await query.answer("🚫 Not authorized")
            return
        
        await query.answer()
        
        data = query.data
        
        # Handle sort type selection
        if data.startswith('sort_'):
            await self._handle_sort_selection(query, context, data)
        
        # Handle time filter selection
        elif data.startswith('time_'):
            await self._handle_time_filter_selection(query, context, data)
        
        # Handle rule deletion
        elif data.startswith('delete_rule_'):
            await self._handle_rule_deletion(query, context, data)
        
        # Handle post approval/rejection
        elif data.startswith('approve_') or data.startswith('reject_'):
            await self._handle_post_decision(query, context, data)
    
    async def _handle_sort_selection(self, query, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Handle sort type selection during rule creation."""
        if 'rule_creation' not in context.user_data:
            await query.edit_message_text("❌ Rule creation session expired. Please start over with /add_rule")
            return
        
        rule_data = context.user_data['rule_creation']
        sort_type = data.replace('sort_', '')
        rule_data['sort_type'] = sort_type
        
        if sort_type == 'top':
            # Show time filter options for 'top' sort
            rule_data['step'] = 'time_filter'
            keyboard = [
                [InlineKeyboardButton("1 Hour", callback_data="time_hour"),
                 InlineKeyboardButton("1 Day", callback_data="time_day")],
                [InlineKeyboardButton("1 Week", callback_data="time_week"),
                 InlineKeyboardButton("1 Month", callback_data="time_month")],
                [InlineKeyboardButton("1 Year", callback_data="time_year"),
                 InlineKeyboardButton("All Time", callback_data="time_all")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"✅ Sort type: {sort_type}\n\n"
                "Step 3/5: Choose time filter for 'top' posts:",
                reply_markup=reply_markup
            )
        else:
            # Skip time filter for other sort types
            rule_data['step'] = 'frequency'
            await query.edit_message_text(
                f"✅ Sort type: {sort_type}\n\n"
                "Step 4/5: Enter check frequency in hours\n"
                "Example: 4 (checks every 4 hours)\n"
                "Range: 1-168 hours"
            )
    
    async def _handle_time_filter_selection(self, query, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Handle time filter selection during rule creation."""
        if 'rule_creation' not in context.user_data:
            await query.edit_message_text("❌ Rule creation session expired. Please start over with /add_rule")
            return
        
        rule_data = context.user_data['rule_creation']
        time_filter = data.replace('time_', '')
        rule_data['time_filter'] = time_filter
        rule_data['step'] = 'frequency'
        
        await query.edit_message_text(
            f"✅ Sort type: {rule_data['sort_type']} ({time_filter})\n\n"
            "Step 4/5: Enter check frequency in hours\n"
            "Example: 4 (checks every 4 hours)\n"
            "Range: 1-168 hours"
        )
    
    async def _handle_rule_deletion(self, query, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Handle rule deletion."""
        rule_id = int(data.replace('delete_rule_', ''))
        
        success = await self.db.delete_rule(rule_id, query.from_user.id)
        
        if success:
            await query.edit_message_text("✅ Rule deleted successfully!")
        else:
            await query.edit_message_text("❌ Failed to delete rule.")
    
    async def _handle_post_decision(self, query, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Handle post approval or rejection."""
        message_id = query.message.message_id
        
        # Get pending approval data
        approval_data = await self.db.get_pending_approval(message_id)
        if not approval_data:
            await query.edit_message_caption(caption="❌ This approval request has expired.")
            return
        
        if data.startswith('approve_'):
            await self._approve_post(query, context, approval_data)
        elif data.startswith('reject_'):
            await self._reject_post(query, context, approval_data)
    
    async def _approve_post(self, query, context: ContextTypes.DEFAULT_TYPE, approval_data: Dict[str, Any]):
        """Approve a post and forward it to the target channel."""
        try:
            # Get the bot instance to send to channel
            bot = context.bot
            
            # Try to send the post to the target channel
            target_channel = approval_data['target_channel']
            post_id = approval_data['post_id']
            file_path = approval_data.get('file_path')
            title = approval_data['title']
            permalink = approval_data['permalink']
            
            # Check if file path exists
            if not file_path:
                await query.edit_message_caption(caption="❌ Media file not found. The file may have been cleaned up.")
                return
            
            # Check if file actually exists
            import os
            if not os.path.exists(file_path):
                await query.edit_message_caption(caption="❌ Media file no longer exists. The file may have been cleaned up.")
                return
            
            # Send media without caption
            forwarded_message = None
            
            if approval_data['media_type'] == 'image':
                with open(file_path, 'rb') as photo:
                    forwarded_message = await bot.send_photo(
                        chat_id=target_channel,
                        photo=photo
                    )
            elif approval_data['media_type'] == 'video':
                # Check if it's a GIF (use send_animation) or regular video (use send_video)
                if file_path.lower().endswith('.gif'):
                    with open(file_path, 'rb') as animation:
                        forwarded_message = await bot.send_animation(
                            chat_id=target_channel,
                            animation=animation
                        )
                else:
                    with open(file_path, 'rb') as video:
                        forwarded_message = await bot.send_video(
                            chat_id=target_channel,
                            video=video
                        )
            else:
                await query.edit_message_caption(caption=f"❌ Unsupported media type: {approval_data['media_type']}")
                return
            
            # Update database
            forwarded_message_id = forwarded_message.message_id if forwarded_message else None
            success = await self.db.approve_post(
                post_id=post_id,
                admin_id=query.from_user.id,
                rule_id=approval_data['rule_id'],
                target_channel=target_channel,
                forwarded_message_id=forwarded_message_id
            )
            
            if success:
                # Show success message briefly, then delete
                await query.edit_message_caption(
                    caption=f"✅ Post Approved & Forwarded\n\n"
                            f"📝 {title}\n"
                            f"📤 Sent to: {target_channel}"
                )
                
                # Delete the message after 3 seconds
                import asyncio
                await asyncio.sleep(3)
                try:
                    await query.message.delete()
                except Exception as delete_error:
                    logger.warning(f"Could not delete approval message: {delete_error}")
                
                # Clean up temp file
                try:
                    os.remove(file_path)
                    logger.info(f"Cleaned up temp file: {file_path}")
                except Exception as cleanup_error:
                    logger.warning(f"Could not clean up temp file {file_path}: {cleanup_error}")
            else:
                await query.edit_message_caption(caption="❌ Failed to update approval status.")
                
        except BadRequest as e:
            if "chat not found" in str(e).lower() or "not found" in str(e).lower():
                await query.edit_message_caption(
                    caption="❌ Channel not found\n\n"
                            "Make sure the bot is added as an admin to the target channel."
                )
            elif "not enough rights" in str(e).lower():
                await query.edit_message_caption(
                    caption="❌ Permission denied\n\n"
                            "The bot needs admin rights in the target channel to send messages."
                )
            else:
                await query.edit_message_caption(caption=f"❌ Error sending to channel: {e}")
        except Exception as e:
            logger.error(f"Error approving post: {e}")
            await query.edit_message_caption(caption="❌ An error occurred while forwarding the post.")
    
    async def _reject_post(self, query, context: ContextTypes.DEFAULT_TYPE, approval_data: Dict[str, Any]):
        """Reject a post."""
        try:
            success = await self.db.reject_post(
                post_id=approval_data['post_id'],
                admin_id=query.from_user.id,
                rule_id=approval_data['rule_id']
            )
            
            if success:
                # Show rejection message briefly, then delete
                await query.edit_message_caption(
                    caption=f"❌ Post Rejected\n\n"
                            f"📝 {approval_data['title']}"
                )
                
                # Delete the message after 2 seconds
                import asyncio
                await asyncio.sleep(2)
                try:
                    await query.message.delete()
                except Exception as delete_error:
                    logger.warning(f"Could not delete rejection message: {delete_error}")
                
                # Clean up temp file
                file_path = approval_data.get('file_path')
                if file_path:
                    try:
                        import os
                        os.remove(file_path)
                        logger.info(f"Cleaned up temp file after rejection: {file_path}")
                    except Exception as cleanup_error:
                        logger.warning(f"Could not clean up temp file {file_path}: {cleanup_error}")
            else:
                await query.edit_message_caption(caption="❌ Failed to update rejection status.")
                
        except Exception as e:
            logger.error(f"Error rejecting post: {e}")
            await query.edit_message_caption(caption="❌ An error occurred while rejecting the post.")
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command - show bot statistics."""
        user = update.effective_user
        
        if not self.config.is_admin(user.id, user.username):
            await update.message.reply_text("🚫 You are not authorized to use this bot.")
            return
        
        try:
            # Get statistics
            rules = await self.db.get_admin_rules(user.id)
            active_rules = [r for r in rules if r['active']]
            
            # Get total posts processed (approximate)
            async with aiosqlite.connect(self.config.database_path) as db:
                cursor = await db.execute("SELECT COUNT(*) FROM posts")
                total_posts = (await cursor.fetchone())[0]
                
                cursor = await db.execute("SELECT COUNT(*) FROM approved_posts WHERE admin_id = ?", (user.id,))
                approved_posts = (await cursor.fetchone())[0]
                
                cursor = await db.execute("SELECT COUNT(*) FROM posts WHERE status = 'rejected' AND admin_id = ?", (user.id,))
                rejected_posts = (await cursor.fetchone())[0]
            
            status_text = f"""📊 Bot Status

👤 Your Statistics:
• Active Rules: {len(active_rules)}
• Total Rules: {len(rules)}
• Posts Approved: {approved_posts}
• Posts Rejected: {rejected_posts}

🤖 System:
• Total Posts Processed: {total_posts}
• Bot Status: ✅ Running
• Database: ✅ Connected

📋 Your Active Rules:"""

            if active_rules:
                for i, rule in enumerate(active_rules, 1):
                    status_text += f"\n{i}. r/{rule['subreddit']} → {rule['target_channel']}"
            else:
                status_text += "\nNo active rules. Use /add_rule to create one!"
            
            await update.message.reply_text(status_text)
            
        except Exception as e:
            logger.error(f"Error in status command: {e}")
            await update.message.reply_text("❌ Error getting bot status.")
