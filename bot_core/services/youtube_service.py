import os
import datetime
import zoneinfo
import logging
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from xml.etree.ElementTree import ParseError

from bot_core import config

logger = logging.getLogger(__name__)

class YouTubeService:
    def __init__(self, api_key=None, channel_id=None):
        """Initializes the YouTube service."""
        self.api_key = api_key or config.YOUTUBE_API_KEY
        self.channel_id = channel_id or config.YOUTUBE_CHANNEL_ID
        self.youtube = build("youtube", "v3", developerKey=self.api_key)
        self.ny_tz = zoneinfo.ZoneInfo("America/New_York")
        
        # Calculate the decision time for 'today' vs 'yesterday' video search
        israel_decision_dt = datetime.datetime.combine(
            datetime.date.min, 
            datetime.time(hour=16, minute=30),
            tzinfo=zoneinfo.ZoneInfo("Asia/Jerusalem")
        )
        self.ny_target_day_decision_time = israel_decision_dt.astimezone(self.ny_tz).time()

        # Define session times in New York Time
        self.ny_morning_live_start = datetime.time(hour=8, minute=30)
        self.ny_morning_live_end = datetime.time(hour=10, minute=30)
        self.ny_afternoon_live_start = datetime.time(hour=15, minute=0)
        self.ny_afternoon_live_end = datetime.time(hour=17, minute=0)

    def _get_target_date_range_utc(self):
        """Determines the target date range in UTC based on New York time."""
        now_ny = datetime.datetime.now(self.ny_tz)
        
        if now_ny.time() >= self.ny_target_day_decision_time:
            target_date = now_ny.date()
        else:
            target_date = now_ny.date() - datetime.timedelta(days=1)
            
        start_target_day_ny = datetime.datetime.combine(target_date, datetime.time.min, tzinfo=self.ny_tz)
        end_target_day_ny = datetime.datetime.combine(target_date, datetime.time.max, tzinfo=self.ny_tz)
        
        start_utc = start_target_day_ny.astimezone(datetime.timezone.utc)
        end_utc = end_target_day_ny.astimezone(datetime.timezone.utc)
        
        return start_utc.isoformat().replace('+00:00', 'Z'), end_utc.isoformat().replace('+00:00', 'Z')

    def fetch_live_videos_for_day(self):
        """Retrieves and filters videos from the channel for the target day's sessions."""
        published_after, published_before = self._get_target_date_range_utc()

        search_request = self.youtube.search().list(
            part="id,snippet",
            channelId=self.channel_id,
            publishedAfter=published_after,
            publishedBefore=published_before,
            order="date",
            type="video",
            eventType="completed",
            maxResults=10
        )
        search_response = search_request.execute()

        if not search_response.get("items"):
            logger.info("No videos found for the target date.")
            return []

        video_ids = [item["id"]["videoId"] for item in search_response["items"]]
        videos_request = self.youtube.videos().list(
            part="snippet,liveStreamingDetails",
            id=",".join(video_ids)
        )
        videos_response = videos_request.execute()
        
        morning_videos, afternoon_videos = [], []
        for item in videos_response.get("items", []):
            start_time_str = (item.get("liveStreamingDetails", {}).get("actualStartTime") or 
                              item.get("liveStreamingDetails", {}).get("scheduledStartTime") or 
                              item["snippet"]["publishedAt"])

            if not start_time_str:
                continue

            try:
                published_dt_utc = datetime.datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
            except ValueError:
                logger.warning(f"Could not parse timestamp for video {item['id']}.")
                continue

            published_dt_ny = published_dt_utc.astimezone(self.ny_tz)
            video_time_ny = published_dt_ny.time()

            if self.ny_morning_live_start <= video_time_ny < self.ny_morning_live_end:
                morning_videos.append(item)
            elif self.ny_afternoon_live_start <= video_time_ny < self.ny_afternoon_live_end:
                afternoon_videos.append(item)
        
        return morning_videos + afternoon_videos

    def get_latest_live_video_tuples(self, limit: int = 4):
        """Returns a list of tuples (id, title) for the latest videos."""
        video_items = self.fetch_live_videos_for_day()
        sorted_videos = sorted(video_items, key=lambda x: x["snippet"]["publishedAt"], reverse=True)
        
        return [
            (item["id"], item["snippet"]["title"]) 
            for item in sorted_videos[:limit]
        ]

    def fetch_transcript(self, video_id: str):
        """Retrieves the transcript text for a given video ID."""
        try:
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['iw', 'en'])
            return " ".join(segment["text"] for segment in transcript_list)
        except (TranscriptsDisabled, NoTranscriptFound) as e:
            logger.warning(f"Transcript not available for video {video_id}: {e}")
            return None
        except ParseError as e:
            logger.error(f"Failed to parse transcript XML for video {video_id}: {e}")
            return None
            
    def get_video_details(self, video_id: str):
        """Retrieves details for a specific video ID."""
        try:
            request = self.youtube.videos().list(part="snippet", id=video_id)
            response = request.execute()
            if response.get("items"):
                return response["items"][0]
            return None
        except Exception as e:
            logger.error(f"Failed to retrieve details for video {video_id}: {e}")
            return None