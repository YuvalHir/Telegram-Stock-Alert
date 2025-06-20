import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
)

logger = logging.getLogger(__name__)

# Conversation states
(
    ALERT_TYPE, GET_TICKER, GET_PERIOD, GET_DIRECTION, GET_PRICE,
    GET_DATE1, GET_PRICE1_CHOICE, GET_DATE2, GET_PRICE2_CHOICE,
    GET_THRESHOLD, LIST_ALERTS
) = range(11)

# --- Entry and Exit Points ---

async def new_alert_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Starts the new alert creation conversation."""
    chat_id = update.effective_chat.id
    keyboard = [
        [InlineKeyboardButton("📈 SMA Alert", callback_data="sma")],
        [InlineKeyboardButton("💰 Price Alert", callback_data="price")],
        [InlineKeyboardButton("📊 Custom Line Alert", callback_data="custom_line")],
        [InlineKeyboardButton("❌ Cancel", callback_data='main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            "Please choose the type of alert:", reply_markup=reply_markup
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Please choose the type of alert:",
            reply_markup=reply_markup
        )
    return ALERT_TYPE

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancels the conversation and returns to the main menu."""
    from .command_handlers import handle_main_menu
    await handle_main_menu(update, context)
    return ConversationHandler.END

# --- State Handlers ---

async def alert_type_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the user's choice of alert type."""
    query = update.callback_query
    await query.answer()
    context.user_data['alert_type'] = query.data
    await query.edit_message_text("✍️ Please enter the stock ticker (e.g., AAPL):")
    return GET_TICKER

async def get_ticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gets the ticker and routes to the next appropriate state."""
    ticker = update.message.text.strip().upper()
    context.user_data['ticker'] = ticker
    alert_type = context.user_data['alert_type']
    
    if alert_type == "sma":
        await update.message.reply_text("✍️ Please enter the SMA period (e.g., 20):")
        return GET_PERIOD
    elif alert_type == "price":
        await update.message.reply_text("✍️ Please enter the target price:")
        return GET_PRICE
    elif alert_type == "custom_line":
        await update.message.reply_text("✍️ Please enter the first date (YYYY-MM-DD):")
        return GET_DATE1

async def get_period(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gets the SMA period."""
    try:
        context.user_data['period'] = int(update.message.text.strip())
        keyboard = [
            [InlineKeyboardButton("⬆️ Above", callback_data="above"),
             InlineKeyboardButton("⬇️ Below", callback_data="below")]
        ]
        await update.message.reply_text("Choose direction:", reply_markup=InlineKeyboardMarkup(keyboard))
        return GET_DIRECTION
    except ValueError:
        await update.message.reply_text("❌ Invalid input. Please enter a number.")
        return GET_PERIOD

