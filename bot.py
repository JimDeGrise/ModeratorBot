"""Main bot implementation for ModeratorBot."""
import asyncio
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, ContextTypes, filters

from config.settings import config
from src.database import db
from src.moderation import ModerationManager
from src.rate_limiter import rate_limiter

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class ModeratorBot:
    """Main ModeratorBot class."""
    
    def __init__(self):
        self.application = None
        self.moderation_manager = None
        self._cleanup_task = None
    
    async def initialize(self):
        """Initialize the bot and all components."""
        logger.info("Initializing ModeratorBot...")
        
        # Initialize database
        await db.initialize()
        logger.info("Database initialized")
        
        # Create application
        self.application = Application.builder().token(config.bot_token).build()
        
        # Initialize moderation manager
        self.moderation_manager = ModerationManager(self.application.bot)
        
        # Add handlers
        self._add_handlers()
        
        # Start cleanup task
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
        
        logger.info("ModeratorBot initialized successfully")
    
    def _add_handlers(self):
        """Add message and command handlers."""
        # Message handler for rate limiting
        self.application.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS,
                self.handle_message
            )
        )
        
        # Admin commands
        self.application.add_handler(
            CommandHandler("mute", self.cmd_mute, filters=filters.ChatType.GROUPS)
        )
        self.application.add_handler(
            CommandHandler("unmute", self.cmd_unmute, filters=filters.ChatType.GROUPS)
        )
        self.application.add_handler(
            CommandHandler("status", self.cmd_status, filters=filters.ChatType.GROUPS)
        )
        self.application.add_handler(
            CommandHandler("stats", self.cmd_stats)
        )
        
        # General commands
        self.application.add_handler(
            CommandHandler("start", self.cmd_start)
        )
        self.application.add_handler(
            CommandHandler("help", self.cmd_help)
        )
        self.application.add_handler(
            CommandHandler("rules", self.cmd_rules, filters=filters.ChatType.GROUPS)
        )
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming messages for rate limiting."""
        if not update.message or not update.message.from_user:
            return
        
        user_id = update.message.from_user.id
        chat_id = update.message.chat.id
        message_id = update.message.message_id
        
        try:
            # Check for rate limit violation and apply auto-mute if needed
            moderation_result = await self.moderation_manager.handle_message(
                user_id, chat_id, message_id
            )
            
            if moderation_result and moderation_result['action'] == 'mute':
                # Delete the message that triggered the mute
                try:
                    await context.bot.delete_message(chat_id, message_id)
                except Exception as e:
                    logger.warning(f"Could not delete message {message_id}: {e}")
                
                # Send notification to the chat
                duration_str = self._format_duration(moderation_result['mute_duration_minutes'])
                username = moderation_result['username']
                violation_count = moderation_result['violation_count']
                
                notification_text = (
                    f"🔇 {username} has been muted for {duration_str} "
                    f"(violation #{violation_count}) for sending too many messages."
                )
                
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=notification_text
                    )
                except Exception as e:
                    logger.warning(f"Could not send mute notification: {e}")
        
        except Exception as e:
            logger.error(f"Error handling message from user {user_id} in chat {chat_id}: {e}")
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        if not update.message or not update.message.from_user:
            return
        
        user_id = update.message.from_user.id
        
        if update.message.chat.type == 'private':
            # Private message
            if config.is_admin(user_id):
                text = (
                    "🤖 **ModeratorBot Admin Panel**\n\n"
                    "Welcome! You have admin access to the bot.\n\n"
                    "**Available Commands:**\n"
                    "/stats - View bot statistics\n"
                    "/help - Show help information\n\n"
                    "**Group Commands:**\n"
                    "/mute - Manually mute a user\n"
                    "/unmute - Unmute a user\n"
                    "/status - Check user status\n"
                    "/rules - Show group rules"
                )
            else:
                text = (
                    "🤖 **ModeratorBot**\n\n"
                    "I'm a moderation bot that helps keep chats organized.\n\n"
                    "Add me to a group to get started!\n\n"
                    "Use /help for more information."
                )
        else:
            # Group message
            text = (
                "🤖 **ModeratorBot is active!**\n\n"
                "I'll help moderate this chat by automatically muting users who send too many messages.\n\n"
                "Use /help for available commands."
            )
        
        await update.message.reply_text(text, parse_mode='Markdown')
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        if not update.message:
            return
        
        user_id = update.message.from_user.id if update.message.from_user else 0
        is_admin = config.is_admin(user_id)
        
        text = (
            "🤖 **ModeratorBot Help**\n\n"
            "**Auto-Moderation Features:**\n"
            f"• Automatically mutes users who send {config.antiflood_max_messages}+ messages in {config.antiflood_window_seconds} seconds\n"
            "• Progressive mute durations for repeat offenders\n"
            "• Admins and whitelisted users are exempt\n\n"
            "**Available Commands:**\n"
            "/rules - Show chat rules\n"
            "/help - Show this help message\n"
        )
        
        if is_admin:
            text += (
                "\n**Admin Commands:**\n"
                "/mute <reply> [duration] - Manually mute a user\n"
                "/unmute <reply> - Unmute a user\n"
                "/status <reply> - Check user moderation status\n"
                "/stats - View bot statistics\n"
            )
        
        await update.message.reply_text(text, parse_mode='Markdown')
    
    async def cmd_rules(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /rules command."""
        if not update.message:
            return
        
        text = f"📜 **Chat Rules**\n\n{config.rules}"
        await update.message.reply_text(text, parse_mode='Markdown')
    
    async def cmd_mute(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /mute command (admin only)."""
        if not update.message or not update.message.from_user:
            return
        
        user_id = update.message.from_user.id
        if not config.is_admin(user_id):
            await update.message.reply_text("❌ You don't have permission to use this command.")
            return
        
        if not update.message.reply_to_message:
            await update.message.reply_text("❌ Please reply to a message to mute the user.")
            return
        
        target_user = update.message.reply_to_message.from_user
        if not target_user:
            await update.message.reply_text("❌ Could not identify the user to mute.")
            return
        
        if config.is_admin(target_user.id):
            await update.message.reply_text("❌ Cannot mute an admin.")
            return
        
        # Parse duration (default: 60 minutes)
        duration_minutes = 60
        if context.args:
            try:
                duration_minutes = int(context.args[0])
                if duration_minutes <= 0:
                    raise ValueError()
            except ValueError:
                await update.message.reply_text("❌ Invalid duration. Please specify minutes as a number.")
                return
        
        # Apply mute
        result = await self.moderation_manager.manual_mute(
            target_user.id, 
            update.message.chat.id,
            duration_minutes,
            "Manual mute by admin"
        )
        
        if result['action'] == 'manual_mute':
            duration_str = self._format_duration(duration_minutes)
            username = result['username']
            await update.message.reply_text(
                f"🔇 {username} has been muted for {duration_str}."
            )
        else:
            await update.message.reply_text(f"❌ Failed to mute user: {result.get('error', 'Unknown error')}")
    
    async def cmd_unmute(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /unmute command (admin only)."""
        if not update.message or not update.message.from_user:
            return
        
        user_id = update.message.from_user.id
        if not config.is_admin(user_id):
            await update.message.reply_text("❌ You don't have permission to use this command.")
            return
        
        if not update.message.reply_to_message:
            await update.message.reply_text("❌ Please reply to a message to unmute the user.")
            return
        
        target_user = update.message.reply_to_message.from_user
        if not target_user:
            await update.message.reply_text("❌ Could not identify the user to unmute.")
            return
        
        # Unmute user
        result = await self.moderation_manager.unmute_user(
            target_user.id,
            update.message.chat.id
        )
        
        if result['success']:
            username = target_user.username or target_user.first_name or f"User_{target_user.id}"
            await update.message.reply_text(f"🔊 {username} has been unmuted.")
        else:
            await update.message.reply_text(f"❌ Failed to unmute user: {result.get('error', 'Unknown error')}")
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command (admin only)."""
        if not update.message or not update.message.from_user:
            return
        
        user_id = update.message.from_user.id
        if not config.is_admin(user_id):
            await update.message.reply_text("❌ You don't have permission to use this command.")
            return
        
        if not update.message.reply_to_message:
            await update.message.reply_text("❌ Please reply to a message to check the user's status.")
            return
        
        target_user = update.message.reply_to_message.from_user
        if not target_user:
            await update.message.reply_text("❌ Could not identify the user.")
            return
        
        # Get user status
        status = await self.moderation_manager.get_user_status(
            target_user.id,
            update.message.chat.id
        )
        
        username = target_user.username or target_user.first_name or f"User_{target_user.id}"
        
        text = (
            f"📊 **Status for {username}**\n\n"
            f"**User ID:** `{target_user.id}`\n"
            f"**Total Violations:** {status['total_violations']}\n"
            f"**Currently Muted:** {'Yes' if status['is_currently_muted'] else 'No'}\n"
            f"**Messages in Window:** {status['current_message_count']}/{config.antiflood_max_messages}\n"
            f"**Is Admin:** {'Yes' if status['is_admin'] else 'No'}\n"
            f"**Is Whitelisted:** {'Yes' if status['is_whitelisted'] else 'No'}\n"
            f"**Rate Limit Exempt:** {'Yes' if status['is_exempt'] else 'No'}\n"
        )
        
        if status['last_violation']:
            text += f"**Last Violation:** {status['last_violation'].strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
        
        await update.message.reply_text(text, parse_mode='Markdown')
    
    async def cmd_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats command (admin only)."""
        if not update.message or not update.message.from_user:
            return
        
        user_id = update.message.from_user.id
        if not config.is_admin(user_id):
            await update.message.reply_text("❌ You don't have permission to use this command.")
            return
        
        # Get statistics
        db_stats = await db.get_database_stats()
        rate_limiter_stats = rate_limiter.get_stats()
        
        text = (
            "📈 **Bot Statistics**\n\n"
            "**Database:**\n"
            f"• Total Violations: {db_stats['total_violations']}\n"
            f"• Active Violations: {db_stats['active_violations']}\n"
            f"• Unique Users: {db_stats['unique_users']}\n"
            f"• Unique Chats: {db_stats['unique_chats']}\n\n"
            "**Rate Limiter:**\n"
            f"• Tracked Users: {rate_limiter_stats['tracked_users']}\n"
            f"• Messages in Window: {rate_limiter_stats['total_messages_in_window']}\n\n"
            "**Configuration:**\n"
            f"• Message Limit: {config.antiflood_max_messages} messages\n"
            f"• Time Window: {config.antiflood_window_seconds} seconds\n"
            f"• Admin Count: {len(config.admin_ids)}\n"
            f"• Whitelisted Users: {len(config.whitelisted_users)}\n"
        )
        
        await update.message.reply_text(text, parse_mode='Markdown')
    
    def _format_duration(self, minutes: int) -> str:
        """Format duration for display."""
        if minutes < 60:
            return f"{minutes} minute{'s' if minutes != 1 else ''}"
        elif minutes < 1440:
            hours = minutes // 60
            return f"{hours} hour{'s' if hours != 1 else ''}"
        else:
            days = minutes // 1440
            return f"{days} day{'s' if days != 1 else ''}"
    
    async def _periodic_cleanup(self):
        """Periodic cleanup task."""
        while True:
            try:
                await asyncio.sleep(3600)  # Run every hour
                
                # Clean up old rate limiter entries
                await rate_limiter.cleanup_old_entries()
                
                # Deactivate old violations
                await db.deactivate_old_violations(hours_back=24)
                
                # Clean up old database entries (every 24 hours)
                if hasattr(self, '_last_db_cleanup'):
                    import time
                    if time.time() - self._last_db_cleanup > 86400:  # 24 hours
                        await db.cleanup_old_data(days_to_keep=90)
                        self._last_db_cleanup = time.time()
                else:
                    import time
                    self._last_db_cleanup = time.time()
                
                logger.info("Periodic cleanup completed")
                
            except Exception as e:
                logger.error(f"Error in periodic cleanup: {e}")
    
    async def run(self):
        """Run the bot."""
        try:
            await self.initialize()
            logger.info("Starting bot...")
            await self.application.run_polling()
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
        except Exception as e:
            logger.error(f"Error running bot: {e}")
        finally:
            if self._cleanup_task:
                self._cleanup_task.cancel()
            logger.info("Bot shutdown complete")


async def main():
    """Main entry point."""
    bot = ModeratorBot()
    await bot.run()


if __name__ == '__main__':
    asyncio.run(main())