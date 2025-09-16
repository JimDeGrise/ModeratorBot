"""Rate limiter implementation with sliding window algorithm."""
import time
import asyncio
from typing import Dict, List, Tuple
from collections import defaultdict
from dataclasses import dataclass
from config.settings import config


@dataclass
class MessageRecord:
    """Represents a message record for rate limiting."""
    timestamp: float
    user_id: int
    chat_id: int


class RateLimiter:
    """
    Rate limiter using sliding window algorithm.
    
    Tracks messages per user per chat and detects when rate limits are exceeded.
    Non-blocking design that works with concurrent chats.
    """
    
    def __init__(self):
        # Key: (chat_id, user_id), Value: List of message timestamps
        self._message_history: Dict[Tuple[int, int], List[float]] = defaultdict(list)
        self._lock = asyncio.Lock()
    
    async def check_rate_limit(self, user_id: int, chat_id: int) -> bool:
        """
        Check if a user has exceeded the rate limit in a chat.
        
        Args:
            user_id: The user's ID
            chat_id: The chat's ID
            
        Returns:
            True if rate limit is exceeded, False otherwise
        """
        # Skip rate limiting for exempt users
        if config.is_exempt_from_rate_limit(user_id):
            return False
        
        current_time = time.time()
        key = (chat_id, user_id)
        
        async with self._lock:
            # Clean up old messages outside the window
            cutoff_time = current_time - config.antiflood_window_seconds
            self._message_history[key] = [
                timestamp for timestamp in self._message_history[key]
                if timestamp > cutoff_time
            ]
            
            # Add current message
            self._message_history[key].append(current_time)
            
            # Check if rate limit is exceeded
            message_count = len(self._message_history[key])
            return message_count > config.antiflood_max_messages
    
    async def add_message(self, user_id: int, chat_id: int) -> bool:
        """
        Add a message and check if rate limit is exceeded.
        
        This is a convenience method that combines adding a message
        and checking the rate limit in one call.
        
        Args:
            user_id: The user's ID
            chat_id: The chat's ID
            
        Returns:
            True if rate limit is exceeded, False otherwise
        """
        return await self.check_rate_limit(user_id, chat_id)
    
    async def get_message_count(self, user_id: int, chat_id: int) -> int:
        """
        Get the current message count for a user in a chat within the window.
        
        Args:
            user_id: The user's ID
            chat_id: The chat's ID
            
        Returns:
            Number of messages in the current window
        """
        current_time = time.time()
        key = (chat_id, user_id)
        
        async with self._lock:
            # Clean up old messages
            cutoff_time = current_time - config.antiflood_window_seconds
            self._message_history[key] = [
                timestamp for timestamp in self._message_history[key]
                if timestamp > cutoff_time
            ]
            
            return len(self._message_history[key])
    
    async def reset_user_history(self, user_id: int, chat_id: int):
        """
        Reset message history for a specific user in a chat.
        
        Args:
            user_id: The user's ID
            chat_id: The chat's ID
        """
        key = (chat_id, user_id)
        async with self._lock:
            if key in self._message_history:
                del self._message_history[key]
    
    async def cleanup_old_entries(self):
        """
        Clean up old entries from all message histories.
        
        This should be called periodically to prevent memory leaks.
        """
        current_time = time.time()
        cutoff_time = current_time - config.antiflood_window_seconds * 2  # Keep some buffer
        
        async with self._lock:
            keys_to_remove = []
            for key, timestamps in self._message_history.items():
                # Remove old timestamps
                updated_timestamps = [
                    timestamp for timestamp in timestamps
                    if timestamp > cutoff_time
                ]
                
                if updated_timestamps:
                    self._message_history[key] = updated_timestamps
                else:
                    keys_to_remove.append(key)
            
            # Remove empty entries
            for key in keys_to_remove:
                del self._message_history[key]
    
    def get_stats(self) -> Dict[str, int]:
        """
        Get statistics about the rate limiter.
        
        Returns:
            Dictionary with stats about tracked users and messages
        """
        total_tracked_users = len(self._message_history)
        total_messages = sum(len(timestamps) for timestamps in self._message_history.values())
        
        return {
            'tracked_users': total_tracked_users,
            'total_messages_in_window': total_messages
        }


# Global rate limiter instance
rate_limiter = RateLimiter()