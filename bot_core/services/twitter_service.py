import asyncio
import logging
from datetime import datetime, timedelta, timezone, time, date
import zoneinfo
from twikit import Client

from bot_core import config

logger = logging.getLogger(__name__)

class TwitterService:
    def __init__(self):
        """Initializes the Twitter service."""
        self.xclient = Client('en-US')
        self.ny_tz = zoneinfo.ZoneInfo("America/New_York")
        self.ny_market_open_time = time(9, 30)
        self.ny_market_close_time = time(16, 0)
        self._is_logged_in = False

    async def login(self):
        """Logs into the Twitter client if not already logged in."""
        if self._is_logged_in:
            return True
        try:
            logger.info("Attempting to log into Twitter...")
            await self.xclient.login(
                auth_info_1=config.X_USERNAME,
                auth_info_2=config.X_EMAIL,
                password=config.X_PASSWORD,
                cookies_file='cookies.json',
                enable_ui_metrics=True
            )
            self._is_logged_in = True
            logger.info("Successfully logged into Twitter.")
            return True
        except Exception as e:
            logger.error(f"Failed to log into Twitter: {e}")
            self._is_logged_in = False
            return False

    def _is_before_market_close(self, date_string):
        """Checks if a tweet's date is before yesterday's NY market close."""
        try:
            date_object = datetime.strptime(date_string, "%a %b %d %H:%M:%S %z %Y")
            now_in_ny = datetime.now(self.ny_tz)
            yesterday_in_ny = now_in_ny - timedelta(days=1)
            threshold_dt_ny = datetime.combine(yesterday_in_ny.date(), self.ny_market_close_time, tzinfo=self.ny_tz)
            threshold_utc = threshold_dt_ny.astimezone(timezone.utc)
            return date_object < threshold_utc
        except ValueError:
            return False

    def _is_after_market_open(self, date_string):
        """Checks if a tweet's date is before today's NY market open."""
        try:
            date_object = datetime.strptime(date_string, "%a %b %d %H:%M:%S %z %Y")
            now_in_ny = datetime.now(self.ny_tz)
            threshold_dt_ny = datetime.combine(now_in_ny.date(), self.ny_market_open_time, tzinfo=self.ny_tz)
            threshold_utc = threshold_dt_ny.astimezone(timezone.utc)
            return date_object < threshold_utc
        except ValueError:
            return False

    async def fetch_tweets(self, username: str, before_market: bool):
        """
        Fetches tweets for a given user, filtered by market open/close times.
        Assumes login has already been attempted.
        """
        if not self._is_logged_in:
            logger.warning("Cannot fetch tweets, not logged into Twitter.")
            return []
            
        try:
            user = await self.xclient.get_user_by_screen_name(username)
            user_tweets = await user.get_tweets('Tweets')
        except Exception as e:
            logger.error(f"Failed to get user or initial tweets for {username}: {e}")
            return []

        all_tweets = [tweet for tweet in user_tweets]
        
        if before_market:
            stop_condition_check = self._is_before_market_close
        else:
            stop_condition_check = self._is_after_market_open
        
        try:
            if all_tweets and not stop_condition_check(all_tweets[-1].created_at):
                async for page in user_tweets:
                    all_tweets.extend(page)
                    if stop_condition_check(all_tweets[-1].created_at):
                        break
        except Exception as e:
            logger.error(f"Error paginating tweets for {username}: {e}")

        # Filter tweets based on the time window
        final_tweets = [
            (tweet.text, tweet.created_at) 
            for tweet in all_tweets 
            if not stop_condition_check(tweet.created_at)
        ]

        return final_tweets