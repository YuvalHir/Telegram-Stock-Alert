import datetime
import os
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from google import genai
from google.genai import types
from google.genai.types import Tool, GoogleSearch
import zoneinfo  # Python 3.9+ for timezone support
from dotenv import load_dotenv
load_dotenv(dotenv_path='varribles.env')  # Loads variables from the .env file


# -----------------------
# Configuration Settings
# -----------------------

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
CHANNEL_ID = "UCSxjNbPriyBh9RNl_QNSAtw"
TRANSCRIPTS_DIR = "transcripts"
SUMMARIES_DIR = "summaries"

google_search_tool = Tool(
    google_search = GoogleSearch()
)


# Define threshold times (in local Israel time) for the lives to be considered finished.
FIRST_LIVE_END = datetime.time(hour=17, minute=30)
SECOND_LIVE_END = datetime.time(hour=23, minute=0)

# Define session ranges in Israel local time
AFTERNOON_SESSION_START = datetime.time(hour=16, minute=0)
AFTERNOON_SESSION_END   = datetime.time(hour=18, minute=0)
EVENING_SESSION_START = datetime.time(22, 0, 0)
EVENING_SESSION_END = datetime.time(0, 30, 0)


# Create transcripts directory if it does not exist.
if not os.path.exists(TRANSCRIPTS_DIR):
    os.makedirs(TRANSCRIPTS_DIR)
if not os.path.exists(SUMMARIES_DIR):
    os.makedirs(SUMMARIES_DIR)

# -----------------------
# Helper Functions
# -----------------------

def get_target_date_range():
    """
    Determines the target date range based on the current time in Israel.
    If current time is after the first live's finish time, use today's date.
    Otherwise, use yesterday's date.
    Returns ISO8601 strings for publishedAfter and publishedBefore in UTC.
    
    If the evening session spans midnight (i.e. EVENING_SESSION_START > EVENING_SESSION_END),
    the publishedBefore is extended to the next day at EVENING_SESSION_END.
    """
    israel_tz = zoneinfo.ZoneInfo("Asia/Jerusalem")
    now_israel = datetime.datetime.now(israel_tz)
    print(f"[DEBUG] Current time in Israel: {now_israel.strftime('%Y-%m-%d %H:%M:%S')}")

    if now_israel.time() >= FIRST_LIVE_END:
        target_date = now_israel.date()
        print("[DEBUG] Current time is after FIRST_LIVE_END, using today's date.")
    else:
        target_date = now_israel.date() - datetime.timedelta(days=1)
        print("[DEBUG] Current time is before FIRST_LIVE_END, using yesterday's date.")

    # publishedAfter is the start of the target date (local midnight)
    start_local = datetime.datetime.combine(target_date, datetime.time.min, tzinfo=israel_tz)

    # Determine publishedBefore: if evening session spans midnight, use target_date + 1 with EVENING_SESSION_END.
    if EVENING_SESSION_START > EVENING_SESSION_END:
        end_local = datetime.datetime.combine(target_date + datetime.timedelta(days=1), EVENING_SESSION_END, tzinfo=israel_tz)
    else:
        end_local = datetime.datetime.combine(target_date, datetime.time.max, tzinfo=israel_tz)
    
    # Convert the local times to UTC.
    start_utc = start_local.astimezone(datetime.timezone.utc)
    end_utc = end_local.astimezone(datetime.timezone.utc)
    
    published_after = start_utc.isoformat().replace('+00:00', 'Z')
    published_before = end_utc.isoformat().replace('+00:00', 'Z')
    
    print(f"[DEBUG] Target date: {target_date}")
    print(f"[DEBUG] Local start time: {start_local.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[DEBUG] Local end time: {end_local.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[DEBUG] UTC range: {published_after} to {published_before}")
    
    return published_after, published_before


