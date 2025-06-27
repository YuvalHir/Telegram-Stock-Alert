import asyncio
import logging
from datetime import datetime, timedelta
from io import BytesIO

import pandas as pd
from plotly import graph_objects as go
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from bot_core import config
from bot_core.services.fear_greed_service import get_fear_greed_index_api
from bot_core.utils.market_data_cache import market_cache

logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Greets the user and clears any previous conversation data."""
    context.user_data.clear()
    context.chat_data.clear()
    await update.message.reply_text("👋 Welcome to the Stock Alert Bot! Use /newalert to add a new alert or /menu to go to the main menu.")

async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the main menu with market info and primary action buttons."""
    context.user_data.clear()
    chat_id = update.effective_chat.id
    
    # Access the stock_service from bot_data
    stock_service = context.bot_data['stock_service']

    market_info = stock_service.get_multiple_market_info(config.MARKET_SYMBOLS)

    # --- Fear & Greed Index Integration ---
    fear_greed_data = market_cache.get('fear_greed_index')
    if fear_greed_data is None:
        logger.info("Fetching new Fear & Greed Index...")
        try:
            # get_fear_greed_index returns (category, value_str)
            category, value_str = get_fear_greed_index_api()
            fear_greed_data = f"Fear & Greed Index: {category} ({value_str})"
            market_cache.set('fear_greed_index', fear_greed_data)
            logger.info(f"Fetched and cached: {fear_greed_data}")
        except Exception as e:
            logger.error(f"Failed to fetch Fear & Greed Index: {e}")
            fear_greed_data = "Fear & Greed Index: N/A (Error fetching)"
    else:
        logger.info(f"Using cached Fear & Greed Index: {fear_greed_data}")
    # --- End Fear & Greed Index Integration ---

    keyboard = [
        [InlineKeyboardButton("➕ New Alert", callback_data="new_alert")],
        [InlineKeyboardButton("📋 List Alerts", callback_data="list_alerts")],
        [InlineKeyboardButton("❓ Help", callback_data="help")],
        [InlineKeyboardButton("🚀 Advanced", callback_data="advanced")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = (
        "🏠 *Main Menu*\n\n"
        "*Market Updates Today:*\n"
        f"📈 S&P 500: {market_info.get('^GSPC', 'N/A')}\n"
        f"📊 Nasdaq: {market_info.get('^IXIC', 'N/A')}\n"
        f"😮 VIX: {market_info.get('^VIX', 'N/A')}\n"
        f"₿ Bitcoin: {market_info.get('BTC-USD', 'N/A')}\n"
        f"📊 {fear_greed_data}\n\n" # Add Fear & Greed Index here
        "Select an option to proceed:"
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode="Markdown", reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            text, parse_mode="Markdown", reply_markup=reply_markup
        )
    return ConversationHandler.END

async def list_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays all active alerts for the user from the database."""
    chat_id = update.effective_chat.id
    db_manager = context.bot_data['db_manager']
    
    rows = db_manager.get_alerts_for_user(chat_id)

    if not rows:
        message = "😅 You have no active alerts."
        if update.callback_query:
            await context.bot.send_message(chat_id, message)
        else:
            await update.message.reply_text(message)
        return

    text = "🔔 <b>Active Alerts:</b>\n"
    keyboard_buttons = []
    for i, row in enumerate(rows, 1):
        alert_id, alert_type, ticker, period, target_price, direction, _, _, _, _, threshold = row
        
        if alert_type == "sma":
            alert_text = f"<b>{ticker}</b>: {direction} SMA({period})"
        elif alert_type == "price":
            alert_text = f"<b>{ticker}</b>: {direction} {target_price}"
        elif alert_type == "custom_line":
            alert_text = f"<b>{ticker}</b>: Custom Line (±{threshold})"
        else:
            alert_text = f"<b>{ticker}</b>: {alert_type}"
            
        text += f"<b>{i}</b>. {alert_text}\n"
        keyboard_buttons.append([InlineKeyboardButton(f"Remove alert {i}", callback_data=f"remove_{alert_id}")])

    keyboard_buttons.append([InlineKeyboardButton("📊 Send All Graphs", callback_data="send_all_graphs")])
    keyboard_buttons.append([InlineKeyboardButton("🏠 Back to Menu", callback_data="main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard_buttons)

    if update.callback_query:
        # If called from a callback, we might need to send a new message
        await context.bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)

async def send_all_graphs_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Acknowledges the 'send all graphs' request and initiates the process."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Please wait, graphs are being generated...")
    await send_all_graphs(update, context)
    return ConversationHandler.END

async def send_all_graphs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fetches all alerts for a user, generates, and sends a graph for each."""
    chat_id = update.effective_chat.id
    db_manager = context.bot_data['db_manager']
    stock_service = context.bot_data['stock_service']
    
    rows = db_manager.get_alerts_for_user(chat_id)
    if not rows:
        await context.bot.send_message(chat_id, "😅 You have no active alerts to graph.")
        return

    loop = asyncio.get_running_loop()
    for row in rows:
        # Create a dictionary from the tuple
        alert = dict(zip(['id', 'alert_type', 'ticker', 'period', 'target_price', 'direction', 'date1', 'price1', 'date2', 'price2', 'threshold'], row))
        ticker = alert['ticker']
        
        try:
            start_date_str = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
            end_date_str = datetime.now().strftime("%Y-%m-%d")

            df = await loop.run_in_executor(
                None, lambda: stock_service.get_complete_daily_data(ticker, start_date_str, end_date_str)
            )
            if df.empty:
                await context.bot.send_message(chat_id, f"No data for {ticker} to generate a graph.")
                continue

            fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
            fig.update_layout(title=f"{ticker} Graph", template='plotly_dark')
            
            # Simplified for now. Detailed trace logic will be added later.

            img_bytes = await loop.run_in_executor(None, lambda: fig.to_image(format="png"))
            await context.bot.send_photo(chat_id, photo=img_bytes, caption=f"Graph for your {ticker} alert.")
            
        except Exception as e:
            logger.error(f"Error generating graph for {ticker}: {e}")
            await context.bot.send_message(chat_id, f"Could not generate graph for {ticker}.")