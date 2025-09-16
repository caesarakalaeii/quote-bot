"""Configuration management for the quote bot."""
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Configuration class for environment variables."""
    
    # Discord configuration
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
    GUILD_ID = os.getenv('GUILD_ID')  # Optional: specific guild for slash commands
    VOTE_CHANNEL_ID = os.getenv('VOTE_CHANNEL_ID')  # Optional: specific channel for quote voting
    
    # Database configuration
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = os.getenv('DB_PORT', '5432')
    DB_NAME = os.getenv('DB_NAME', 'quotebot')
    DB_USER = os.getenv('DB_USER', 'postgres')
    DB_PASSWORD = os.getenv('DB_PASSWORD')
    
    # Bot configuration
    VOTE_DURATION_DAYS = int(os.getenv('VOTE_DURATION_DAYS', '7'))
    MIN_VOTES_THRESHOLD = int(os.getenv('MIN_VOTES_THRESHOLD', '3'))
    
    @classmethod
    def validate(cls):
        """Validate that required environment variables are set."""
        required_vars = ['DISCORD_TOKEN', 'DB_PASSWORD']
        missing_vars = []
        
        for var in required_vars:
            if not getattr(cls, var):
                missing_vars.append(var)
        
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
        
        return True