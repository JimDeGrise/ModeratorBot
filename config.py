"""
Configuration module with singleton pattern for ModeratorBot.
Caches config object to prevent repeated environment variable loading.
"""

import os
from typing import List, Optional
from dotenv import load_dotenv


class Config:
    """Singleton configuration class for ModeratorBot."""
    
    _instance: Optional['Config'] = None
    _initialized: bool = False
    
    def __new__(cls) -> 'Config':
        """Create singleton instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self) -> None:
        """Initialize configuration if not already done."""
        if not self._initialized:
            load_dotenv()
            self._load_config()
            self._validate_config()
            Config._initialized = True
    
    def _load_config(self) -> None:
        """Load configuration from environment variables."""
        self.BOT_TOKEN: str = os.getenv('BOT_TOKEN', '')
        
        # Admin IDs list
        admin_ids_str = os.getenv('ADMIN_IDS', '')
        self.ADMIN_IDS: List[int] = []
        if admin_ids_str:
            try:
                self.ADMIN_IDS = [int(id_str.strip()) for id_str in admin_ids_str.split(',') if id_str.strip()]
            except ValueError:
                self.ADMIN_IDS = []
        
        # Community rules
        self.RULES: str = os.getenv('RULES', 'Соблюдаем правила сообщества.')
        
        # Anti-flood settings
        self.ANTIFLOOD_MAX_MESSAGES: int = int(os.getenv('ANTIFLOOD_MAX_MESSAGES', '5'))
        self.ANTIFLOOD_WINDOW_SECONDS: int = int(os.getenv('ANTIFLOOD_WINDOW_SECONDS', '10'))
        
        # Warning system
        self.WARNS_TO_PUNISH: int = int(os.getenv('WARNS_TO_PUNISH', '3'))
        self.AUTO_MUTE_HOURS: int = int(os.getenv('AUTO_MUTE_HOURS', '24'))
        
        # Allowed domains for links
        allowed_domains_str = os.getenv('ALLOWED_DOMAINS', '')
        self.ALLOWED_DOMAINS: List[str] = []
        if allowed_domains_str:
            self.ALLOWED_DOMAINS = [domain.strip() for domain in allowed_domains_str.split(',') if domain.strip()]
        
        # Banned words
        banned_words_str = os.getenv('BANNED_WORDS', '')
        self.BANNED_WORDS: List[str] = []
        if banned_words_str:
            self.BANNED_WORDS = [word.strip().lower() for word in banned_words_str.split(',') if word.strip()]
        
        # Captcha settings
        self.CAPTCHA_TIMEOUT_SECONDS: int = int(os.getenv('CAPTCHA_TIMEOUT_SECONDS', '120'))
        
        # Database path
        self.DB_PATH: str = os.getenv('DB_PATH', './data/modbot.db')
    
    def _validate_config(self) -> None:
        """Validate critical configuration parameters."""
        if not self.BOT_TOKEN:
            raise ValueError("BOT_TOKEN environment variable is required")
        
        # Check that admin list is not empty (warning, not error)
        if not self.ADMIN_IDS:
            import logging
            logging.warning("ADMIN_IDS is empty - no administrators configured")


def get_config() -> Config:
    """Get singleton configuration instance."""
    return Config()