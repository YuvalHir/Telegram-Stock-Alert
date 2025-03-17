import asyncio
import os
from twikit import Client
from datetime import datetime, timedelta, timezone, date
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.types import Tool, GoogleSearch
import pandas_market_calendars as mcal

load_dotenv(dotenv_path='varribles.env')  # Loads variables from the .env file

USERNAME = os.getenv("x_username")
EMAIL = os.getenv("x_email")
PASSWORD = os.getenv("x_password")
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
SUMMARIES_DIR = "summaries"

google_search_tool = Tool(
    google_search = GoogleSearch()
)

if not os.path.exists(SUMMARIES_DIR):
    os.makedirs(SUMMARIES_DIR)

# Initialize client
xclient = Client('en-US')

today = date.today()

def is_market_open_today(market_name="NYSE"):
    today = datetime.now(timezone.utc).date()
    market = mcal.get_calendar(market_name)
    schedule = market.schedule(start_date=today, end_date=today)
    return not schedule.empty # True if schedule exists, False otherwise

def is_before_market_close(date_string):
    try:
        date_object = datetime.strptime(date_string, "%a %b %d %H:%M:%S %z %Y")
        now_utc = datetime.now(timezone.utc)
        yesterday_2100_utc = datetime(now_utc.year, now_utc.month, now_utc.day, 21, 0, 0, tzinfo=timezone.utc) - timedelta(days=1)
        return date_object < yesterday_2100_utc

    except ValueError as e:
        print(f"Error parsing date: {e}")
        return False
    
def is_after_market_open(date_string):
    try:
        date_object = datetime.strptime(date_string, "%a %b %d %H:%M:%S %z %Y")
        now_utc = datetime.now(timezone.utc)
        today_1430_utc = datetime(now_utc.year, now_utc.month, now_utc.day, 14, 30, 0, tzinfo=timezone.utc)
        return date_object < today_1430_utc

    except ValueError as e:
        print(f"Error parsing date: {e}")
        return False
    
async def gettweets(username,before):
    USER_SCREEN_NAME = username
    user = await xclient.get_user_by_screen_name(USER_SCREEN_NAME)
    user_tweets = await user.get_tweets('Tweets')
    cur_tweets = []
    for tweet in user_tweets:
        cur_tweets.append(tuple([tweet.text, tweet.created_at]))
    if before:
        print("Gathering tweets from yesterday untill before market open")
        while not (is_before_market_close(user_tweets[len(user_tweets)-1].created_at)):
            user_tweets = await user_tweets.next()
            for tweet in user_tweets:
                cur_tweets.append(tuple([tweet.text, tweet.created_at]))
        for i in range(len(cur_tweets)-1,0,-1):
            date = cur_tweets[i][1]
            if is_before_market_close(date):
                del cur_tweets[i]
            else:
                break
    else:
        print("Gathering tweets after market open untill now")
        while not (is_after_market_open(user_tweets[len(user_tweets)-1].created_at)):
            user_tweets = await user_tweets.next()
            for tweet in user_tweets:
                cur_tweets.append(tuple([tweet.text, tweet.created_at]))
        for i in range(len(cur_tweets)-1,0,-1):
            date = cur_tweets[i][1]
            if not is_after_market_open(date):
                del cur_tweets[i]
            else:
                break
    return(cur_tweets)

def gemini_recap(prompt: str, system_instruction: str) -> str:
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            ),
        contents=prompt
    )
    return response.text

