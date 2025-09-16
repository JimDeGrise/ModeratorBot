"""
Utility functions for ModeratorBot.
Contains common functions for command detection, user management, and filtering.
"""

import logging
import re
from datetime import datetime, timedelta
from typing import List, Optional, Set
from urllib.parse import urlparse

from telegram import Chat, ChatMember, Message, Update, User
from telegram.constants import ChatMemberStatus
from telegram.error import BadRequest, Forbidden, TelegramError
from telegram.ext import ContextTypes

from config import get_config

# Set up logging
logger = logging.getLogger(__name__)
config = get_config()


def is_command_message(message: Message) -> bool:
    """
    Check if message is a command message.
    Unified function to determine if a message is a bot command.
    
    Args:
        message: Telegram message object
        
    Returns:
        bool: True if message is a command, False otherwise
    """
    if not message or not message.text:
        return False
    
    text = message.text.strip()
    # Check if message starts with / (command prefix)
    if text.startswith('/'):
        return True
    
    # Check for bot mentions with commands
    if message.entities:
        for entity in message.entities:
            if entity.type == "bot_command":
                return True
    
    return False


async def is_admin(user: User, chat: Chat, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Check if user is an administrator.
    
    Args:
        user: Telegram user object
        chat: Telegram chat object
        context: Bot context
        
    Returns:
        bool: True if user is admin, False otherwise
    """
    # Check if user is in configured admin list
    if user.id in config.ADMIN_IDS:
        return True
    
    # Check if user is chat administrator
    try:
        chat_member = await context.bot.get_chat_member(chat.id, user.id)
        return chat_member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except (BadRequest, Forbidden, TelegramError) as e:
        logger.error(f"Error checking admin status for user {user.id} in chat {chat.id}: {e}")
        return False


async def mute_user(
    user_id: int, 
    chat_id: int, 
    duration_hours: int, 
    context: ContextTypes.DEFAULT_TYPE,
    reason: str = "Нарушение правил"
) -> bool:
    """
    Mute user in chat with detailed error logging.
    
    Args:
        user_id: ID of user to mute
        chat_id: Chat ID where to mute user
        duration_hours: Duration of mute in hours
        context: Bot context
        reason: Reason for mute
        
    Returns:
        bool: True if mute was successful, False otherwise
    """
    try:
        until_date = datetime.now() + timedelta(hours=duration_hours)
        
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions={
                'can_send_messages': False,
                'can_send_media_messages': False,
                'can_send_polls': False,
                'can_send_other_messages': False,
                'can_add_web_page_previews': False,
                'can_change_info': False,
                'can_invite_users': False,
                'can_pin_messages': False
            },
            until_date=until_date
        )
        
        logger.info(f"Successfully muted user {user_id} in chat {chat_id} for {duration_hours} hours. Reason: {reason}")
        return True
        
    except Forbidden as e:
        logger.error(f"Bot lacks permissions to mute user {user_id} in chat {chat_id}: {e}")
        return False
    except BadRequest as e:
        logger.error(f"Bad request when muting user {user_id} in chat {chat_id}: {e}")
        return False
    except TelegramError as e:
        logger.error(f"Telegram error when muting user {user_id} in chat {chat_id}: {e}")
        return False
    except Exception as e:
        logger.exception(f"Unexpected error when muting user {user_id} in chat {chat_id}: {e}")
        return False


async def kick_user(
    user_id: int, 
    chat_id: int, 
    context: ContextTypes.DEFAULT_TYPE,
    reason: str = "Нарушение правил"
) -> bool:
    """
    Kick user from chat with detailed error logging.
    
    Args:
        user_id: ID of user to kick
        chat_id: Chat ID where to kick user
        context: Bot context
        reason: Reason for kick
        
    Returns:
        bool: True if kick was successful, False otherwise
    """
    try:
        await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
        # Unban immediately to allow rejoin
        await context.bot.unban_chat_member(chat_id=chat_id, user_id=user_id)
        
        logger.info(f"Successfully kicked user {user_id} from chat {chat_id}. Reason: {reason}")
        return True
        
    except Forbidden as e:
        logger.error(f"Bot lacks permissions to kick user {user_id} from chat {chat_id}: {e}")
        return False
    except BadRequest as e:
        logger.error(f"Bad request when kicking user {user_id} from chat {chat_id}: {e}")
        return False
    except TelegramError as e:
        logger.error(f"Telegram error when kicking user {user_id} from chat {chat_id}: {e}")
        return False
    except Exception as e:
        logger.exception(f"Unexpected error when kicking user {user_id} from chat {chat_id}: {e}")
        return False


def contains_banned_words(text: str) -> bool:
    """
    Check if text contains banned words.
    
    Args:
        text: Text to check
        
    Returns:
        bool: True if text contains banned words, False otherwise
    """
    if not text or not config.BANNED_WORDS:
        return False
    
    text_lower = text.lower()
    for banned_word in config.BANNED_WORDS:
        if banned_word in text_lower:
            return True
    return False


def contains_links(text: str) -> bool:
    """
    Check if text contains links.
    
    Args:
        text: Text to check
        
    Returns:
        bool: True if text contains links, False otherwise
    """
    if not text:
        return False
    
    # Simple URL pattern matching
    url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    return bool(re.search(url_pattern, text))


def is_allowed_domain(url: str) -> bool:
    """
    Check if URL domain is in allowed domains list.
    
    Args:
        url: URL to check
        
    Returns:
        bool: True if domain is allowed, False otherwise
    """
    if not config.ALLOWED_DOMAINS:
        return False
    
    try:
        parsed_url = urlparse(url)
        domain = parsed_url.netloc.lower()
        
        # Remove www. prefix if present
        if domain.startswith('www.'):
            domain = domain[4:]
        
        return domain in [allowed_domain.lower() for allowed_domain in config.ALLOWED_DOMAINS]
    except Exception:
        return False


def extract_urls_from_text(text: str) -> List[str]:
    """
    Extract URLs from text.
    
    Args:
        text: Text to extract URLs from
        
    Returns:
        List[str]: List of URLs found in text
    """
    if not text:
        return []
    
    url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    return re.findall(url_pattern, text)


def has_disallowed_links(text: str) -> bool:
    """
    Check if text contains links that are not in allowed domains.
    
    Args:
        text: Text to check
        
    Returns:
        bool: True if text contains disallowed links, False otherwise
    """
    urls = extract_urls_from_text(text)
    for url in urls:
        if not is_allowed_domain(url):
            return True
    return False


# Anti-flood tracking
user_message_times: dict = {}


def check_flood(user_id: int) -> bool:
    """
    Check if user is flooding messages.
    
    Args:
        user_id: ID of user to check
        
    Returns:
        bool: True if user is flooding, False otherwise
    """
    current_time = datetime.now()
    
    if user_id not in user_message_times:
        user_message_times[user_id] = []
    
    # Add current message time
    user_message_times[user_id].append(current_time)
    
    # Remove old messages outside the window
    window_start = current_time - timedelta(seconds=config.ANTIFLOOD_WINDOW_SECONDS)
    user_message_times[user_id] = [
        msg_time for msg_time in user_message_times[user_id] 
        if msg_time >= window_start
    ]
    
    # Check if user exceeded message limit
    return len(user_message_times[user_id]) > config.ANTIFLOOD_MAX_MESSAGES


def format_user_mention(user: User) -> str:
    """
    Format user mention for logging and messages.
    
    Args:
        user: Telegram user object
        
    Returns:
        str: Formatted user mention
    """
    if user.username:
        return f"@{user.username}"
    else:
        return f"{user.first_name} (ID: {user.id})"