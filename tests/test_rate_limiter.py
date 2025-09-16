"""Unit tests for the rate limiter."""
import pytest
import asyncio
import time
from unittest.mock import patch
from src.rate_limiter import RateLimiter


class TestRateLimiter:
    """Test cases for the RateLimiter class."""
    
    @pytest.fixture
    def rate_limiter(self):
        """Create a fresh rate limiter for each test."""
        return RateLimiter()
    
    @pytest.mark.asyncio
    async def test_single_message_under_limit(self, rate_limiter):
        """Test that a single message doesn't trigger rate limit."""
        result = await rate_limiter.add_message(user_id=123, chat_id=456)
        assert result is False, "Single message should not trigger rate limit"
    
    @pytest.mark.asyncio
    async def test_multiple_messages_under_limit(self, rate_limiter):
        """Test that messages under the limit don't trigger rate limiting."""
        user_id, chat_id = 123, 456
        
        # Send 4 messages (under the default limit of 5)
        for i in range(4):
            result = await rate_limiter.add_message(user_id, chat_id)
            assert result is False, f"Message {i+1} should not trigger rate limit"
    
    @pytest.mark.asyncio
    async def test_messages_at_limit(self, rate_limiter):
        """Test that exactly at limit doesn't trigger rate limiting."""
        user_id, chat_id = 123, 456
        
        # Send exactly 5 messages (at the limit)
        for i in range(5):
            result = await rate_limiter.add_message(user_id, chat_id)
            assert result is False, f"Message {i+1} should not trigger rate limit"
    
    @pytest.mark.asyncio
    async def test_messages_over_limit(self, rate_limiter):
        """Test that exceeding the limit triggers rate limiting."""
        user_id, chat_id = 123, 456
        
        # Send 5 messages (at limit)
        for i in range(5):
            result = await rate_limiter.add_message(user_id, chat_id)
            assert result is False, f"Message {i+1} should not trigger rate limit"
        
        # 6th message should trigger rate limit
        result = await rate_limiter.add_message(user_id, chat_id)
        assert result is True, "6th message should trigger rate limit"
    
    @pytest.mark.asyncio
    async def test_different_users_separate_limits(self, rate_limiter):
        """Test that different users have separate rate limits."""
        user1, user2, chat_id = 123, 124, 456
        
        # User 1 sends 5 messages
        for i in range(5):
            result = await rate_limiter.add_message(user1, chat_id)
            assert result is False
        
        # User 2 should be able to send messages without triggering limit
        result = await rate_limiter.add_message(user2, chat_id)
        assert result is False, "Different user should have separate limit"
        
        # User 1's 6th message should trigger limit
        result = await rate_limiter.add_message(user1, chat_id)
        assert result is True, "User 1 should trigger rate limit"
        
        # User 2 can still send more messages
        for i in range(4):
            result = await rate_limiter.add_message(user2, chat_id)
            assert result is False
    
    @pytest.mark.asyncio
    async def test_different_chats_separate_limits(self, rate_limiter):
        """Test that different chats have separate rate limits."""
        user_id, chat1, chat2 = 123, 456, 457
        
        # Send 5 messages in chat 1
        for i in range(5):
            result = await rate_limiter.add_message(user_id, chat1)
            assert result is False
        
        # User should be able to send messages in chat 2
        result = await rate_limiter.add_message(user_id, chat2)
        assert result is False, "Different chat should have separate limit"
        
        # Chat 1 should trigger limit on 6th message
        result = await rate_limiter.add_message(user_id, chat1)
        assert result is True, "Chat 1 should trigger rate limit"
        
        # Chat 2 should still allow more messages
        for i in range(4):
            result = await rate_limiter.add_message(user_id, chat2)
            assert result is False
    
    @pytest.mark.asyncio
    async def test_sliding_window_behavior(self, rate_limiter):
        """Test that the sliding window properly expires old messages."""
        user_id, chat_id = 123, 456
        
        # Mock time to control window behavior
        with patch('time.time') as mock_time:
            # Start at time 0
            mock_time.return_value = 0.0
            
            # Send 5 messages at time 0
            for i in range(5):
                result = await rate_limiter.add_message(user_id, chat_id)
                assert result is False
            
            # Move to time 11 (outside the 10-second window)
            mock_time.return_value = 11.0
            
            # Should be able to send messages again
            result = await rate_limiter.add_message(user_id, chat_id)
            assert result is False, "Messages should be allowed after window expires"
            
            # Can send up to 5 more messages
            for i in range(4):
                result = await rate_limiter.add_message(user_id, chat_id)
                assert result is False
            
            # 6th message in new window should trigger limit
            result = await rate_limiter.add_message(user_id, chat_id)
            assert result is True
    
    @pytest.mark.asyncio
    async def test_partial_window_expiry(self, rate_limiter):
        """Test partial expiry of messages in sliding window."""
        user_id, chat_id = 123, 456
        
        with patch('time.time') as mock_time:
            # Send 3 messages at time 0
            mock_time.return_value = 0.0
            for i in range(3):
                result = await rate_limiter.add_message(user_id, chat_id)
                assert result is False
            
            # Send 2 more messages at time 5
            mock_time.return_value = 5.0
            for i in range(2):
                result = await rate_limiter.add_message(user_id, chat_id)
                assert result is False
            
            # At time 5, we have 5 messages total
            # Move to time 11 (messages from time 0 should expire)
            mock_time.return_value = 11.0
            
            # Should have 2 messages left from time 5
            count = await rate_limiter.get_message_count(user_id, chat_id)
            assert count == 2, "Should have 2 messages remaining after partial expiry"
            
            # Should be able to send 3 more messages
            for i in range(3):
                result = await rate_limiter.add_message(user_id, chat_id)
                assert result is False
            
            # 6th message should trigger limit
            result = await rate_limiter.add_message(user_id, chat_id)
            assert result is True
    
    @pytest.mark.asyncio
    async def test_exempt_users_bypass_limit(self, rate_limiter):
        """Test that exempt users bypass rate limiting."""
        user_id, chat_id = 123, 456
        
        # Mock config to make user exempt
        with patch('src.rate_limiter.config.is_exempt_from_rate_limit') as mock_exempt:
            mock_exempt.return_value = True
            
            # Should be able to send many messages without triggering limit
            for i in range(20):
                result = await rate_limiter.add_message(user_id, chat_id)
                assert result is False, f"Exempt user should not trigger limit on message {i+1}"
    
    @pytest.mark.asyncio
    async def test_get_message_count(self, rate_limiter):
        """Test getting current message count."""
        user_id, chat_id = 123, 456
        
        # Initially should be 0
        count = await rate_limiter.get_message_count(user_id, chat_id)
        assert count == 0
        
        # Add 3 messages
        for i in range(3):
            await rate_limiter.add_message(user_id, chat_id)
        
        count = await rate_limiter.get_message_count(user_id, chat_id)
        assert count == 3
    
    @pytest.mark.asyncio
    async def test_reset_user_history(self, rate_limiter):
        """Test resetting user history."""
        user_id, chat_id = 123, 456
        
        # Add some messages
        for i in range(3):
            await rate_limiter.add_message(user_id, chat_id)
        
        count = await rate_limiter.get_message_count(user_id, chat_id)
        assert count == 3
        
        # Reset history
        await rate_limiter.reset_user_history(user_id, chat_id)
        
        count = await rate_limiter.get_message_count(user_id, chat_id)
        assert count == 0
    
    @pytest.mark.asyncio
    async def test_cleanup_old_entries(self, rate_limiter):
        """Test cleanup of old entries."""
        user_id, chat_id = 123, 456
        
        with patch('time.time') as mock_time:
            # Add messages at time 0
            mock_time.return_value = 0.0
            for i in range(3):
                await rate_limiter.add_message(user_id, chat_id)
            
            # Move to time 30 (well past window)
            mock_time.return_value = 30.0
            
            # Cleanup should remove old entries
            await rate_limiter.cleanup_old_entries()
            
            # Message count should be 0 after cleanup
            count = await rate_limiter.get_message_count(user_id, chat_id)
            assert count == 0
    
    @pytest.mark.asyncio
    async def test_concurrent_access(self, rate_limiter):
        """Test concurrent access to rate limiter."""
        user_id, chat_id = 123, 456
        
        async def add_messages(count):
            results = []
            for i in range(count):
                result = await rate_limiter.add_message(user_id, chat_id)
                results.append(result)
            return results
        
        # Run concurrent tasks
        tasks = [add_messages(3) for _ in range(3)]
        results = await asyncio.gather(*tasks)
        
        # Flatten results
        all_results = [r for sublist in results for r in sublist]
        
        # Should have some rate limit triggers
        rate_limit_count = sum(1 for r in all_results if r)
        assert rate_limit_count > 0, "Should have some rate limit triggers with concurrent access"
    
    def test_get_stats(self, rate_limiter):
        """Test getting rate limiter statistics."""
        stats = rate_limiter.get_stats()
        
        assert 'tracked_users' in stats
        assert 'total_messages_in_window' in stats
        assert isinstance(stats['tracked_users'], int)
        assert isinstance(stats['total_messages_in_window'], int)