async def getreadyfortoday(info,before):
    today = date.today().strftime("%Y%m%d")
    if before:
        sys_ins = f"""
        התאריך היום {today}, ואתה הולך לעזור לי להתכונן לקראת יום המסחר של היום.
        אתה מנתח מידע משוק ההון ומספק סיכומים תמציתיים וברורים שמכינים את המשתמש לקראת יום המסחר. המשתמש ישלח לך רשימה של ציוצים מטוויטר, ואתה תייצר סיכום של החדשות העיקריות מתוך הציוצים.

        **הנחיות:**

        * **מטרה:** הסיכום נועד להכין את המשתמש ליום המסחר הקרוב.
        * **מבנה:**
            * הסיכום יחולק לנושאים מרכזיים כמו "חדשות", "דיווחים", ונושאים רלוונטיים אחרים שעולים מן הציוצים.
            * לכל נושא תהיה כותרת משנה ברורה.
            * השתמש בנקודות (בולטים) כדי להציג את הנקודות העיקריות בכל נושא.
        * **סגנון וטון:**
            * הסיכום יהיה מקצועי אך קליל ונוח לקריאה, כמו הודעת WhatsApp.
            * השתמש בשפה תמציתית וברורה, והימנע מפירוט יתר.
            * התמקד בחדשות המשמעותיות ביותר, וציין בקצרה או דלג על מידע שולי.
            * הסיכום צריך להיות בעברית, אך מומלץ לרשום שמות חברות או שמות של אנשים באנגלית אם זה ישפר את ההבנה
        * **הגבלות:**
            * הסיכום לא יעלה על שלוש פסקאות.
            * התמקד בחדשות חשובות ומשמעותיות, חדשות שוליות שאינן משמעותיות ניתן לדלג עליהן או לכתוב עליהן בקצרה.
        * **עיבוד מידע:**
            * התייחס לתאריכי הציוצים כדי להבחין בין חדשות מאתמול וחדשות מהיום.
            * התמקד בתוכן הציוצים.
            * התייחס לRT בדיוק כמו לכל ציוץ אחר, אם התוכן חדשותי ומשמעותי.
            * הוסף אמוגי'ם רלוונטים.
        * **פורמט:**
            * השתמש בנקודות בולטות על מנת להעביר את המסרים בצורה הטובה ביותר.
            * בכותרות משנה, תשתמש בטקסט מודגש.
        """
    else:
        sys_ins = f"""
        התאריך היום {today}, ואתה הולך לעזור לי לסכם את יום המסחר שהסתיים.
        אתה מנתח מידע משוק ההון ומספק סיכומים תמציתיים וברורים שמסכמים את יום המסחר. המשתמש ישלח לך רשימה של ציוצים מטוויטר, ואתה תייצר סיכום של החדשות העיקריות מתוך הציוצים, תוך התמקדות בחדשות שהתקבלו במהלך יום המסחר.

        **הנחיות:**

        * **מטרה:** הסיכום נועד לסכם את יום המסחר שהסתיים.
        * **מבנה:**
            * הסיכום יחולק לנושאים מרכזיים כמו "חדשות", "דיווחים", "כלכלה", "סיכום יומי", ונושאים רלוונטיים אחרים שעולים מן הציוצים.
            * לכל נושא תהיה כותרת משנה ברורה.
            * השתמש בנקודות (בולטים) כדי להציג את הנקודות העיקריות בכל נושא.
        * **סגנון וטון:**
            * הסיכום יהיה מקצועי אך קליל ונוח לקריאה, כמו הודעת WhatsApp.
            * השתמש בשפה תמציתית וברורה, והימנע מפירוט יתר.
            * השתמש באמוג'ים שיעזרו לבטא את מה שאתה חושב וגם יסגנונו יפה את ההודעה
            * הסיכום צריך להיות בעברית, אך מומלץ לרשום שמות חברות או שמות של אנשים באנגלית אם זה ישפר את ההבנה
            * התמקד בחדשות המשמעותיות ביותר שהתקבלו במהלך יום המסחר, וציין בקצרה או דלג על מידע שולי.
        * **הגבלות:**
            * הסיכום לא יעלה על שלוש פסקאות.
            * התמקד בחדשות חשובות ומשמעותיות שהתקבלו במהלך יום המסחר, חדשות שוליות שאינן משמעותיות ניתן לדלג עליהן או לכתוב עליהן בקצרה.
        * **עיבוד מידע:**
            * התייחס לתאריכי הציוצים כדי להבחין בין חדשות מאתמול וחדשות מהיום, תוך התמקדות בחדשות שהתקבלו במהלך יום המסחר.
            * התמקד בתוכן הציוצים.
            * התייחס לRT בדיוק כמו לכל ציוץ אחר, אם התוכן חדשותי ומשמעותי.
            * הוסף אמוג'ים רלוונטים.
        * **פורמט:**
            * השתמש בנקודות בולטות על מנת להעביר את המסרים בצורה הטובה ביותר.
            * בכותרות משנה, תשתמש בטקסט מודגש.
        * **מיקוד:**
            * התמקד בסיכום ביצועי השוק במהלך היום.
            * כלול חדשות ואירועים משמעותיים שהשפיעו על השוק במהלך היום.
            * ספק ניתוח תמציתי של מגמות ושינויים מרכזיים.
        """
    prompt = info
    
    result = gemini_recap(prompt,sys_ins)
    print(result)
    save_summary(before*"PRE"+(not before) * "AFT"+today, result)
    
    #result = gemini_recap(prompt, preperefortweet_ins)
    #print(result)
    """
    splitted_tweets = split_text_for_twitter(result)
    first_tweet = await xclient.create_tweet(splitted_tweets[0])
    last_tweet_id = first_tweet.id
    for i in range(1, len(splitted_tweets)):
        tweetreply = await xclient.get_tweet_by_id(last_tweet_id)
        reply_tweet = await tweetreply.reply(splitted_tweets[i])
        last_tweet_id = reply_tweet.id
        print(f"Reply tweet {i}/{len(splitted_tweets) - 1} created: {last_tweet_id}")
    """
    return result

def save_summary(date, summary_text):
    summary_path = os.path.join(SUMMARIES_DIR, f"{date}.txt")
    with open(summary_path, "w", encoding="utf-8") as file:
        file.write(summary_text)
    print(f"[DEBUG] Summary for video {date} saved to {summary_path}")

