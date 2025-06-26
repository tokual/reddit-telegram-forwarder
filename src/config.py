"""Configuration management for the Reddit Telegram Bot."""

import os
from pathlib import Path
from typing import List, Set, Optional
from dotenv import load_dotenv


class Config:
    """Configuration class for the bot."""
    
    def __init__(self):
        """Initialize configuration from environment variables."""
        # Load environment variables from .env file
        load_dotenv()
        
        # Telegram configuration
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not self.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")
        
        # Reddit configuration
        self.reddit_client_id = os.getenv("REDDIT_CLIENT_ID")
        self.reddit_client_secret = os.getenv("REDDIT_CLIENT_SECRET")
        self.reddit_user_agent = os.getenv("REDDIT_USER_AGENT", "reddit-telegram-forwarder/1.0")
        
        if not self.reddit_client_id or not self.reddit_client_secret:
            raise ValueError("Reddit credentials (REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET) are required")
        
        # Database configuration
        self.database_path = os.getenv("DATABASE_PATH", "./data/bot.db")
        
        # Logging configuration
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        self.log_file = os.getenv("LOG_FILE", "./logs/bot.log")
        
        # Bot configuration
        self.check_interval_minutes = int(os.getenv("CHECK_INTERVAL_MINUTES", "5"))
        self.max_posts_per_check = int(os.getenv("MAX_POSTS_PER_CHECK", "10"))
        self.temp_files_dir = os.getenv("TEMP_FILES_DIR", "./temp")
        
        # Raspberry Pi optimizations
        self.raspberry_pi_mode = os.getenv("RASPBERRY_PI_MODE", "false").lower() == "true"
        self.video_timeout_seconds = int(os.getenv("VIDEO_TIMEOUT_SECONDS", "120" if self.raspberry_pi_mode else "60"))
        self.audio_timeout_seconds = int(os.getenv("AUDIO_TIMEOUT_SECONDS", "60" if self.raspberry_pi_mode else "30"))
        self.ffmpeg_threads = int(os.getenv("FFMPEG_THREADS", "2" if self.raspberry_pi_mode else "4"))
        
        # Ensure directories exist
        self._ensure_directories()
        
        # Load admin list
        self._admins = self._load_admins()
    
    def _ensure_directories(self):
        """Ensure required directories exist."""
        directories = [
            Path(self.database_path).parent,
            Path(self.log_file).parent,
            Path(self.temp_files_dir)
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    def _load_admins(self) -> Set[str]:
        """Load admin list from admins.txt file."""
        admins = set()
        admins_file = Path("admins.txt")
        
        if admins_file.exists():
            with open(admins_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        admins.add(line)
        
        return admins
    
    @property
    def admins(self) -> Set[str]:
        """Get the set of admin user IDs/usernames."""
        return self._admins
    
    def is_admin(self, user_id: int, username: Optional[str] = None) -> bool:
        """Check if a user is an admin."""
        user_id_str = str(user_id)
        
        # Check direct user ID match
        if user_id_str in self._admins:
            return True
        
        # Check username match (with @ prefix)
        if username and f"@{username}" in self._admins:
            return True
        
        return False
    
    def reload_admins(self):
        """Reload the admin list from file."""
        self._admins = self._load_admins()
