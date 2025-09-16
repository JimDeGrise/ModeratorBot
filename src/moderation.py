"""Moderation manager that handles auto-mute and escalation logic."""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from telegram import Bot, ChatMember
from telegram.error import TelegramError

from config.settings import config
from src.database import db, UserViolation
from src.rate_limiter import rate_limiter

logger = logging.getLogger(__name__)


class ModerationManager:
    """
    Manages auto-mute functionality and escalation logic.
    
    Handles rate limit violations, applies mutes with escalating durations,
    and notifies administrators of moderation actions.
    """
    
    def __init__(self, bot: Bot):
        self.bot = bot
        self._notification_lock = asyncio.Lock()
    
    async def handle_message(self, user_id: int, chat_id: int, 
                           message_id: int = None) -> Optional[Dict[str, Any]]:
        """
        Handle an incoming message and check for rate limit violations.
        
        Args:
            user_id: The user's ID
            chat_id: The chat's ID  
            message_id: The message ID (optional, for deletion)
            
        Returns:
            Dictionary with moderation action details if action was taken, None otherwise
        """
        # Check if rate limit is exceeded
        rate_limit_exceeded = await rate_limiter.add_message(user_id, chat_id)
        
        if rate_limit_exceeded:
            logger.info(f"Rate limit exceeded for user {user_id} in chat {chat_id}")
            
            # Get user's violation history to determine escalation level
            violation_count = await db.get_user_violation_count(user_id, chat_id)
            
            # Calculate mute duration based on escalation
            mute_duration_minutes = config.get_mute_duration(violation_count + 1)
            
            # Create violation record
            violation = UserViolation(
                user_id=user_id,
                chat_id=chat_id,
                violation_type='rate_limit',
                timestamp=datetime.utcnow(),
                mute_duration_minutes=mute_duration_minutes,
                is_active=True
            )
            
            # Save violation to database
            violation_id = await db.add_violation(violation)
            
            # Apply the mute
            mute_result = await self._apply_mute(user_id, chat_id, mute_duration_minutes)
            
            if mute_result['success']:
                # Reset rate limiter for this user
                await rate_limiter.reset_user_history(user_id, chat_id)
                
                # Notify admins
                await self._notify_admins_of_mute(user_id, chat_id, violation_count + 1, 
                                                mute_duration_minutes, mute_result['username'])
                
                return {
                    'action': 'mute',
                    'user_id': user_id,
                    'chat_id': chat_id,
                    'violation_id': violation_id,
                    'violation_count': violation_count + 1,
                    'mute_duration_minutes': mute_duration_minutes,
                    'username': mute_result['username'],
                    'reason': 'Rate limit exceeded'
                }
            else:
                logger.error(f"Failed to mute user {user_id} in chat {chat_id}: {mute_result['error']}")
        
        return None
    
    async def _apply_mute(self, user_id: int, chat_id: int, 
                         duration_minutes: int) -> Dict[str, Any]:
        """
        Apply a mute to a user in a chat.
        
        Args:
            user_id: The user's ID
            chat_id: The chat's ID
            duration_minutes: Duration of the mute in minutes
            
        Returns:
            Dictionary with result information
        """
        try:
            # Calculate unmute time
            until_date = datetime.utcnow() + timedelta(minutes=duration_minutes)
            
            # Get user information
            username = "Unknown"
            try:
                chat_member = await self.bot.get_chat_member(chat_id, user_id)
                user = chat_member.user
                username = user.username or user.first_name or f"User_{user_id}"
            except TelegramError as e:
                logger.warning(f"Could not get user info for {user_id}: {e}")
            
            # Restrict user (mute)
            await self.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=self._get_muted_permissions(),
                until_date=until_date
            )
            
            logger.info(f"Successfully muted user {user_id} ({username}) in chat {chat_id} for {duration_minutes} minutes")
            
            return {
                'success': True,
                'username': username,
                'until_date': until_date
            }
            
        except TelegramError as e:
            logger.error(f"Failed to mute user {user_id} in chat {chat_id}: {e}")
            return {
                'success': False,
                'error': str(e),
                'username': username
            }
    
    def _get_muted_permissions(self):
        """Get permissions for a muted user."""
        try:
            from telegram import ChatPermissions
            return ChatPermissions(
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
                can_change_info=False,
                can_invite_users=False,
                can_pin_messages=False
            )
        except ImportError:
            # Fallback for older versions
            return None
    
    async def _notify_admins_of_mute(self, user_id: int, chat_id: int, 
                                   violation_count: int, duration_minutes: int,
                                   username: str):
        """
        Notify administrators of a mute action.
        
        Args:
            user_id: The muted user's ID
            chat_id: The chat's ID
            violation_count: Number of violations for this user
            duration_minutes: Duration of the mute
            username: Username of the muted user
        """
        if not config.notify_admins or not config.admin_ids:
            return
        
        async with self._notification_lock:
            try:
                # Format duration for display
                if duration_minutes < 60:
                    duration_str = f"{duration_minutes} minutes"
                elif duration_minutes < 1440:
                    hours = duration_minutes // 60
                    duration_str = f"{hours} hour{'s' if hours != 1 else ''}"
                else:
                    days = duration_minutes // 1440
                    duration_str = f"{days} day{'s' if days != 1 else ''}"
                
                # Create notification message
                message = (
                    f"🔇 **Auto-Mute Applied**\n\n"
                    f"**User:** {username} (`{user_id}`)\n"
                    f"**Chat ID:** `{chat_id}`\n"
                    f"**Violation #:** {violation_count}\n"
                    f"**Duration:** {duration_str}\n"
                    f"**Reason:** Rate limit exceeded ({config.antiflood_max_messages}+ messages in {config.antiflood_window_seconds}s)\n"
                    f"**Time:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
                )
                
                # Send notification to configured chat or admin DMs
                if config.notification_chat:
                    try:
                        await self.bot.send_message(
                            chat_id=config.notification_chat,
                            text=message,
                            parse_mode='Markdown'
                        )
                    except TelegramError as e:
                        logger.warning(f"Failed to send notification to chat {config.notification_chat}: {e}")
                
                # Also send to individual admins if no notification chat is configured
                if not config.notification_chat:
                    for admin_id in config.admin_ids:
                        try:
                            await self.bot.send_message(
                                chat_id=admin_id,
                                text=message,
                                parse_mode='Markdown'
                            )
                        except TelegramError as e:
                            logger.warning(f"Failed to send notification to admin {admin_id}: {e}")
                
            except Exception as e:
                logger.error(f"Error sending admin notification: {e}")
    
    async def manual_mute(self, user_id: int, chat_id: int, 
                         duration_minutes: int, reason: str = "Manual mute") -> Dict[str, Any]:
        """
        Manually mute a user (for admin commands).
        
        Args:
            user_id: The user's ID
            chat_id: The chat's ID
            duration_minutes: Duration of the mute in minutes
            reason: Reason for the mute
            
        Returns:
            Dictionary with result information
        """
        # Create violation record
        violation = UserViolation(
            user_id=user_id,
            chat_id=chat_id,
            violation_type='manual',
            timestamp=datetime.utcnow(),
            mute_duration_minutes=duration_minutes,
            is_active=True
        )
        
        # Save violation to database
        violation_id = await db.add_violation(violation)
        
        # Apply the mute
        mute_result = await self._apply_mute(user_id, chat_id, duration_minutes)
        
        if mute_result['success']:
            return {
                'action': 'manual_mute',
                'user_id': user_id,
                'chat_id': chat_id,
                'violation_id': violation_id,
                'mute_duration_minutes': duration_minutes,
                'username': mute_result['username'],
                'reason': reason
            }
        else:
            return {
                'action': 'manual_mute_failed',
                'error': mute_result['error']
            }
    
    async def unmute_user(self, user_id: int, chat_id: int) -> Dict[str, Any]:
        """
        Unmute a user manually.
        
        Args:
            user_id: The user's ID
            chat_id: The chat's ID
            
        Returns:
            Dictionary with result information
        """
        try:
            # Get unrestricted permissions
            from telegram import ChatPermissions
            permissions = ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )
            
            await self.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=permissions
            )
            
            logger.info(f"Successfully unmuted user {user_id} in chat {chat_id}")
            
            return {
                'success': True,
                'action': 'unmute'
            }
            
        except TelegramError as e:
            logger.error(f"Failed to unmute user {user_id} in chat {chat_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def get_user_status(self, user_id: int, chat_id: int) -> Dict[str, Any]:
        """
        Get moderation status for a user.
        
        Args:
            user_id: The user's ID
            chat_id: The chat's ID
            
        Returns:
            Dictionary with user status information
        """
        stats = await db.get_user_stats(user_id, chat_id)
        message_count = await rate_limiter.get_message_count(user_id, chat_id)
        
        return {
            'user_id': user_id,
            'chat_id': chat_id,
            'total_violations': stats.total_violations,
            'last_violation': stats.last_violation,
            'is_currently_muted': stats.is_currently_muted,
            'current_message_count': message_count,
            'is_exempt': config.is_exempt_from_rate_limit(user_id),
            'is_admin': config.is_admin(user_id),
            'is_whitelisted': config.is_whitelisted(user_id)
        }