async def get_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gets the target price for a price alert."""
    try:
        context.user_data['target_price'] = float(update.message.text.strip())
        keyboard = [
            [InlineKeyboardButton("⬆️ Above", callback_data="above"),
             InlineKeyboardButton("⬇️ Below", callback_data="below")]
        ]
        await update.message.reply_text("Choose direction:", reply_markup=InlineKeyboardMarkup(keyboard))
        return GET_DIRECTION
    except ValueError:
        await update.message.reply_text("❌ Invalid input. Please enter a numeric price.")
        return GET_PRICE

async def get_direction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gets the alert direction and saves the alert."""
    query = update.callback_query
    await query.answer()
    context.user_data['direction'] = query.data
    
    db_manager = context.bot_data['db_manager']
    user_alerts = context.bot_data['user_alerts']
    
    alert_type = context.user_data['alert_type']
    ticker = context.user_data['ticker']
    user_id = query.message.chat_id
    
    if alert_type == "sma":
        alert = {
            'type': 'sma', 'ticker': ticker,
            'period': context.user_data['period'],
            'direction': context.user_data['direction']
        }
        text = f"✅ SMA alert set for *{ticker}*!"
    elif alert_type == "price":
        alert = {
            'type': 'price', 'ticker': ticker,
            'target_price': context.user_data['target_price'],
            'direction': context.user_data['direction']
        }
        text = f"✅ Price alert set for *{ticker}*!"
    else: # Should not happen if coming from this flow
        return ConversationHandler.END

    alert_id = db_manager.save_alert(user_id, alert)
    alert['id'] = alert_id
    user_alerts.setdefault(user_id, []).append(alert)
    
    keyboard = [
        [InlineKeyboardButton("➕ Add Another", callback_data="new_alert")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END
    
# --- Custom Line Handlers ---

async def get_date(update: Update, context: ContextTypes.DEFAULT_TYPE, date_key: str, next_state: int):
    """Generic function to get a date and fetch High/Low prices."""
    try:
        date_obj = datetime.strptime(update.message.text.strip(), '%Y-%m-%d').date()
        context.user_data[date_key] = date_obj
        
        ticker = context.user_data['ticker']
        stock_service = context.bot_data['stock_service']
        
        data = stock_service.get_complete_daily_data(ticker, start_date=date_obj, end_date=date_obj)
        
        if data.empty:
            await update.message.reply_text(f"Could not find data for {ticker} on {date_obj}. Please enter a different date:")
            return context.user_data['current_date_state']

        high_price = data['High'].iloc[0]
        low_price = data['Low'].iloc[0]

        keyboard = [
            [InlineKeyboardButton(f"⬆️ High: {high_price:.2f}", callback_data=f"price_{high_price}")],
            [InlineKeyboardButton(f"⬇️ Low: {low_price:.2f}", callback_data=f"price_{low_price}")]
        ]
        await update.message.reply_text("Please choose the price for this date:", reply_markup=InlineKeyboardMarkup(keyboard))
        
        return next_state

    except ValueError:
        await update.message.reply_text("❌ Invalid date format. Please use YYYY-MM-DD:")
        return context.user_data['current_date_state']
    except Exception as e:
        logger.error(f"Error fetching price data in get_date: {e}")
        await update.message.reply_text("An error occurred. Please try a different date.")
        return context.user_data['current_date_state']

async def get_date1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['current_date_state'] = GET_DATE1
    return await get_date(update, context, 'date1', GET_PRICE1_CHOICE)

async def get_price1_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    price1 = float(query.data.split('_')[1])
    context.user_data['price1'] = price1
    
    await query.edit_message_text("✍️ Please enter the second date (YYYY-MM-DD):")
    return GET_DATE2

async def get_date2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['current_date_state'] = GET_DATE2
    return await get_date(update, context, 'date2', GET_PRICE2_CHOICE)

async def get_price2_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    price2 = float(query.data.split('_')[1])
    context.user_data['price2'] = price2
    
    await query.edit_message_text("✍️ Finally, please enter a threshold value (e.g., 0.5):")
    return GET_THRESHOLD

async def get_threshold(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gets the threshold and saves the custom line alert."""
    try:
        threshold = float(update.message.text.strip())
        context.user_data['threshold'] = threshold
        
        db_manager = context.bot_data['db_manager']
        user_alerts = context.bot_data['user_alerts']
        user_id = update.effective_chat.id
        
        alert = {
            'type': 'custom_line',
            'ticker': context.user_data.get('ticker'),
            'date1': context.user_data.get('date1'),
            'price1': context.user_data.get('price1'),
            'date2': context.user_data.get('date2'),
            'price2': context.user_data.get('price2'),
            'threshold': threshold
        }
        
        alert_id = db_manager.save_alert(user_id, alert)
        alert['id'] = alert_id
        user_alerts.setdefault(user_id, []).append(alert)
        
        text = (
            f"✅ Custom Line alert set for *{context.user_data.get('ticker')}* "
            f"from {alert['date1']} to {alert['date2']} with threshold ±{threshold}!"
        )
        keyboard = [
            [InlineKeyboardButton("➕ Add Another", callback_data="new_alert")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        return ConversationHandler.END

    except ValueError:
        await update.message.reply_text("❌ Invalid input. Please enter a numeric threshold.")
        return GET_THRESHOLD

# Function to build and return the ConversationHandler
def get_conversation_handler():
    """Builds and returns the full alert creation ConversationHandler."""
    return ConversationHandler(
        entry_points=[
            CommandHandler("newalert", new_alert_entry, filters=filters.ChatType.PRIVATE),
            CallbackQueryHandler(new_alert_entry, pattern="^new_alert$"),
        ],
        states={
            ALERT_TYPE: [CallbackQueryHandler(alert_type_choice, pattern="^(sma|price|custom_line)$")],
            GET_TICKER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_ticker)],
            GET_PERIOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_period)],
            GET_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_price)],
            GET_DIRECTION: [CallbackQueryHandler(get_direction, pattern="^(above|below)$")],
            GET_DATE1: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_date1)],
            GET_PRICE1_CHOICE: [CallbackQueryHandler(get_price1_choice, pattern=r"^price_")],
            GET_DATE2: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_date2)],
            GET_PRICE2_CHOICE: [CallbackQueryHandler(get_price2_choice, pattern=r"^price_")],
            GET_THRESHOLD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_threshold)],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_conversation, pattern="^main_menu$"),
            CommandHandler("cancel", cancel_conversation),
        ],
        per_message=False,
        per_user=True,
        map_to_parent={
            ConversationHandler.END: ConversationHandler.END
        }
    )