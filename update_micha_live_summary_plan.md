Plan to Update micha_live_summary.py for New York Time Live Sessions

Overall Goal: Update the script to identify "morning" (08:30-10:30 NYT) and "afternoon" (15:00-17:00 NYT) YouTube live sessions. This involves:

Changing time-based filtering to use New York Time (NYT).

Updating the logic that determines the target day for video search to be based on NYT.

Detailed Plan:

Add/Update Timezone and Session Constants (Configuration Section):

Ensure zoneinfo is imported: import zoneinfo

Define the New York timezone:

NEW_YORK_TZ = zoneinfo.ZoneInfo("America/New_York")


Remove or comment out old Israel-based session time constants:

AFTERNOON_SESSION_START, AFTERNOON_SESSION_END

EVENING_SESSION_START, EVENING_SESSION_END

Define new New York Time session boundaries:

# New York Time session definitions
NY_MORNING_LIVE_START = datetime.time(hour=8, minute=30)
NY_MORNING_LIVE_END = datetime.time(hour=10, minute=30)    # End is exclusive
NY_AFTERNOON_LIVE_START = datetime.time(hour=15, minute=0)
NY_AFTERNOON_LIVE_END = datetime.time(hour=17, minute=0)  # End is exclusive
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
Python
IGNORE_WHEN_COPYING_END

Calculate and define the New York equivalent of the old FIRST_LIVE_END (16:30 Israel Time) to be used for deciding the target day. Remove FIRST_LIVE_END and SECOND_LIVE_END.

# Decision time for "today" vs "yesterday" video search, based on NYT
# Equivalent to the old 16:30 Israel Time decision point.
_israel_decision_dt_temp = datetime.datetime.combine(datetime.date.min, # Arbitrary date
                                                  datetime.time(hour=16, minute=30), 
                                                  tzinfo=zoneinfo.ZoneInfo("Asia/Jerusalem"))
NY_TARGET_DAY_DECISION_TIME = _israel_decision_dt_temp.astimezone(NEW_YORK_TZ).time()
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
Python
IGNORE_WHEN_COPYING_END

Modify get_target_date_range() Function (approx. lines 49-91 of micha_live_summary.py):

Get current time in New York:

now_ny = datetime.datetime.now(NEW_YORK_TZ)
print(f"[DEBUG] Current time in New York: {now_ny.strftime('%Y-%m-%d %H:%M:%S %Z')}")
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
Python
IGNORE_WHEN_COPYING_END

Determine target_date based on now_ny.time() and NY_TARGET_DAY_DECISION_TIME:

if now_ny.time() >= NY_TARGET_DAY_DECISION_TIME:
    target_date = now_ny.date()
    print(f"[DEBUG] Current NY time ({now_ny.time()}) is on or after NY_TARGET_DAY_DECISION_TIME ({NY_TARGET_DAY_DECISION_TIME}), using today's date in NY: {target_date}")
else:
    target_date = now_ny.date() - datetime.timedelta(days=1)
    print(f"[DEBUG] Current NY time ({now_ny.time()}) is before NY_TARGET_DAY_DECISION_TIME ({NY_TARGET_DAY_DECISION_TIME}), using yesterday's date in NY: {target_date}")
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
Python
IGNORE_WHEN_COPYING_END

Define publishedAfter and publishedBefore based on the target_date in New York time, then convert to UTC:

# publishedAfter is the start of the target date in NY time
start_target_day_ny = datetime.datetime.combine(target_date, datetime.time.min, tzinfo=NEW_YORK_TZ)

# publishedBefore is the end of the target date in NY time
end_target_day_ny = datetime.datetime.combine(target_date, datetime.time.max, tzinfo=NEW_YORK_TZ)

start_utc = start_target_day_ny.astimezone(datetime.timezone.utc)
end_utc = end_target_day_ny.astimezone(datetime.timezone.utc)

published_after = start_utc.isoformat().replace('+00:00', 'Z')
published_before = end_utc.isoformat().replace('+00:00', 'Z')
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
Python
IGNORE_WHEN_COPYING_END

Update all debug print statements within this function to refer to New York time where appropriate.

Modify get_live_video_items() Function (approx. lines 140-184 of micha_live_summary.py):

Timezone Conversion:

Convert published_dt_utc to published_dt_new_york:

published_dt_new_york = published_dt_utc.astimezone(NEW_YORK_TZ)
video_time_ny = published_dt_new_york.time()
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
Python
IGNORE_WHEN_COPYING_END

Update Debug Logging:

Adjust print statements to reflect New York time.

Filtering Logic:

Initialize morning_videos_ny = [] and afternoon_videos_ny = [].

Implement new filtering logic:

if NY_MORNING_LIVE_START <= video_time_ny < NY_MORNING_LIVE_END:
    print(f"[DEBUG] Video {item['id']} ({item['snippet']['title']}) falls within the NY morning session.")
    morning_videos_ny.append(item)
elif NY_AFTERNOON_LIVE_START <= video_time_ny < NY_AFTERNOON_LIVE_END:
    print(f"[DEBUG] Video {item['id']} ({item['snippet']['title']}) falls within the NY afternoon session.")
    afternoon_videos_ny.append(item)
else:
    print(f"[DEBUG] Video {item['id']} ({item['snippet']['title']}) at NY time {video_time_ny} does NOT fall within any defined NY session.")
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
Python
IGNORE_WHEN_COPYING_END

Combine Filtered Videos:

combined_videos = morning_videos_ny + afternoon_videos_ny
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
Python
IGNORE_WHEN_COPYING_END

Mermaid Diagram for get_live_video_items:

graph TD
    A[Start get_live_video_items] --> B{Loop through video items};
    B --> C[Get video publish time UTC];
    C --> D_new[Convert UTC to New York Time];
    D_new --> E_new[Get New York .time() as video_time_ny];
    E_new --> F{Is video_time_ny in NY Morning Range? (NY_MORNING_LIVE_START <= video_time_ny < NY_MORNING_LIVE_END)};
    F -- Yes --> G[Add to morning_videos_ny];
    F -- No --> H{Is video_time_ny in NY Afternoon Range? (NY_AFTERNOON_LIVE_START <= video_time_ny < NY_AFTERNOON_LIVE_END)};
    H -- Yes --> I[Add to afternoon_videos_ny];
    H -- No --> J[Log as not in session];
    G --> K{End Loop?};
    I --> K;
    J --> K;
    K -- No --> B;
    K -- Yes --> L[Combine morning_videos_ny and afternoon_videos_ny];
    L --> M[Return combined_videos];
IGNORE_WHEN_COPYING_START
content_copy
download
Use code with caution.
Mermaid
IGNORE_WHEN_COPYING_END