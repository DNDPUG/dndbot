"""Configuration class for the DnD Bot."""

import os

from dotenv import load_dotenv

# Load environment variables from dndbot.env
load_dotenv(dotenv_path="dnd-bot-dev.env")


class Config:
    """Configuration class to manage environment variables for the bot."""

    def __init__(self):
        """Initialize the configuration by loading environment variables."""
        env = os.getenv("APP_ENV", "development")
        load_dotenv(f".env.{env}")
        self.BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
        self.CLIENT_ID = os.getenv("CLIENT_ID", "")
        self.CLIENT_SECRET = os.getenv("CLIENT_SECRET", "")
        self.GOOGLE_APPLICATION_CREDENTIALS = os.getenv(
            "GOOGLE_APPLICATION_CREDENTIALS",
            "",
        )
        self.GOOGLE_SHEET_NAME = os.getenv(
            "GOOGLE_SHEET_NAME",
            "",
        )
        self.GOOGLE_WORKSHEET = os.getenv("GOOGLE_WORKSHEET", "")
        self.OAUTH_URL = os.getenv("OAUTH_URL", "")
        self.CHARACTER_URL = os.getenv("CHARACTER_URL", "")
        self.MYTHIC_PROFILE_URL = os.getenv("MYTHIC_PROFILE_URL", "")
        self.CHARACTER_URL = os.getenv("CHARACTER_URL", "")
        self.MYTHIC_PROFILE_URL = os.getenv("MYTHIC_PROFILE_URL", "")
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


config = Config()