def get_live_video_items():
    """
    Retrieves videos from Micha's channel published on the target day.
    Uses the Videos API to get extended details (including liveStreamingDetails)
    and uses the live's start time rather than the snippet's published time.
    Returns a list of video items that match either the afternoon or evening session.
    """
    israel_tz = zoneinfo.ZoneInfo("Asia/Jerusalem")
    youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
    published_after, published_before = get_target_date_range()

    # First, perform a search to get video IDs.
    search_request = youtube.search().list(
        part="id,snippet",
        channelId=CHANNEL_ID,
        publishedAfter=published_after,
        publishedBefore=published_before,
        order="date",
        type="video",
        eventType="completed",  # Only get lives, not regular videos.
        maxResults=10
    )
    search_response = search_request.execute()

    if not search_response.get("items"):
        print("[DEBUG] No videos found for the target date.")
        return []

    print("[DEBUG] Retrieved video items:")
    for item in search_response["items"]:
        print(f" - Video ID: {item['id']['videoId']}, Published at (UTC): {item['snippet']['publishedAt']}")

    # Extract video IDs from the search results.
    video_ids = [item["id"]["videoId"] for item in search_response["items"]]

    # Now, call the Videos API to get detailed info including liveStreamingDetails.
    videos_request = youtube.videos().list(
        part="snippet,liveStreamingDetails",
        id=",".join(video_ids)
    )
    videos_response = videos_request.execute()
    detailed_items = videos_response.get("items", [])

    # Print the session boundaries for debugging.
    print("[DEBUG] Afternoon session start:", AFTERNOON_SESSION_START, "end:", AFTERNOON_SESSION_END)
    print("[DEBUG] Evening session start:", EVENING_SESSION_START, "end:", EVENING_SESSION_END)

    afternoon_videos = []
    evening_videos = []
    for item in detailed_items:
        # Get live streaming details.
        live_details = item.get("liveStreamingDetails", {})
        # Use actualStartTime if available, otherwise scheduledStartTime, otherwise fall back to snippet.publishedAt.
        print("act",live_details.get("actualStartTime"),"sced", live_details.get("scheduledStartTime"), "pub", item["snippet"]["publishedAt"])
        start_time_str = (live_details.get("actualStartTime") or
                          live_details.get("scheduledStartTime") or
                          item["snippet"]["publishedAt"])

        try:
            published_dt_utc = datetime.datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
        except Exception as e:
            print(f"[DEBUG] Error parsing time {start_time_str}: {e}")
            continue

        published_dt_israel = published_dt_utc.astimezone(israel_tz)
        video_time = published_dt_israel.time()
        local_time_str = published_dt_israel.strftime('%Y-%m-%d %H:%M:%S')
        print(f"[DEBUG] Video {item['id']} local start time: {local_time_str} (time: {video_time})")

        # Filter based on Israel local time.
        if AFTERNOON_SESSION_START <= video_time < AFTERNOON_SESSION_END:
            print(f"[DEBUG] Video {item['id']} falls within the afternoon session.")
            afternoon_videos.append(item)
        else:
            # Check if evening session crosses midnight.
            if EVENING_SESSION_START <= EVENING_SESSION_END:
                # Evening session does not cross midnight.
                if EVENING_SESSION_START <= video_time <= EVENING_SESSION_END:
                    print(f"[DEBUG] Video {item['id']} falls within the evening session (non-midnight crossing).")
                    evening_videos.append(item)
                else:
                    print(f"[DEBUG] Video {item['id']} does NOT fall within the evening session (non-midnight crossing).")
            else:
                # Evening session spans midnight: valid if time >= EVENING_SESSION_START or <= EVENING_SESSION_END.
                if video_time >= EVENING_SESSION_START or video_time <= EVENING_SESSION_END:
                    print(f"[DEBUG] Video {item['id']} falls within the evening session (midnight crossing).")
                    evening_videos.append(item)
                else:
                    print(f"[DEBUG] Video {item['id']} does NOT fall within the evening session (midnight crossing).")

    combined_videos = afternoon_videos + evening_videos
    print(f"[DEBUG] Total videos after filtering: {len(combined_videos)}")
    return combined_videos



def get_latest_live_video_tuples(limit: int = 4):
    """
    Retrieves the latest live video items from Micha's channel and returns a list of tuples
    containing the video ID and title for up to `limit` videos.
    """
    video_items = get_live_video_items()  # Existing function call.
    
    # Assuming the items are ordered by publish date descending, select the first `limit` items.
    selected_items = video_items[:limit]
    
    video_tuples = []
    for item in selected_items:
        video_id = item["id"]
        video_title = item["snippet"]["title"]
        video_tuples.append((video_id, video_title))
    
    return video_tuples


def get_video_transcript(video_id):
    """
    Retrieve the transcript text for the given video using the YouTube Transcript API.
    """
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['iw', 'en']) #Adjust language if needed
        transcript_text = " ".join(segment["text"] for segment in transcript_list)
        return transcript_text
    except (TranscriptsDisabled, NoTranscriptFound) as e:
        print(f"[DEBUG] Transcript not available for video {video_id}: {e}")
        return None

def transcript_already_processed(video_id):
    """
    Check if a transcript for the given video ID has already been saved locally.
    """
    transcript_path = os.path.join(TRANSCRIPTS_DIR, f"{video_id}.txt")
    return os.path.exists(transcript_path)

def save_transcript(video_id, transcript_text):
    """
    Save transcript text to a file to avoid reprocessing.
    """
    transcript_path = os.path.join(TRANSCRIPTS_DIR, f"{video_id}.txt")
    with open(transcript_path, "w", encoding="utf-8") as file:
        file.write(transcript_text)
    print(f"[DEBUG] Transcript for video {video_id} saved to {transcript_path}")

def save_summary(video_id, summary_text):
    """
    Save the generated summary text to a file for record-keeping.
    """
    summary_path = os.path.join(SUMMARIES_DIR, f"{video_id}.txt")
    with open(summary_path, "w", encoding="utf-8") as file:
        file.write(summary_text)
    print(f"[DEBUG] Summary for video {video_id} saved to {summary_path}")

