"""
Database module for ModeratorBot.
Handles user warnings, captcha tracking, and other persistent data.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

import aiosqlite

from config import get_config

logger = logging.getLogger(__name__)
config = get_config()


class Database:
    """Database manager for ModeratorBot."""
    
    def __init__(self) -> None:
        """Initialize database manager."""
        self.db_path = config.DB_PATH
        self._initialized = False
    
    async def init_db(self) -> None:
        """Initialize database and create tables."""
        if self._initialized:
            return
        
        # Create data directory if it doesn't exist
        import os
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        async with aiosqlite.connect(self.db_path) as db:
            # Create warnings table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS warnings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    reason TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create captcha_pending table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS captcha_pending (
                    user_id INTEGER PRIMARY KEY,
                    chat_id INTEGER NOT NULL,
                    join_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await db.commit()
        
        self._initialized = True
        logger.info("Database initialized successfully")
    
    async def add_warning(self, user_id: int, chat_id: int, reason: str = "Нарушение правил") -> int:
        """
        Add warning to user.
        
        Args:
            user_id: ID of user to warn
            chat_id: Chat ID where warning was issued
            reason: Reason for warning
            
        Returns:
            int: Total warning count for user in this chat
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                'INSERT INTO warnings (user_id, chat_id, reason) VALUES (?, ?, ?)',
                (user_id, chat_id, reason)
            )
            await db.commit()
            
            # Get total warning count
            cursor = await db.execute(
                'SELECT COUNT(*) FROM warnings WHERE user_id = ? AND chat_id = ?',
                (user_id, chat_id)
            )
            result = await cursor.fetchone()
            return result[0] if result else 0
    
    async def get_warning_count(self, user_id: int, chat_id: int) -> int:
        """
        Get warning count for user in chat.
        
        Args:
            user_id: ID of user
            chat_id: Chat ID
            
        Returns:
            int: Warning count
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                'SELECT COUNT(*) FROM warnings WHERE user_id = ? AND chat_id = ?',
                (user_id, chat_id)
            )
            result = await cursor.fetchone()
            return result[0] if result else 0
    
    async def clear_warnings(self, user_id: int, chat_id: int) -> None:
        """
        Clear all warnings for user in chat.
        
        Args:
            user_id: ID of user
            chat_id: Chat ID
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                'DELETE FROM warnings WHERE user_id = ? AND chat_id = ?',
                (user_id, chat_id)
            )
            await db.commit()
    
    async def add_captcha_pending(self, user_id: int, chat_id: int) -> None:
        """
        Add user to captcha pending list.
        
        Args:
            user_id: ID of user
            chat_id: Chat ID
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                'INSERT OR REPLACE INTO captcha_pending (user_id, chat_id) VALUES (?, ?)',
                (user_id, chat_id)
            )
            await db.commit()
    
    async def remove_captcha_pending(self, user_id: int) -> None:
        """
        Remove user from captcha pending list.
        
        Args:
            user_id: ID of user
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                'DELETE FROM captcha_pending WHERE user_id = ?',
                (user_id,)
            )
            await db.commit()
    
    async def is_captcha_pending(self, user_id: int) -> bool:
        """
        Check if user has pending captcha.
        
        Args:
            user_id: ID of user
            
        Returns:
            bool: True if user has pending captcha
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                'SELECT 1 FROM captcha_pending WHERE user_id = ?',
                (user_id,)
            )
            result = await cursor.fetchone()
            return result is not None
    
    async def cleanup_old_captcha(self) -> None:
        """Clean up old captcha entries that have timed out."""
        timeout_seconds = config.CAPTCHA_TIMEOUT_SECONDS
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                '''DELETE FROM captcha_pending 
                   WHERE datetime(join_time, '+{} seconds') < datetime('now')'''.format(timeout_seconds)
            )
            await db.commit()


# Global database instance
db = Database()