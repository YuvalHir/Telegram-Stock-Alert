import logging
import zoneinfo
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot_core.utils.helpers import markdown_to_html, extract_video_id

logger = logging.getLogger(__name__)

# Conversation states for this module
AWAITING_VIDEO_ID_FOR_SUMMARY = 'awaiting_video_id_for_summary'
AWAITING_VIDEO_ID_FOR_GEMINI = 'awaiting_video_id_for_gemini'
GEMINI_CHAT_ACTIVE = 'gemini_chat_active'

def _prepare_text_for_display(text: str) -> str:
    """Converts markdown to HTML and adds RTL formatting for display."""
    if not text:
        return "No content to display."
    html_text = markdown_to_html(text)
    
    final_lines = []
    for line in html_text.splitlines():
        if line.strip():
            final_lines.append(f"\u200F{line}")
        else:
            final_lines.append(line)
            
    return "\n".join(final_lines)

def _prepare_youtube_summary_for_display(summary_text, video_details):
    """Formats the YouTube summary and video details for sending to the user."""
    if not summary_text or not video_details:
        return "Could not retrieve the YouTube summary at this time."

    published_dt_str = video_details['snippet']['publishedAt']
    published_dt_utc = datetime.fromisoformat(published_dt_str.replace('Z', '+00:00'))
    
    israel_tz = zoneinfo.ZoneInfo("Asia/Jerusalem")
    published_local = published_dt_utc.astimezone(israel_tz)
    date_str = published_local.strftime('%d/%m/%Y')
    time_str = published_local.strftime('%H:%M')
    
    formatted_summary = _prepare_text_for_display(summary_text)
    
    return (
        f'הנה סיכום הלייב של מיכה שהתקיים בתאריך {date_str} בשעה {time_str}:\n\n'
        f'{formatted_summary}'
    )

async def summary_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the main summary features menu."""
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("📰 Latest Live Summary", callback_data='sum_latest_summary')],
        [InlineKeyboardButton("📹 Custom Live Summary", callback_data='sum_custom_summary')],
        [InlineKeyboardButton("🤖 Ask AI about a Video", callback_data='sum_ai_chat')],
        [InlineKeyboardButton("🏠 Return to Main Menu", callback_data='main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text="📰 Summary & AI Menu:", reply_markup=reply_markup)

async def summary_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles button presses from the summary menu."""
    query = update.callback_query
    await query.answer()
    choice = query.data
    
    if choice == 'sum_latest_summary':
        summary_manager = context.bot_data['summary_manager']
        await query.edit_message_text("⏳ Fetching the latest YouTube summary, please wait...")
        summary_text, video_details = summary_manager.get_youtube_summary()
        display_text = _prepare_youtube_summary_for_display(summary_text, video_details)
        await query.edit_message_text(text=display_text, parse_mode="HTML")

    elif choice == 'sum_custom_summary':
        context.user_data[AWAITING_VIDEO_ID_FOR_SUMMARY] = True
        await query.edit_message_text("Please provide the YouTube video ID or link for the custom summary.")

    elif choice == 'sum_ai_chat':
        youtube_service = context.bot_data['youtube_service']
        video_tuples = youtube_service.get_latest_live_video_tuples(limit=4)
        
        buttons = [
            [InlineKeyboardButton(title, callback_data=f"video_select:{video_id}")] 
            for video_id, title in video_tuples
        ]
        buttons.append([InlineKeyboardButton("Manual Input", callback_data="manual_video")])
        buttons.append([InlineKeyboardButton("🏠 Return to Menu", callback_data='main_menu')])
        keyboard = InlineKeyboardMarkup(buttons)
        
        await query.edit_message_text("Which video would you like to discuss?", reply_markup=keyboard)

async def video_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the user's video selection for the AI chat."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("video_select:"):
        video_id = data.split(":")[1]
        await initiate_gemini_chat(query.message, context, video_id)
    elif data == "manual_video":
        context.user_data[AWAITING_VIDEO_ID_FOR_GEMINI] = True
        await query.edit_message_text("Please send me the YouTube video ID or link.")

async def summary_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles text input when expecting a video ID or a chat message."""
    user_text = update.message.text.strip()
    
    if context.user_data.get(AWAITING_VIDEO_ID_FOR_SUMMARY):
        summary_manager = context.bot_data['summary_manager']
        await update.message.reply_text(f"⏳ Processing video ID for summary: {user_text}, please wait...")
        video_id = extract_video_id(user_text)
        summary_text, video_details = summary_manager.get_youtube_summary(video_id=video_id)
        display_text = _prepare_youtube_summary_for_display(summary_text, video_details)
        await update.message.reply_text(display_text, parse_mode="HTML")
        context.user_data.pop(AWAITING_VIDEO_ID_FOR_SUMMARY, None)

    elif context.user_data.get(AWAITING_VIDEO_ID_FOR_GEMINI):
        video_id = extract_video_id(user_text)
        bot_message = await update.message.reply_text(f"⏳ Processing video ID for AI chat: {user_text}, please wait...")
        await initiate_gemini_chat(bot_message, context, video_id)
        context.user_data.pop(AWAITING_VIDEO_ID_FOR_GEMINI, None)
        
    elif context.user_data.get(GEMINI_CHAT_ACTIVE):
        await handle_gemini_chat(update, context)

async def initiate_gemini_chat(message, context: ContextTypes.DEFAULT_TYPE, video_id: str):
    """Initiates a Gemini chat session with the transcript of the selected video."""
    await message.edit_text("Retrieving transcript, please wait...")
    summary_manager = context.bot_data['summary_manager']
    
    transcript = summary_manager.get_transcript_for_video(video_id)
    if not transcript:
        await message.edit_text("Transcript not available for this video.")
        return
        
    context.user_data[GEMINI_CHAT_ACTIVE] = True
    sys_instruct = (
        "You are a knowledgeable stock market expert with a friendly tone, using emojis to enhance your responses. "
        "Your answers should be concise, focusing on the most critical points. "
        f"Use the following transcript as your primary source of information: {transcript}"
    )
    context.user_data['gemini_system_instruction'] = sys_instruct
    context.user_data['gemini_history'] = []
    
    await message.edit_text("I have the video transcript. What would you like to know?")

async def handle_gemini_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles follow-up messages in a Gemini chat session."""
    user_text = update.message.text
    context.user_data['gemini_history'].append({'role': 'user', 'parts': [user_text]})
    
    ai_service = context.bot_data['ai_service']
    system_instruction = context.user_data.get('gemini_system_instruction', "You are a helpful assistant.")
    
    contents = [part for item in context.user_data['gemini_history'] for part in item['parts']]
    
    response = ai_service.generate_content(
        prompt_parts=contents,
        system_instruction=system_instruction,
        model_name="gemini-2.0-flash-exp"
    )
    
    if response:
        context.user_data['gemini_history'].append({'role': 'model', 'parts': [response]})
        html_response = _prepare_text_for_display(response)
        await update.message.reply_text(html_response, parse_mode="HTML")
    else:
        await update.message.reply_text("I'm sorry, I couldn't generate a response.")