"""Database models and operations for the ModeratorBot."""
import aiosqlite
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from config.settings import config


@dataclass
class UserViolation:
    """Represents a user violation record."""
    id: Optional[int] = None
    user_id: int = 0
    chat_id: int = 0
    violation_type: str = 'rate_limit'
    timestamp: datetime = None
    mute_duration_minutes: int = 0
    is_active: bool = True
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


@dataclass
class UserStats:
    """Represents user statistics."""
    user_id: int
    chat_id: int
    total_violations: int
    last_violation: Optional[datetime]
    is_currently_muted: bool


class Database:
    """Database manager for the ModeratorBot."""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or config.db_path
        self._lock = asyncio.Lock()
    
    async def initialize(self):
        """Initialize the database and create tables."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS user_violations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    violation_type TEXT NOT NULL DEFAULT 'rate_limit',
                    timestamp TEXT NOT NULL,
                    mute_duration_minutes INTEGER NOT NULL DEFAULT 0,
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    UNIQUE(user_id, chat_id, timestamp)
                )
            ''')
            
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_user_chat 
                ON user_violations(user_id, chat_id)
            ''')
            
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_timestamp 
                ON user_violations(timestamp)
            ''')
            
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_active 
                ON user_violations(is_active)
            ''')
            
            await db.commit()
    
    async def add_violation(self, violation: UserViolation) -> int:
        """
        Add a new violation record.
        
        Args:
            violation: The violation to add
            
        Returns:
            The ID of the newly created violation
        """
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute('''
                    INSERT INTO user_violations 
                    (user_id, chat_id, violation_type, timestamp, mute_duration_minutes, is_active)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    violation.user_id,
                    violation.chat_id,
                    violation.violation_type,
                    violation.timestamp.isoformat(),
                    violation.mute_duration_minutes,
                    violation.is_active
                ))
                await db.commit()
                return cursor.lastrowid
    
    async def get_user_violation_count(self, user_id: int, chat_id: int, 
                                     days_back: int = 30) -> int:
        """
        Get the number of violations for a user in a chat within the specified timeframe.
        
        Args:
            user_id: The user's ID
            chat_id: The chat's ID
            days_back: Number of days to look back (default: 30)
            
        Returns:
            Number of violations
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days_back)
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT COUNT(*) FROM user_violations
                WHERE user_id = ? AND chat_id = ? AND timestamp > ?
            ''', (user_id, chat_id, cutoff_date.isoformat()))
            
            result = await cursor.fetchone()
            return result[0] if result else 0
    
    async def get_user_stats(self, user_id: int, chat_id: int) -> UserStats:
        """
        Get comprehensive stats for a user in a chat.
        
        Args:
            user_id: The user's ID
            chat_id: The chat's ID
            
        Returns:
            UserStats object with user information
        """
        async with aiosqlite.connect(self.db_path) as db:
            # Get total violations
            cursor = await db.execute('''
                SELECT COUNT(*), MAX(timestamp) FROM user_violations
                WHERE user_id = ? AND chat_id = ?
            ''', (user_id, chat_id))
            
            result = await cursor.fetchone()
            total_violations = result[0] if result else 0
            last_violation_str = result[1] if result and result[1] else None
            
            last_violation = None
            if last_violation_str:
                try:
                    last_violation = datetime.fromisoformat(last_violation_str)
                except ValueError:
                    pass
            
            # Check if currently muted (has active violation in last 24 hours)
            recent_cutoff = datetime.utcnow() - timedelta(hours=24)
            cursor = await db.execute('''
                SELECT COUNT(*) FROM user_violations
                WHERE user_id = ? AND chat_id = ? AND timestamp > ? AND is_active = 1
            ''', (user_id, chat_id, recent_cutoff.isoformat()))
            
            active_violations = await cursor.fetchone()
            is_currently_muted = (active_violations[0] if active_violations else 0) > 0
            
            return UserStats(
                user_id=user_id,
                chat_id=chat_id,
                total_violations=total_violations,
                last_violation=last_violation,
                is_currently_muted=is_currently_muted
            )
    
    async def deactivate_old_violations(self, hours_back: int = 24):
        """
        Deactivate violations older than the specified timeframe.
        
        Args:
            hours_back: Number of hours to look back
        """
        cutoff_date = datetime.utcnow() - timedelta(hours=hours_back)
        
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    UPDATE user_violations 
                    SET is_active = 0 
                    WHERE timestamp < ? AND is_active = 1
                ''', (cutoff_date.isoformat(),))
                await db.commit()
    
    async def get_recent_violations(self, hours_back: int = 1) -> List[Dict[str, Any]]:
        """
        Get recent violations for monitoring purposes.
        
        Args:
            hours_back: Number of hours to look back
            
        Returns:
            List of violation dictionaries
        """
        cutoff_date = datetime.utcnow() - timedelta(hours=hours_back)
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT user_id, chat_id, violation_type, timestamp, mute_duration_minutes
                FROM user_violations
                WHERE timestamp > ?
                ORDER BY timestamp DESC
            ''', (cutoff_date.isoformat(),))
            
            rows = await cursor.fetchall()
            return [
                {
                    'user_id': row[0],
                    'chat_id': row[1],
                    'violation_type': row[2],
                    'timestamp': row[3],
                    'mute_duration_minutes': row[4]
                }
                for row in rows
            ]
    
    async def cleanup_old_data(self, days_to_keep: int = 90):
        """
        Clean up old violation data to prevent database growth.
        
        Args:
            days_to_keep: Number of days of data to keep
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
        
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    DELETE FROM user_violations 
                    WHERE timestamp < ? AND is_active = 0
                ''', (cutoff_date.isoformat(),))
                await db.commit()
    
    async def get_database_stats(self) -> Dict[str, int]:
        """
        Get statistics about the database.
        
        Returns:
            Dictionary with database statistics
        """
        async with aiosqlite.connect(self.db_path) as db:
            # Total violations
            cursor = await db.execute('SELECT COUNT(*) FROM user_violations')
            total_violations = (await cursor.fetchone())[0]
            
            # Active violations
            cursor = await db.execute('SELECT COUNT(*) FROM user_violations WHERE is_active = 1')
            active_violations = (await cursor.fetchone())[0]
            
            # Unique users
            cursor = await db.execute('SELECT COUNT(DISTINCT user_id) FROM user_violations')
            unique_users = (await cursor.fetchone())[0]
            
            # Unique chats
            cursor = await db.execute('SELECT COUNT(DISTINCT chat_id) FROM user_violations')
            unique_chats = (await cursor.fetchone())[0]
            
            return {
                'total_violations': total_violations,
                'active_violations': active_violations,
                'unique_users': unique_users,
                'unique_chats': unique_chats
            }


# Global database instance
db = Database()