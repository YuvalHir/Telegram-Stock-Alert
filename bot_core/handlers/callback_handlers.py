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

    logger.info(f"Remove alert callback data: {query.data}")
    try:
        alert_id_str = query.data.split("_")[1]
        alert_id = int(alert_id_str)
        logger.info(f"Extracted alert_id: {alert_id}")
    except (IndexError, ValueError) as e:
        logger.error(f"Failed to extract alert_id from callback data '{query.data}': {e}")
        await query.edit_message_text("❌ Failed to remove alert. Invalid alert ID.", reply_markup=None)
        return

    user_id = query.effective_chat.id
    logger.info(f"User ID: {user_id}")

    db_manager = context.bot_data.get('db_manager')
    user_alerts = context.bot_data.get('user_alerts')

    if not db_manager:
        logger.error("db_manager not found in context.bot_data")
        await query.edit_message_text("❌ Failed to remove alert. Database manager not available.", reply_markup=None)
        return
    if not user_alerts:
        logger.error("user_alerts not found in context.bot_data")
        # Continue attempting database removal even if in-memory store is missing
        pass # Or handle specifically if necessary

    # 1. Remove from database
    try:
        db_manager.remove_alert(alert_id)
        logger.info(f"Removed alert {alert_id} from database.")
    except Exception as e:
        logger.error(f"Failed to remove alert {alert_id} from database: {e}")
        await query.edit_message_text("❌ Failed to remove alert from database.", reply_markup=None)
        return

    # 2. Remove from in-memory store
    if user_id in user_alerts and user_alerts[user_id]:
        initial_count = len(user_alerts[user_id])
        user_alerts[user_id] = [a for a in user_alerts[user_id] if a.get('id') != alert_id]
        if len(user_alerts[user_id]) < initial_count:
            logger.info(f"Removed alert {alert_id} from in-memory store for user {user_id}.")
        else:
            logger.warning(f"Alert {alert_id} not found in in-memory store for user {user_id}.")

    # 3. Update the message
    await query.edit_message_text("✅ Alert removed.", reply_markup=None)

    # After a short delay, show the main menu again
    # Ensure asyncio is imported
    import asyncio
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
