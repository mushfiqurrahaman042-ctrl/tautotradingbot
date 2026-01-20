from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# Configuration settings
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///trading_bot.db")
WEBHOOK_PASSPHRASE = os.getenv("WEBHOOK_PASSPHRASE")

# Exchange configuration
SUPPORTED_EXCHANGES = ["binance", "bybit"]

# Trading parameters
POSITION_SIZE_DEFAULT = 0.001  # Default position size
PARTIAL_TP_PERCENTAGE = 0.20      # 20% for partial take profit

# Environment
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")