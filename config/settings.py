"""Configuration management for the ModeratorBot."""
import os
from typing import List, Optional
from dotenv import load_dotenv


class Config:
    """Configuration class that loads settings from environment variables."""
    
    def __init__(self):
        load_dotenv()
        
        # Bot configuration
        self.bot_token: str = os.getenv('BOT_TOKEN', '')
        # Allow missing token for testing
        if not self.bot_token and not os.getenv('PYTEST_CURRENT_TEST'):
            raise ValueError("BOT_TOKEN is required")
            
        # Admin configuration
        admin_ids_str = os.getenv('ADMIN_IDS', '')
        self.admin_ids: List[int] = []
        if admin_ids_str:
            try:
                self.admin_ids = [int(x.strip()) for x in admin_ids_str.split(',') if x.strip()]
            except ValueError:
                raise ValueError("ADMIN_IDS must be comma-separated integers")
        
        # Rate limiting configuration
        self.antiflood_max_messages: int = int(os.getenv('ANTIFLOOD_MAX_MESSAGES', '5'))
        self.antiflood_window_seconds: int = int(os.getenv('ANTIFLOOD_WINDOW_SECONDS', '10'))
        
        # Escalation configuration
        self.warns_to_punish: int = int(os.getenv('WARNS_TO_PUNISH', '3'))
        self.auto_mute_hours: int = int(os.getenv('AUTO_MUTE_HOURS', '24'))
        
        # Progressive mute durations (in minutes)
        escalation_str = os.getenv('ESCALATION_DURATIONS', '60,360,1440,10080')  # 1h, 6h, 24h, 7d
        try:
            self.escalation_durations = [int(x.strip()) for x in escalation_str.split(',')]
        except ValueError:
            self.escalation_durations = [60, 360, 1440, 10080]
        
        # Whitelist configuration
        whitelist_str = os.getenv('WHITELISTED_USERS', '')
        self.whitelisted_users: List[int] = []
        if whitelist_str:
            try:
                self.whitelisted_users = [int(x.strip()) for x in whitelist_str.split(',') if x.strip()]
            except ValueError:
                raise ValueError("WHITELISTED_USERS must be comma-separated integers")
        
        # Other existing configuration
        self.rules: str = os.getenv('RULES', 'Please follow the community rules.')
        self.allowed_domains: List[str] = []
        domains_str = os.getenv('ALLOWED_DOMAINS', '')
        if domains_str:
            self.allowed_domains = [x.strip() for x in domains_str.split(',') if x.strip()]
            
        self.banned_words: List[str] = []
        words_str = os.getenv('BANNED_WORDS', '')
        if words_str:
            self.banned_words = [x.strip().lower() for x in words_str.split(',') if x.strip()]
            
        self.captcha_timeout_seconds: int = int(os.getenv('CAPTCHA_TIMEOUT_SECONDS', '120'))
        self.db_path: str = os.getenv('DB_PATH', './data/modbot.db')
        
        # Admin notification settings
        self.notify_admins: bool = os.getenv('NOTIFY_ADMINS', 'true').lower() == 'true'
        self.notification_chat: Optional[int] = None
        if os.getenv('NOTIFICATION_CHAT'):
            try:
                self.notification_chat = int(os.getenv('NOTIFICATION_CHAT'))
            except ValueError:
                pass
    
    def is_admin(self, user_id: int) -> bool:
        """Check if a user is an admin."""
        return user_id in self.admin_ids
    
    def is_whitelisted(self, user_id: int) -> bool:
        """Check if a user is whitelisted."""
        return user_id in self.whitelisted_users
    
    def is_exempt_from_rate_limit(self, user_id: int) -> bool:
        """Check if a user is exempt from rate limiting."""
        return self.is_admin(user_id) or self.is_whitelisted(user_id)
    
    def get_mute_duration(self, violation_count: int) -> int:
        """Get mute duration in minutes based on violation count."""
        if violation_count <= 0:
            return self.escalation_durations[0] if self.escalation_durations else 60
        
        # Use the last duration if we exceed the configured escalation levels
        index = min(violation_count - 1, len(self.escalation_durations) - 1)
        return self.escalation_durations[index]


# Global config instance
config = Config()