def get_saved_summary(video_id):
    """
    Checks if a summary for the given video ID exists.
    If yes, returns the saved summary text; otherwise, returns None.
    """
    print("searching for:", video_id)
    summary_path = os.path.join(SUMMARIES_DIR, f"{video_id}.txt")
    if os.path.exists(summary_path):
        with open(summary_path, "r", encoding="utf-8") as file:
            summary_text = file.read()
        print(f"[DEBUG] Found existing summary for video {video_id} at {summary_path}")
        return summary_text
    return None

# -----------------------
# Main Process 
# -----------------------
def process_video(video_id, transcript_text):
    """
    Process the video transcript by either retrieving a saved summary or generating a new one.
    Returns the summary text.
    """
    # Check if summary already exists
    summary_text = get_saved_summary(video_id)
    if summary_text:
        return summary_text
    
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

    prompt = transcript_text

    response = client.models.generate_content(
        model="gemini-2.0-pro-exp",
        config=types.GenerateContentConfig(
            system_instruction=sys_instruct),
        contents=prompt
    )

    summary_text = response.text
    #printing summaries disabled
    #print("[DEBUG] Generated Summary:")
    #print(summary_text)
    save_summary(video_id, summary_text)
    return summary_text

def get_transcript_for_video(video_id: str) -> str:
    """
    Retrieves the transcript for the given video ID.
    If the transcript is already processed, it reads it from the saved file.
    Otherwise, it downloads, saves, and returns the transcript.
    
    Returns:
        transcript_text (str): The transcript text, or an empty string if not available.
    """
    transcript_path = os.path.join(TRANSCRIPTS_DIR, f"{video_id}.txt")
    
    if transcript_already_processed(video_id):
        with open(transcript_path, "r", encoding="utf-8") as file:
            transcript_text = file.read()
        print(f"[DEBUG] Transcript for video {video_id} already processed. Using saved transcript.")
    else:
        transcript_text = get_video_transcript(video_id)
        if not transcript_text:
            print(f"[DEBUG] Could not retrieve transcript for video {video_id}.")
            return ""
        save_transcript(video_id, transcript_text)
    
    return transcript_text


def get_latest_summary(video_id=None):
    """
    If a video_id is provided, retrieve and process that video.
    Otherwise, process the latest live video from the channel.
    Returns a tuple of (summary_text, published_dt).
    """
    if video_id:
        print(f"[DEBUG] Processing specific video ID: {video_id}")
        # Check if transcript is already saved
        transcript_text = get_transcript_for_video(video_id)
        
        # Process transcript to generate summary
        summary_text = process_video(video_id, transcript_text)
        
        # Optionally, retrieve the published date for the specific video.
        youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
        request = youtube.videos().list(part="snippet", id=video_id)
        response = request.execute()
        published_dt = None
        if response.get("items"):
            published_at = response["items"][0]["snippet"]["publishedAt"]
            published_dt = datetime.datetime.strptime(published_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
        print(f"[DEBUG] Summary for video {video_id}:\n{summary_text}\n")
        return summary_text, published_dt
    
    else:
        # Default behavior: process the latest live video
        video_items = get_live_video_items()
        if not video_items:
            print("[DEBUG] No matching live videos found for the target date.")
            return

        # Sort videos by publishedAt (descending) and pick the latest one
        latest_video = sorted(
            video_items, 
            key=lambda x: x["snippet"]["publishedAt"], 
            reverse=True
        )[0]

        video_id = latest_video["id"]
        published_at = latest_video["snippet"]["publishedAt"]
        published_dt = datetime.datetime.strptime(published_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
        print(f"[DEBUG] Processing latest video ID: {video_id}, published at (UTC): {published_at}")

        transcript_text = get_transcript_for_video(video_id)
        
        summary_text = process_video(video_id, transcript_text)
        #print(f"[DEBUG] Summary for video {video_id}:\n{summary_text}\n")
        return summary_text, published_dt

def gemini_generate_content(prompt: str, system_instruction: str) -> str:
    """
    Generates content using Gemini with the given prompt and system instruction.
    This function wraps your Gemini API call.
    """
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=[google_search_tool],
            response_modalities=["TEXT"],
            ),
        contents=prompt
    )
    print("Grounding Information:")
    candidate = response.candidates[0]
    # Check if grounding metadata and search entry point are available
    if (candidate.grounding_metadata is not None and 
        candidate.grounding_metadata.search_entry_point is not None):
        grounding_info = candidate.grounding_metadata.search_entry_point.rendered_content
        print("Grounding Information:")
        print(grounding_info)
    else:
        print("No grounding information available for this response.")

    return response.text



if __name__ == "__main__":
    import sys
    # If a video ID is provided as a command line argument, process that video
    if len(sys.argv) > 1:
        video_id_arg = sys.argv[1]
        get_latest_summary(video_id=video_id_arg)
    else:
        # Otherwise, process the latest live video
        get_latest_summary()

