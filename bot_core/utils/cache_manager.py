import os
import logging
from bot_core import config

logger = logging.getLogger(__name__)

class CacheManager:
    def __init__(self, transcript_dir=None, summary_dir=None):
        """Initializes the CacheManager and ensures directories exist."""
        self.transcript_dir = transcript_dir or config.TRANSCRIPTS_DIR
        self.summary_dir = summary_dir or config.SUMMARIES_DIR
        
        if not os.path.exists(self.transcript_dir):
            os.makedirs(self.transcript_dir)
            logger.info(f"Created transcript directory: {self.transcript_dir}")
            
        if not os.path.exists(self.summary_dir):
            os.makedirs(self.summary_dir)
            logger.info(f"Created summary directory: {self.summary_dir}")

    def get_transcript(self, video_id: str):
        """
        Retrieves a saved transcript if it exists.
        Returns the transcript text or None.
        """
        transcript_path = os.path.join(self.transcript_dir, f"{video_id}.txt")
        if os.path.exists(transcript_path):
            try:
                with open(transcript_path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                logger.error(f"Failed to read transcript {video_id}: {e}")
        return None

    def save_transcript(self, video_id: str, transcript_text: str):
        """Saves a transcript to a file."""
        transcript_path = os.path.join(self.transcript_dir, f"{video_id}.txt")
        try:
            with open(transcript_path, "w", encoding="utf-8") as f:
                f.write(transcript_text)
            logger.info(f"Saved transcript for video {video_id}.")
        except Exception as e:
            logger.error(f"Failed to save transcript for {video_id}: {e}")

    def get_summary(self, key: str):
        """
        Retrieves a saved summary by its key (e.g., video_id or date string).
        Returns the summary text or None.
        """
        summary_path = os.path.join(self.summary_dir, f"{key}.txt")
        if os.path.exists(summary_path):
            try:
                with open(summary_path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                logger.error(f"Failed to read summary {key}: {e}")
        return None

    def save_summary(self, key: str, summary_text: str):
        """Saves a summary to a file using a key."""
        summary_path = os.path.join(self.summary_dir, f"{key}.txt")
        try:
            with open(summary_path, "w", encoding="utf-8") as f:
                f.write(summary_text)
            logger.info(f"Saved summary for key {key}.")
        except Exception as e:
            logger.error(f"Failed to save summary for {key}: {e}")