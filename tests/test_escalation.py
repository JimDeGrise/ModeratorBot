"""Unit tests for escalation logic and moderation."""
import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
from src.moderation import ModerationManager
from src.database import Database, UserViolation, UserStats


class TestModerationEscalation:
    """Test cases for moderation escalation logic."""
    
    @pytest.fixture
    def mock_bot(self):
        """Create a mock bot."""
        bot = AsyncMock()
        bot.restrict_chat_member = AsyncMock()
        bot.get_chat_member = AsyncMock()
        bot.send_message = AsyncMock()
        bot.delete_message = AsyncMock()
        return bot
    
    @pytest.fixture
    def moderation_manager(self, mock_bot):
        """Create a moderation manager with mock bot."""
        return ModerationManager(mock_bot)
    
    @pytest.fixture
    def mock_database(self):
        """Create a mock database."""
        db = AsyncMock(spec=Database)
        db.add_violation = AsyncMock()
        db.get_user_violation_count = AsyncMock()
        db.get_user_stats = AsyncMock()
        return db
    
    @pytest.mark.asyncio
    async def test_first_violation_basic_mute(self, moderation_manager, mock_database):
        """Test that first violation gets basic mute duration."""
        user_id, chat_id = 123, 456
        
        with patch('src.moderation.db', mock_database), \
             patch('src.moderation.rate_limiter') as mock_rate_limiter, \
             patch('src.moderation.config') as mock_config:
            
            # Setup mocks
            mock_rate_limiter.add_message = AsyncMock(return_value=True)  # Rate limit exceeded
            mock_rate_limiter.reset_user_history = AsyncMock()
            mock_database.get_user_violation_count.return_value = 0  # First violation
            mock_database.add_violation.return_value = 1
            mock_config.get_mute_duration.return_value = 60  # 60 minutes for first violation
            mock_config.notify_admins = False
            
            # Mock successful mute
            moderation_manager._apply_mute = AsyncMock(return_value={
                'success': True,
                'username': 'TestUser',
                'until_date': datetime.utcnow() + timedelta(minutes=60)
            })
            
            # Test
            result = await moderation_manager.handle_message(user_id, chat_id)
            
            # Assertions
            assert result is not None
            assert result['action'] == 'mute'
            assert result['violation_count'] == 1
            assert result['mute_duration_minutes'] == 60
            mock_config.get_mute_duration.assert_called_with(1)
    
    @pytest.mark.asyncio
    async def test_escalation_progression(self, moderation_manager, mock_database):
        """Test that violations escalate properly."""
        user_id, chat_id = 123, 456
        
        escalation_durations = [60, 360, 1440, 10080]  # 1h, 6h, 24h, 7d
        
        for violation_num, expected_duration in enumerate(escalation_durations, 1):
            with patch('src.moderation.db', mock_database), \
                 patch('src.moderation.rate_limiter') as mock_rate_limiter, \
                 patch('src.moderation.config') as mock_config:
                
                # Setup mocks for this violation level
                mock_rate_limiter.add_message = AsyncMock(return_value=True)
                mock_rate_limiter.reset_user_history = AsyncMock()
                mock_database.get_user_violation_count.return_value = violation_num - 1
                mock_database.add_violation.return_value = violation_num
                mock_config.get_mute_duration.return_value = expected_duration
                mock_config.notify_admins = False
                
                moderation_manager._apply_mute = AsyncMock(return_value={
                    'success': True,
                    'username': 'TestUser',
                    'until_date': datetime.utcnow() + timedelta(minutes=expected_duration)
                })
                
                # Test
                result = await moderation_manager.handle_message(user_id, chat_id)
                
                # Assertions
                assert result['violation_count'] == violation_num
                assert result['mute_duration_minutes'] == expected_duration
                mock_config.get_mute_duration.assert_called_with(violation_num)
    
    @pytest.mark.asyncio
    async def test_exempt_users_not_processed(self, moderation_manager):
        """Test that exempt users (admins/whitelisted) are not processed."""
        user_id, chat_id = 123, 456
        
        with patch('src.moderation.rate_limiter') as mock_rate_limiter:
            mock_rate_limiter.add_message = AsyncMock(return_value=False)  # Exempt user
            
            result = await moderation_manager.handle_message(user_id, chat_id)
            
            assert result is None
            mock_rate_limiter.add_message.assert_called_once_with(user_id, chat_id)
    
    @pytest.mark.asyncio
    async def test_failed_mute_handling(self, moderation_manager, mock_database):
        """Test handling when mute operation fails."""
        user_id, chat_id = 123, 456
        
        with patch('src.moderation.db', mock_database), \
             patch('src.moderation.rate_limiter') as mock_rate_limiter, \
             patch('src.moderation.config') as mock_config:
            
            # Setup mocks
            mock_rate_limiter.add_message = AsyncMock(return_value=True)
            mock_database.get_user_violation_count.return_value = 0
            mock_database.add_violation.return_value = 1
            mock_config.get_mute_duration.return_value = 60
            
            # Mock failed mute
            moderation_manager._apply_mute = AsyncMock(return_value={
                'success': False,
                'error': 'Bot not admin',
                'username': 'TestUser'
            })
            
            # Test
            result = await moderation_manager.handle_message(user_id, chat_id)
            
            # Should return None when mute fails
            assert result is None
    
    @pytest.mark.asyncio
    async def test_admin_notification(self, moderation_manager, mock_database):
        """Test admin notification functionality."""
        user_id, chat_id = 123, 456
        
        with patch('src.moderation.db', mock_database), \
             patch('src.moderation.rate_limiter') as mock_rate_limiter, \
             patch('src.moderation.config') as mock_config:
            
            # Setup mocks
            mock_rate_limiter.add_message = AsyncMock(return_value=True)
            mock_rate_limiter.reset_user_history = AsyncMock()
            mock_database.get_user_violation_count.return_value = 2  # 3rd violation
            mock_database.add_violation.return_value = 3
            mock_config.get_mute_duration.return_value = 1440  # 24 hours
            mock_config.notify_admins = True
            mock_config.admin_ids = [789, 790]
            mock_config.notification_chat = None
            
            moderation_manager._apply_mute = AsyncMock(return_value={
                'success': True,
                'username': 'TestUser',
                'until_date': datetime.utcnow() + timedelta(minutes=1440)
            })
            
            moderation_manager._notify_admins_of_mute = AsyncMock()
            
            # Test
            result = await moderation_manager.handle_message(user_id, chat_id)
            
            # Verify notification was called
            moderation_manager._notify_admins_of_mute.assert_called_once_with(
                user_id, chat_id, 3, 1440, 'TestUser'
            )
    
    @pytest.mark.asyncio
    async def test_manual_mute(self, moderation_manager, mock_database):
        """Test manual mute functionality."""
        user_id, chat_id = 123, 456
        duration = 120
        reason = "Manual mute by admin"
        
        with patch('src.moderation.db', mock_database):
            mock_database.add_violation.return_value = 1
            
            moderation_manager._apply_mute = AsyncMock(return_value={
                'success': True,
                'username': 'TestUser',
                'until_date': datetime.utcnow() + timedelta(minutes=duration)
            })
            
            result = await moderation_manager.manual_mute(user_id, chat_id, duration, reason)
            
            assert result['action'] == 'manual_mute'
            assert result['mute_duration_minutes'] == duration
            assert result['reason'] == reason
            
            # Verify violation was recorded
            mock_database.add_violation.assert_called_once()
            violation_arg = mock_database.add_violation.call_args[0][0]
            assert violation_arg.violation_type == 'manual'
            assert violation_arg.mute_duration_minutes == duration
    
    @pytest.mark.asyncio
    async def test_unmute_user(self, moderation_manager):
        """Test unmuting a user."""
        user_id, chat_id = 123, 456
        
        # Mock successful unmute
        moderation_manager.bot.restrict_chat_member = AsyncMock()
        
        result = await moderation_manager.unmute_user(user_id, chat_id)
        
        assert result['success'] is True
        assert result['action'] == 'unmute'
        
        # Verify bot method was called
        moderation_manager.bot.restrict_chat_member.assert_called_once()
        call_args = moderation_manager.bot.restrict_chat_member.call_args
        assert call_args[1]['chat_id'] == chat_id
        assert call_args[1]['user_id'] == user_id
    
    @pytest.mark.asyncio
    async def test_get_user_status(self, moderation_manager, mock_database):
        """Test getting user status."""
        user_id, chat_id = 123, 456
        
        with patch('src.moderation.db', mock_database), \
             patch('src.moderation.rate_limiter') as mock_rate_limiter, \
             patch('src.moderation.config') as mock_config:
            
            # Setup mocks
            mock_stats = UserStats(
                user_id=user_id,
                chat_id=chat_id,
                total_violations=3,
                last_violation=datetime.utcnow(),
                is_currently_muted=True
            )
            mock_database.get_user_stats.return_value = mock_stats
            mock_rate_limiter.get_message_count = AsyncMock(return_value=2)
            mock_config.is_exempt_from_rate_limit.return_value = False
            mock_config.is_admin.return_value = False
            mock_config.is_whitelisted.return_value = False
            
            result = await moderation_manager.get_user_status(user_id, chat_id)
            
            assert result['user_id'] == user_id
            assert result['chat_id'] == chat_id
            assert result['total_violations'] == 3
            assert result['is_currently_muted'] is True
            assert result['current_message_count'] == 2
            assert result['is_exempt'] is False


