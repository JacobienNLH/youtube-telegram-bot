# config.py
import os

# Get bot token from environment variable (for deployment) or use default
BOT_TOKEN = os.getenv("BOT_TOKEN", "8181455842:AAHu8rmGxkevsSqEh-x1TVI3q0WBpWAZv3o")

# Get likes threshold from environment or use default
LIKES_THRESHOLD = int(os.getenv("LIKES_THRESHOLD", "10"))

# Additional deployment settings
DEBUG = os.getenv("DEBUG", "False").lower() == "true"
