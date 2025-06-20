import re
from datetime import datetime, time, timedelta
from urllib.parse import urlparse, parse_qs
from pytz import timezone
import pandas_market_calendars as mcal

def market_is_open(market_name="NYSE"):
    """
    Checks if the specified market is currently open, accounting for holidays.
    """
    market = mcal.get_calendar(market_name)
    schedule = market.schedule(start_date=datetime.now().date(), end_date=datetime.now().date())

    if not schedule.empty:
        now_utc = datetime.now(timezone('UTC'))
        market_open = schedule.iloc[0]['market_open'].to_pydatetime()
        market_close = schedule.iloc[0]['market_close'].to_pydatetime()
        return market_open <= now_utc < market_close
    return False

def seconds_until_market_open():
    """Calculates the time in seconds until the next NYSE market opening."""
    tz = timezone('America/New_York')
    now = datetime.now(tz)
    market_open_time = time(9, 30)
    
    # Potential opening time for today
    today_open = now.replace(hour=9, minute=30, second=0, microsecond=0)

    # If it's before market open on a weekday
    if now < today_open and now.weekday() < 5:
        return (today_open - now).total_seconds()

    # If it's after market open or a weekend, find the next weekday
    days_to_add = 1
    if now.weekday() == 4:  # Friday
        days_to_add = 3
    elif now.weekday() == 5:  # Saturday
        days_to_add = 2
    
    next_open_day = now.date() + timedelta(days=days_to_add)
    next_open_datetime = datetime.combine(next_open_day, market_open_time, tzinfo=tz)
    
    return (next_open_datetime - now).total_seconds()

def markdown_to_html(md_text: str) -> str:
    """
    Converts a simple Markdown string with bolding and bullets to HTML.
    """
    # Convert bold text: **text** -> <b>text</b>
    html_text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', md_text)

    # Process each line: convert bullet marker "* " to a Unicode bullet "• "
    lines = html_text.splitlines()
    html_lines = []
    for line in lines:
        stripped_line = line.strip()
        if stripped_line.startswith("* "):
            content = stripped_line[2:].strip()
            # For bullet points, just add the bullet and the content
            html_lines.append("• " + content)
        elif stripped_line:
            # For non-bullet lines that have content, treat them as-is
            html_lines.append(stripped_line)
        else:
            # If the original line was empty or just whitespace, preserve it as a line break
            # This will create the space between paragraphs in the final output
            html_lines.append("")
            
    return "\n".join(html_lines)

def extract_video_id(video_input: str) -> str:
    """
    Extracts the YouTube video ID from various URL formats or returns the input
    if it's likely already an ID.
    """
    parsed = urlparse(video_input)
    
    # Standard `watch` URLs
    if parsed.netloc in ("www.youtube.com", "youtube.com") and 'v' in parse_qs(parsed.query):
        return parse_qs(parsed.query)['v'][0]
    
    # Shortened `youtu.be` URLs
    if parsed.netloc == "youtu.be":
        return parsed.path.lstrip('/')
        
    # `live` URLs
    if "/live/" in parsed.path:
        return parsed.path.split("/live/")[-1].split("?")[0]
        
    # Fallback regex for other possible formats
    match = re.search(r'(?:v=|/live/|embed/|shorts/)([\w-]{11})', video_input)
    if match:
        return match.group(1)

    # If no patterns match, assume the input is the ID itself
    return video_input.strip()
def market_is_open_today(market_name="NYSE"):
    """Checks if the market is scheduled to be open at any point today."""
    today = datetime.now(timezone('America/New_York')).date()
    market = mcal.get_calendar(market_name)
    schedule = market.schedule(start_date=today, end_date=today)
    return not schedule.empty