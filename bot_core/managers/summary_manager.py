import logging
from datetime import date

from bot_core.services.ai_service import AIService
from bot_core.services.youtube_service import YouTubeService
from bot_core.services.twitter_service import TwitterService
from bot_core.utils.cache_manager import CacheManager
from bot_core.utils.helpers import market_is_open_today # Assuming this function is in helpers

logger = logging.getLogger(__name__)

class SummaryManager:
    def __init__(self, ai_service: AIService, youtube_service: YouTubeService, twitter_service: TwitterService, cache_manager: CacheManager):
        self.ai_service = ai_service
        self.youtube_service = youtube_service
        self.twitter_service = twitter_service
        self.cache_manager = cache_manager

    def get_youtube_summary(self, video_id: str = None):
        """
        Orchestrates the process of getting a YouTube video summary.
        If no video_id is provided, it fetches the latest suitable one.
        """
        if not video_id:
            # Find the latest video with a transcript if no ID is given
            video_items = self.youtube_service.fetch_live_videos_for_day()
            sorted_videos = sorted(video_items, key=lambda x: x["snippet"]["publishedAt"], reverse=True)
            
            for video in sorted_videos:
                video_id = video["id"]
                logger.info(f"Attempting to find transcript for latest video: {video_id}")
                transcript = self.get_transcript_for_video(video_id)
                if transcript:
                    break # Found a processable video
            else: # No video with a transcript was found
                return None, "No recent videos with transcripts found."
        
        # Check cache for existing summary
        summary = self.cache_manager.get_summary(video_id)
        if summary:
            logger.info(f"Retrieved summary for video {video_id} from cache.")
            video_details = self.youtube_service.get_video_details(video_id)
            return summary, video_details
            
        # Get transcript (which also uses caching)
        transcript = self.get_transcript_for_video(video_id)
        if not transcript:
            return None, f"Could not retrieve transcript for video {video_id}."

        # Generate new summary
        logger.info(f"Generating new summary for video {video_id}...")
        sys_instruct = """
אתה מקבל תמליל מלא של וידאו יומי ב-YouTube שמופעל בשידור חי בתחילת וסיום פעילות הבורסה. המטרה היא לסכם את התמליל עבור קהל המשקיעים, ולהפיק סיכום בהתאם להנחיות הבאות. **חשוב מאוד**: אין לכלול שום טקסט פתיחה או סיום – יש להתחיל ישירות עם רשימת הנקודות.

• 📰 **חדשות שוק היום:** לסכם את עיקרי החדשות שדווחו במהלך השידור, כולל עדכונים של חדשות בזמן אמת, במידה ונמסרו.
• 💹 **המלצות אנליסטים ועדכוני מחיר יעד:** לתמצת את המלצות האנליסטים וכל שינוי במחירי היעד.
• 📊 **מדדים מרכזיים:** לכלול מידע על תנועת המדדים הבולטים (S&P, Nasdaq, Russel, VIX) וכן את מיקום מדד הfear and greed.
• 🚀 **מניות עם פוטנציאל גידול:** להדגיש את המניות שהיוצר הביע לגביהן אופטימיות עקב הזדמנויות צמיחה, מצבים טכניים טובים או מחיר קנייה אטרקטיבי. שמות החברות ישמרו באנגלית.
• 👀 **מניות שמומלץ לעקוב:** לציין את המניות שהיוצר ממליץ לעקוב אחריהן, כאשר שמות החברות ישמרו באנגלית.
• ❌ **מניות מומלצות למכירה:** לפרט את המניות שהיוצר ממליץ למכור, כאשר שמות החברות ישמרו באנגלית. אם מידע זה אינו מופיע בתמליל, אל תכלול את הקטגוריה.
• ⚠️ **נקודות חשובות למשקיעים:** לכלול כל מידע חיוני או נקודות מרכזיות שהיוצר ציין והן חשובות למשקיעים.
• 📝 **סיכום קצר:** לספק סיכום קצר ותמציתי של כל התוכן.

**הוראות נוספות:**
1. כלול רק ציטוט אחד או שניים חשובים, אם הם מופיעים בתמליל.
2. ארגן את המידע לקטגוריות ברורות, לא לפי סדר הופעתו בשידור.
3. השתמש אך ורק בפורמט נקודות עם כותרות משנה ואימוג'ים להמחשה.
4. אין לכלול כל טקסט פתיחה או סיום – יש להציג אך ורק את הסיכום המפורט.
5. הסיכום חייב להיות בעברית בלבד, למעט שמות חברות שיפורטו באנגלית.
6. אם מידע עבור קטגוריה מסוימת אינו מופיע בתמליל, אל תכלול את הקטגוריה.
7. אורך הסיכום חייב להיות עד 4096 תווים, בהתחשב במגבלת ההעברה לטלגרם.

הפק את הסיכום בהתאם להנחיות הנ"ל, והתחל ישירות עם רשימת הנקודות ללא כל טקסט נוסף.
"""
        new_summary = self.ai_service.generate_content(
            prompt_parts=[transcript],
            system_instruction=sys_instruct,
            model_name="gemini-2.0-flash-exp"
        )
        
        if new_summary:
            self.cache_manager.save_summary(video_id, new_summary)
            logger.info(f"Successfully generated and cached summary for {video_id}.")
            video_details = self.youtube_service.get_video_details(video_id)
            return new_summary, video_details
        else:
            return None, "Failed to generate summary from AI service."

    def get_transcript_for_video(self, video_id: str):
        """Helper to get a transcript, using the cache first."""
        transcript = self.cache_manager.get_transcript(video_id)
        if transcript:
            logger.info(f"Retrieved transcript for {video_id} from cache.")
            return transcript
        
        logger.info(f"Fetching transcript for {video_id} from YouTube service.")
        transcript = self.youtube_service.fetch_transcript(video_id)
        if transcript:
            self.cache_manager.save_transcript(video_id, transcript)
        return transcript

    async def get_daily_twitter_recap(self, before_market: bool):
        """Orchestrates getting the daily Twitter recap."""
        today_str = date.today().strftime("%Y%m%d")
        recap_type = "PRE" if before_market else "AFT"
        cache_key = f"{recap_type}{today_str}"

        # Check cache first
        summary = self.cache_manager.get_summary(cache_key)
        if summary:
            logger.info(f"Retrieved {recap_type}-market summary from cache.")
            return summary

        if not market_is_open_today():
            logger.info("Market is not open today, skipping Twitter recap.")
            return "The market is closed today, so there is no recap."
            
        # Ensure the twitter service is logged in before fetching
        logged_in = await self.twitter_service.login()
        if not logged_in:
            return "Could not log into Twitter to fetch recap."

        market_experts = ['StockMKTNewz', 'wallstengine', 'AAIISentiment', 'markets']
        all_tweets = []
        for user in market_experts:
            tweets = await self.twitter_service.fetch_tweets(user, before_market=before_market)
            if tweets:
                all_tweets.extend(tweets)
        
        if not all_tweets:
            logger.warning("No tweets gathered for the daily recap.")
            return "Could not gather any tweets for the daily recap."
            
        # Generate summary
        prompt = "\n".join([f"{tweet[0]} (at {tweet[1]})" for tweet in all_tweets])
        
        today_str = date.today().strftime("%d/%m/%Y")
        if before_market:
            sys_instruct = f"""
התאריך היום {today_str}, ואתה הולך לעזור לי להתכונן לקראת יום המסחר של היום.
אתה מנתח מידע משוק ההון ומספק סיכומים תמציתיים וברורים שמכינים את המשתמש לקראת יום המסחר. המשתמש ישלח לך רשימה של ציוצים מטוויטר, ואתה תייצר סיכום של החדשות העיקריות מתוך הציוצים.
**הנחיות:**
* **מטרה:** הסיכום נועד להכין את המשתמש ליום המסחר הקרוב.
* **מבנה:** הסיכום יחולק לנושאים מרכזיים, לכל נושא תהיה כותרת משנה ברורה, והשתמש בנקודות (בולטים).
* **סגנון וטון:** מקצועי אך קליל, תמציתי וברור. התמקד בחדשות המשמעותיות. השתמש בעברית, אך שמות חברות באנגלית.
* **הגבלות:** לא יותר משלוש פסקאות.
* **עיבוד מידע:** התייחס לתאריכי הציוצים. התייחס לRT כציוץ רגיל. הוסף אמוג'ים רלוונטים.
"""
        else:
            sys_instruct = f"""
התאריך היום {today_str}, ואתה הולך לעזור לי לסכם את יום המסחר שהסתיים.
אתה מנתח מידע משוק ההון ומספק סיכומים תמציתיים וברורים. המשתמש ישלח לך רשימה של ציוצים מטוויטר, ואתה תייצר סיכום של החדשות העיקריות מתוכם, תוך התמקדות בחדשות שהתקבלו במהלך יום המסחר.
**הנחיות:**
* **מטרה:** סיכום יום המסחר שהסתיים.
* **מבנה:** חלוקה לנושאים עם כותרות משנה ברורות ונקודות (בולטים).
* **סגנון וטון:** מקצועי וקליל, תמציתי וברור, עם אמוג'ים. השתמש בעברית, אך שמות חברות באנגלית.
* **הגבלות:** לא יותר משלוש פסקאות.
* **מיקוד:** התמקד בביצועי השוק, חדשות ואירועים משמעותיים, וניתוח תמציתי של מגמות.
"""

        new_summary = self.ai_service.generate_content(
            prompt_parts=[prompt],
            system_instruction=sys_instruct,
            model_name="gemini-2.0-flash" # As per original dailyrecap.py
        )
        
        if new_summary:
            self.cache_manager.save_summary(cache_key, new_summary)
            logger.info(f"Successfully generated and cached {recap_type}-market summary.")
            return new_summary
        else:
            return "Failed to generate a recap from the gathered tweets."