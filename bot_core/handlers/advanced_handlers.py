import logging
import re
import zoneinfo
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

# --- Local Imports ---
from micha_live_summary import (
    get_latest_summary, 
    get_latest_live_video_tuples, 
    gemini_generate_content, 
    get_transcript_for_video
)
from bot_core.utils.helpers import markdown_to_html, extract_video_id

logger = logging.getLogger(__name__)

# --- State Management for this Module ---
# Using user_data to track conversation state within the advanced features
AWAITING_VIDEO_ID_FOR_SUMMARY = 'awaiting_video_id_for_summary'
AWAITING_VIDEO_ID_FOR_GEMINI = 'awaiting_video_id_for_gemini'
GEMINI_CHAT_ACTIVE = 'gemini_chat_active'

# --- Summary Preparation ---

def prepere_summary(videoid=None):
    """Prepares the summary text from Micha's live stream for sending."""
    summary_text, published_dt = get_latest_summary(videoid)
    if not summary_text or not published_dt:
        return "Could not retrieve the summary at this time."

    israel_tz = zoneinfo.ZoneInfo("Asia/Jerusalem")
    published_local = published_dt.astimezone(israel_tz)
    date_str = published_local.strftime('%d/%m/%Y')
    time_str = published_local.strftime('%H:%M')
    
    html_summary = markdown_to_html(summary_text)
    
    # Add RTL mark for Hebrew text
    processed_lines = [f"\u200F{line}" for line in html_summary.splitlines() if line.strip()]
    html_summary_rtl = "\n".join(processed_lines)
    
    return (
        f'הנה סיכום הלייב של מיכה שהתקיים בתאריך {date_str} והסתיים בשעה {time_str}:\n\n'
        f'{html_summary_rtl}'
    )

# --- Main Callback Handlers ---

async def advanced_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the advanced features menu."""
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("📰 Latest Live Summary", callback_data='adv_latest_summary')],
        [InlineKeyboardButton("📹 Custom Live Summary", callback_data='adv_custom_summary')],
        [InlineKeyboardButton("🤖 Ask an AI", callback_data='adv_ai_chat')],
        [InlineKeyboardButton("🏠 Return", callback_data='main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text="🚀 Please choose an advanced option:", reply_markup=reply_markup)

async def advanced_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles button presses from the advanced menu."""
    query = update.callback_query
    await query.answer()
    choice = query.data

    if choice == 'adv_latest_summary':
        summary = prepere_summary()
        await query.edit_message_text(text=summary, parse_mode="HTML")
    elif choice == 'adv_custom_summary':
        context.user_data[AWAITING_VIDEO_ID_FOR_SUMMARY] = True
        await query.edit_message_text("Please provide the YouTube video ID or link for the custom summary.")
    elif choice == 'adv_ai_chat':
        await start_ai_chat_prompt(update, context)

async def start_ai_chat_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prompts the user to select a video for the AI chat."""
    video_tuples = get_latest_live_video_tuples(limit=4)
    keyboard = build_video_selection_keyboard(video_tuples)
    msg = update.callback_query.message
    await msg.edit_text("Which video would you like to discuss?", reply_markup=keyboard)

def build_video_selection_keyboard(video_tuples):
    """Builds an inline keyboard for video selection."""
    buttons = [
        [InlineKeyboardButton(title, callback_data=f"video_select:{video_id}")] 
        for video_id, title in video_tuples
    ]
    buttons.append([InlineKeyboardButton("Manual Input", callback_data="manual_video")])
    buttons.append([InlineKeyboardButton("🏠 Return", callback_data='main_menu')])
    return InlineKeyboardMarkup(buttons)

async def video_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the user's video selection for the AI chat."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("video_select:"):
        video_id = data.split(":")[1]
        await initiate_gemini_chat(update, context, video_id)
    elif data == "manual_video":
        context.user_data[AWAITING_VIDEO_ID_FOR_GEMINI] = True
        await query.edit_message_text("Please send me the YouTube video ID or link.")

async def unified_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles text input when expecting a video ID or a chat message."""
    user_text = update.message.text.strip()
    
    if context.user_data.get(AWAITING_VIDEO_ID_FOR_SUMMARY):
        video_id = extract_video_id(user_text)
        summary = prepere_summary(video_id)
        await update.message.reply_text(summary, parse_mode="HTML")
        context.user_data.pop(AWAITING_VIDEO_ID_FOR_SUMMARY, None)
        
    elif context.user_data.get(AWAITING_VIDEO_ID_FOR_GEMINI):
        video_id = extract_video_id(user_text)
        context.user_data.pop(AWAITING_VIDEO_ID_FOR_GEMINI, None)
        # Create a mock update object to pass to initiate_gemini_chat
        mock_query = type('obj', (object,), {'message': update.message})
        mock_update = type('obj', (object,), {'callback_query': mock_query})
        await initiate_gemini_chat(mock_update, context, video_id)

    elif context.user_data.get(GEMINI_CHAT_ACTIVE):
        await handle_gemini_chat(update, context)

async def initiate_gemini_chat(update: Update, context: ContextTypes.DEFAULT_TYPE, video_id: str):
    """Initiates a Gemini chat session with the transcript of the selected video."""
    query = update.callback_query
    await query.message.edit_text("Retrieving transcript, please wait...")
    
    transcript = get_transcript_for_video(video_id)
    if not transcript:
        await query.message.edit_text("Transcript not available for this video.")
        return
        
    context.user_data[GEMINI_CHAT_ACTIVE] = True
    sys_instruct = (
        "You are a knowledgeable stock market expert with a friendly tone, using emojis to enhance your responses. "
        "Your answers should be concise, focusing on the most critical points. "
        f"Use the following transcript as your primary source of information: {transcript}"
    )
    context.user_data['gemini_system_instruction'] = sys_instruct
    context.user_data['gemini_history'] = [] # Start with an empty history
    
    await query.message.edit_text("I have the video transcript. What would you like to know?")

async def handle_gemini_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles follow-up messages in a Gemini chat session."""
    user_text = update.message.text
    context.user_data['gemini_history'].append({'role': 'user', 'parts': [user_text]})
    
    system_instruction = context.user_data.get('gemini_system_instruction', "You are a helpful assistant.")
    response = gemini_generate_content(
        contents=context.user_data['gemini_history'],
        system_instruction=system_instruction
    )
    
    if response:
        context.user_data['gemini_history'].append({'role': 'model', 'parts': [response]})
        html_response = markdown_to_html(response)
        await update.message.reply_text(html_response, parse_mode="HTML")
    else:
        await update.message.reply_text("I'm sorry, I couldn't generate a response.")