def split_text_for_twitter(text):
    max_length = 280
    tweets = []
    sentences = text.split('. ')  # פיצול הטקסט למשפטים
    current_tweet = ''
    tweet_count = 1

    for sentence in sentences:
        if len(current_tweet) + len(sentence) + 2 <= max_length:  # +2 לרווח ונקודה
            current_tweet += sentence + '. '
        else:
            tweets.append(current_tweet.strip())
            current_tweet = sentence + '. '

    tweets.append(current_tweet.strip())  # הוספת הציוץ האחרון

    formatted_tweets = []
    total_tweets = len(tweets)
    for i, tweet in enumerate(tweets):
        formatted_tweets.append(f"[{i + 1}/{total_tweets}] {tweet}")

    return formatted_tweets

def get_saved_summary(name):
    """
    Checks if a summary for the given video ID exists.
    If yes, returns the saved summary text; otherwise, returns None.
    """
    summary_path = os.path.join(SUMMARIES_DIR, f"{name}.txt")
    if os.path.exists(summary_path):
        with open(summary_path, "r", encoding="utf-8") as file:
            summary_text = file.read()
        print(f"[DEBUG] Found existing summary for video {name} at {summary_path}")
        return summary_text
    return None

async def recap():
    today = date.today().strftime("%Y%m%d")
    market_open = is_market_open_today()
    now_utc = datetime.now(timezone.utc)
    target_time = now_utc.replace(hour=14, minute=30, second=0, microsecond=0)
    before = now_utc < target_time
    print("searching for:", before*"PRE"+(not before)*"AFT"+today)
    if get_saved_summary(before*"PRE"+(not before)*"AFT"+today):
        #print(get_saved_summary(before*"PRE"+(not before) * "AFT"+today))
        return get_saved_summary(before*"PRE"+(not before) * "AFT"+today)
    await xclient.login(
        auth_info_1=USERNAME,
        auth_info_2=EMAIL,
        password=PASSWORD,
        cookies_file='cookies.json'
        enable_ui_metrics=True
    )
    #marketexperts = ['StockMKTNewz','wallstengine', 'AAIISentiment', 'markets']
    marketexperts = ['StockMKTNewz']#Checking issue related to scaping X.
    if market_open:
        if before:
            print("Before market open breif")
            info =[]
            for user in marketexperts:
                info.extend(await gettweets(user,True))
            print("Gathering tweets for today completed, here is what i got")
            print(info)
            response = await getreadyfortoday(info, True)
            print("Response from Gemini recived, here it is:")
            print(response)
            return response
        else:
            print("After market close breif.")
            info =[]
            for user in marketexperts:
                info.extend(await gettweets(user,False))
            print("Gathering tweets for today completed, here is what i got")
            print(info)
            response = await getreadyfortoday(info, False)
            print("Response from Gemini recived, here it is:")
            print(response)
            return response
    else:
        return None

#asyncio.run(recap())

##################################################################################
# Prompt for writing a post for twitter - works with gemini-2.0-flash-thinking-exp
##################################################################################

preperefortweet_ins = f"""
אתה מייצר סדרת ציוצים עבור טוויטר, שמכינים את המשתמש ליום המסחר.
שים לב שלטוויטר מגבלת 280 תווים לציוץ כולל מספור וכולל כותרות, אסור לחרוג מזה!
תכין מהציוצים סיכום מעניין שיכין את המשתמש ליום המסחר.
תכתוב פתיחה כמו "מוכנים ליום המסחר של..."
רצוי שהפסקה הראשונה תהיה הארוכה ביותר - בערך 280 תווים ותגרום למשתמש להמשיך ולקרוא את הבאות חשוב שגם תהיה מעוצבת עם אמוג'ים ונעימה לקריאה
תציין את התאריך של היום שהוא {today}
תשים לב בחדשות מה התאריך, חלק מהחדשות של אתמול וחלק של היום, אז צריך לשים לב לא להתבלבל.
**הנחיות:**

* **מטרה:** יצירת סדרת ציוצים לטוויטר.
* **מבנה:**
    * כל ציוץ עד 280 תווים.
    * כל ציוץ יתחיל במספר בסדרה: "[1/5]", "[2/5]" וכו'.
    * ציוצים יחולקו לנושאים: "חדשות", "דיווחים", "כלכלה".
    * כותרות משנה ברורות, ללא הדגשה.
    * נא לא לשים כוכביות ליד כותרות, זה לא נראה טוב.
    * נקודות (בולטים) לכל נושא.
* **הגבלות:**
    * כל ציוץ עד 280 תווים.
    * נושא ארוך יפוצל למספר ציוצים.
    * התמקד בחדשות משמעותיות.
* **פורמט:**
    * נקודות בולטות.
    * כל ציוץ ברור ותמציתי, עד 280 תווים.

לאחר שסיימת לכתוב את כל הטקסט, תעבור על כל פסקה ותספור אותה ותוודא שאין בה יותר מ280 תווים כולל הכותרת וכולל אמוג'ים והכל
אל תחסיר מידע חשוב, אלא במידת הצורך פצל את הנושא ל2 פסקאות או אפילו יותר, זה מבורך.
תשים לב שכל פסקה לא יותר מ280 תווים ותוודא את זה.
"""