class TestDatabaseEscalation:
    """Test database functionality for escalation logic."""
    
    @pytest.fixture
    def test_db(self):
        """Create test database."""
        return Database(':memory:')  # In-memory database for testing
    
    @pytest.mark.asyncio
    async def test_violation_count_tracking(self, test_db):
        """Test violation count tracking over time."""
        await test_db.initialize()
        user_id, chat_id = 123, 456
        
        # Add multiple violations
        for i in range(3):
            violation = UserViolation(
                user_id=user_id,
                chat_id=chat_id,
                violation_type='rate_limit',
                timestamp=datetime.utcnow() - timedelta(days=i),
                mute_duration_minutes=60 * (i + 1)
            )
            await test_db.add_violation(violation)
        
        # Check count
        count = await test_db.get_user_violation_count(user_id, chat_id)
        assert count == 3
        
        # Check count with time limit
        count_recent = await test_db.get_user_violation_count(user_id, chat_id, days_back=1)
        assert count_recent == 1  # Only today's violation
    
    @pytest.mark.asyncio
    async def test_user_stats_aggregation(self, test_db):
        """Test user statistics aggregation."""
        await test_db.initialize()
        user_id, chat_id = 123, 456
        
        # Add violations
        base_time = datetime.utcnow()
        for i in range(2):
            violation = UserViolation(
                user_id=user_id,
                chat_id=chat_id,
                violation_type='rate_limit',
                timestamp=base_time - timedelta(hours=i),
                mute_duration_minutes=60
            )
            await test_db.add_violation(violation)
        
        stats = await test_db.get_user_stats(user_id, chat_id)
        
        assert stats.user_id == user_id
        assert stats.chat_id == chat_id
        assert stats.total_violations == 2
        assert stats.last_violation is not None
        assert abs((stats.last_violation - base_time).total_seconds()) < 1
    
    @pytest.mark.asyncio
    async def test_violation_deactivation(self, test_db):
        """Test automatic deactivation of old violations."""
        await test_db.initialize()
        user_id, chat_id = 123, 456
        
        # Add old violation
        old_violation = UserViolation(
            user_id=user_id,
            chat_id=chat_id,
            violation_type='rate_limit',
            timestamp=datetime.utcnow() - timedelta(hours=25),
            mute_duration_minutes=60,
            is_active=True
        )
        await test_db.add_violation(old_violation)
        
        # Add recent violation
        recent_violation = UserViolation(
            user_id=user_id,
            chat_id=chat_id,
            violation_type='rate_limit',
            timestamp=datetime.utcnow() - timedelta(hours=1),
            mute_duration_minutes=60,
            is_active=True
        )
        await test_db.add_violation(recent_violation)
        
        # Deactivate old violations
        await test_db.deactivate_old_violations(hours_back=24)
        
        # Check that recent violation is still active but old one is not
        stats = await test_db.get_user_stats(user_id, chat_id)
        assert stats.is_currently_muted is True  # Recent violation still active
    
    @pytest.mark.asyncio
    async def test_database_cleanup(self, test_db):
        """Test database cleanup of old data."""
        await test_db.initialize()
        user_id, chat_id = 123, 456
        
        # Add very old inactive violation
        old_violation = UserViolation(
            user_id=user_id,
            chat_id=chat_id,
            violation_type='rate_limit',
            timestamp=datetime.utcnow() - timedelta(days=100),
            mute_duration_minutes=60,
            is_active=False
        )
        await test_db.add_violation(old_violation)
        
        # Add recent violation
        recent_violation = UserViolation(
            user_id=user_id,
            chat_id=chat_id,
            violation_type='rate_limit',
            timestamp=datetime.utcnow(),
            mute_duration_minutes=60,
            is_active=True
        )
        await test_db.add_violation(recent_violation)
        
        # Cleanup old data (keep 90 days)
        await test_db.cleanup_old_data(days_to_keep=90)
        
        # Old violation should be removed, recent one should remain
        stats = await test_db.get_database_stats()
        assert stats['total_violations'] == 1
    
    @pytest.mark.asyncio
    async def test_recent_violations_query(self, test_db):
        """Test querying recent violations."""
        await test_db.initialize()
        user_id, chat_id = 123, 456
        
        # Add violations at different times
        recent_violation = UserViolation(
            user_id=user_id,
            chat_id=chat_id,
            violation_type='rate_limit',
            timestamp=datetime.utcnow() - timedelta(minutes=30),
            mute_duration_minutes=60
        )
        await test_db.add_violation(recent_violation)
        
        old_violation = UserViolation(
            user_id=user_id,
            chat_id=chat_id,
            violation_type='rate_limit',
            timestamp=datetime.utcnow() - timedelta(hours=2),
            mute_duration_minutes=60
        )
        await test_db.add_violation(old_violation)
        
        # Query recent violations (last 1 hour)
        recent_violations = await test_db.get_recent_violations(hours_back=1)
        
        assert len(recent_violations) == 1
        assert recent_violations[0]['user_id'] == user_id