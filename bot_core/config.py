import os
import zoneinfo
from datetime import time

# --- Core Settings ---
API_TOKEN = os.getenv("TELEGRAM_API_TOKEN")
DATABASE_PATH = "alerts.db"

# --- Market Data ---
# Symbols displayed in the main menu
MARKET_SYMBOLS = ["^GSPC", "^IXIC", "^VIX", "BTC-USD"]

# --- Job Scheduling (Times in America/New_York timezone) ---
NEW_YORK_TZ = zoneinfo.ZoneInfo("America/New_York")

# Time to send the pre-market summary from 'X'
X_SUMMARY_PRE_MARKET_TIME = time(9, 15, tzinfo=NEW_YORK_TZ)

# Time to send the end-of-day summary from Micha's live stream
SUMMARY_POST_CLOSE_TIME = time(17, 0, tzinfo=NEW_YORK_TZ)

# --- Service APIs & Credentials ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
YOUTUBE_CHANNEL_ID = "UCSxjNbPriyBh9RNl_QNSAtw"

# Twitter Credentials
X_USERNAME = os.getenv("x_username")
X_EMAIL = os.getenv("x_email")
X_PASSWORD = os.getenv("x_password")

# --- Caching & Directories ---
TRANSCRIPTS_DIR = "transcripts"
SUMMARIES_DIR = "summaries"