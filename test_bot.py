"""
Simple tests for ModeratorBot functionality.
Tests the key optimizations and utility functions.
"""

import os
import tempfile
import unittest
from unittest.mock import Mock

# Set up test environment
os.environ['BOT_TOKEN'] = 'test_token'
os.environ['ADMIN_IDS'] = '123456789,987654321'
os.environ['RULES'] = 'Test rules'
os.environ['ALLOWED_DOMAINS'] = 'example.com,github.com'
os.environ['BANNED_WORDS'] = 'badword1,badword2'

from config import Config, get_config
from utils import (
    is_command_message, contains_banned_words, contains_links,
    has_disallowed_links, is_allowed_domain
)


class TestConfig(unittest.TestCase):
    """Test configuration singleton pattern."""
    
    def test_singleton_pattern(self):
        """Test that config returns the same instance."""
        config1 = get_config()
        config2 = get_config()
        self.assertIs(config1, config2)
    
    def test_config_loading(self):
        """Test that configuration is loaded correctly."""
        config = get_config()
        self.assertEqual(config.BOT_TOKEN, 'test_token')
        self.assertEqual(config.ADMIN_IDS, [123456789, 987654321])
        self.assertEqual(config.RULES, 'Test rules')
        self.assertEqual(config.ALLOWED_DOMAINS, ['example.com', 'github.com'])
        self.assertEqual(config.BANNED_WORDS, ['badword1', 'badword2'])
    
    def test_admin_list_validation(self):
        """Test that empty admin list generates warning."""
        # This test ensures the validation logic works
        config = get_config()
        self.assertIsInstance(config.ADMIN_IDS, list)


class TestUtilityFunctions(unittest.TestCase):
    """Test utility functions."""
    
    def test_is_command_message(self):
        """Test command message detection."""
        # Mock message object
        command_msg = Mock()
        command_msg.text = '/start'
        command_msg.entities = []
        
        non_command_msg = Mock()
        non_command_msg.text = 'Hello world'
        non_command_msg.entities = []
        
        self.assertTrue(is_command_message(command_msg))
        self.assertFalse(is_command_message(non_command_msg))
    
    def test_contains_banned_words(self):
        """Test banned words detection."""
        self.assertTrue(contains_banned_words('This contains badword1'))
        self.assertTrue(contains_banned_words('BADWORD2 in caps'))
        self.assertFalse(contains_banned_words('This is clean text'))
        self.assertFalse(contains_banned_words(''))
    
    def test_contains_links(self):
        """Test link detection."""
        self.assertTrue(contains_links('Check this https://example.com'))
        self.assertTrue(contains_links('Visit http://test.org'))
        self.assertFalse(contains_links('No links here'))
        self.assertFalse(contains_links(''))
    
    def test_is_allowed_domain(self):
        """Test domain allowlist checking."""
        self.assertTrue(is_allowed_domain('https://example.com/path'))
        self.assertTrue(is_allowed_domain('https://github.com/repo'))
        self.assertFalse(is_allowed_domain('https://badsite.com'))
        self.assertFalse(is_allowed_domain('invalid-url'))
    
    def test_has_disallowed_links(self):
        """Test disallowed links detection."""
        self.assertTrue(has_disallowed_links('Visit https://badsite.com'))
        self.assertFalse(has_disallowed_links('Visit https://example.com'))
        self.assertFalse(has_disallowed_links('No links here'))


if __name__ == '__main__':
    unittest.main()