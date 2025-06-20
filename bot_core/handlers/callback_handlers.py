import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from .command_handlers import list_alerts, handle_main_menu  # Import from sibling module

logger = logging.getLogger(__name__)

# --- Menu and General Callbacks ---

async def handle_list_alerts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback to list alerts, typically from a menu button."""
    query = update.callback_query
    await query.answer()
    await query.delete_message()
    await list_alerts(update, context) # Re-use the command handler logic

async def handle_help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays a simple help message."""
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("🏠 Back to Menu", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "ℹ️ *Help*\n\n"
        "• Use */newalert* to create a price, SMA, or custom line alert.\n"
        "• Use */listalerts* to view and manage your active alerts.\n"
        "• The *Advanced* menu contains experimental features.",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

# --- Alert-specific Callbacks ---

async def remove_alert_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Removes an alert from the database and the in-memory store."""
    query = update.callback_query
    await query.answer()
    
    alert_id_str = query.data.split("_")[1]
    alert_id = int(alert_id_str)
    user_id = query.effective_chat.id
    
    db_manager = context.bot_data['db_manager']
    user_alerts = context.bot_data['user_alerts']

    # 1. Remove from database
    db_manager.remove_alert(alert_id)

    # 2. Remove from in-memory store
    if user_id in user_alerts and user_alerts[user_id]:
        user_alerts[user_id] = [a for a in user_alerts[user_id] if a.get('id') != alert_id]
        logger.info(f"Removed alert {alert_id} from in-memory store for user {user_id}.")

    # 3. Update the message
    await query.edit_message_text("✅ Alert removed.", reply_markup=None)
    
    # After a short delay, show the main menu again
    await asyncio.sleep(2)
    await handle_main_menu(update, context)


async def alert_response_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the 'keep' response for a triggered price alert."""
    query = update.callback_query
    await query.answer()
    if query.data.startswith("keep_"):
        await query.delete_message()
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="ℹ️ Alert kept and will trigger again if conditions are met."
        )
