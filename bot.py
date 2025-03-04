import os
import logging
from datetime import datetime, time, timedelta
import pandas as pd
import yfinance as yf
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from pytz import timezone
from plotly import graph_objects as go
import asyncio
from io import BytesIO
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
import sqlite3
import zoneinfo
from micha_live_summary import get_latest_summary

# Create a persistent connection (adjust the path as needed)
conn = sqlite3.connect('alerts.db', check_same_thread=False)
cursor = conn.cursor()
# Create the alerts table if it doesn't exist
cursor.execute('''
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        alert_type TEXT,
        ticker TEXT,
        period INTEGER,
        target_price REAL,
        direction TEXT,
        date1 TEXT,
        price1 REAL,
        date2 TEXT,
        price2 REAL,
        threshold REAL
    )
''')
conn.commit()


# Enable logging
logging.getLogger("yfinance").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# In-memory store for alerts (for production, use a proper database)
user_alerts = {}

# Conversation states
ALERT_TYPE, GET_TICKER, GET_PERIOD, GET_DIRECTION, GET_PRICE, GET_DATE1, GET_PRICE1_OVERRIDE, GET_DATE2, GET_PRICE2_OVERRIDE, GET_THRESHOLD, LIST_ALERTS = range(11)

# Helper: Check if market is open (NYSE hours example: 9:30am-4:00pm EST)
def market_is_open():
    tz = timezone('America/New_York')
    now = datetime.now(tz)
    # Check if today is Saturday (5) or Sunday (6)
    if now.weekday() >= 5:
        return False
    now_time = now.time()
    market_open = time(9, 30)
    market_close = time(16, 0)
    return market_open <= now_time <= market_close

def seconds_until_market_open():
    tz = timezone('America/New_York')
    now = datetime.now(tz)
    market_open_time = time(9, 30)
    # Create a datetime for today’s market open:
    today_open = datetime.combine(now.date(), market_open_time, tzinfo=tz)

    if now < today_open:
        # It's before market open today.
        return (today_open - now).total_seconds()
    else:
        # Otherwise, schedule for tomorrow's open.
        tomorrow = now.date() + timedelta(days=1)
        tomorrow_open = datetime.combine(tomorrow, market_open_time, tzinfo=tz)
        return (tomorrow_open - now).total_seconds()
    
from telegram.helpers import escape_markdown
import re

def markdown_to_html(md_text: str) -> str:
    """
    Converts a simple Markdown summary (with bullet points starting with "* " and bold text marked with **)
    into an HTML formatted string suitable for Telegram (using newlines instead of <br>).
    
    - Each line starting with "* " is treated as a bullet point.
    - Bold text (i.e. **text**) is converted to <b>text</b>.
    - Blank lines (i.e. double newlines) between bullets are preserved.
    """
    # Convert bold text: **text** -> <b>text</b>
    html_text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', md_text)

    # Process each line: convert bullet marker "* " to a Unicode bullet "• " 
    lines = html_text.splitlines()
    html_lines = []
    for line in lines:
        line = line.strip()
        if line.startswith("* "):
            content = line[2:].strip()
            html_lines.append("• " + content)
        else:
            html_lines.append(line)
    # Join the lines with newlines (two newlines between bullets for an empty line)
    return "\n\n".join(html_lines)

async def send_summary(context: ContextTypes.DEFAULT_TYPE):
    """
    Retrieves the latest summary along with its published datetime,
    converts it to HTML for nice bullet-point formatting, and sends it to users.
    """
    summary_text, published_dt = get_latest_summary()
    if summary_text is None or published_dt is None:
        print("[DEBUG] No summary available to send.")
        return

    # Convert published_dt to Israel time for display.
    israel_tz = zoneinfo.ZoneInfo("Asia/Jerusalem")
    published_local = published_dt.astimezone(israel_tz)
    date_str = published_local.strftime('%d/%m/%Y')
    time_str = published_local.strftime('%H:%M')

    # Convert the summary from Markdown to HTML.
    html_summary = markdown_to_html(summary_text)

    # Construct the HTML message.
    message = (
        f'הנה סיכום הלייב של מיכה שהתקיים בתאריך {date_str} והסתיים בשעה {time_str}:\n\n'
        f'{html_summary}'
    )

    # Retrieve user IDs from the alerts database.
    alerts = load_alerts()
    user_ids = alerts.keys()

    # Send the HTML formatted summary message to each user.
    for user_id in user_ids:
        await context.bot.send_message(
            chat_id=user_id,
            text=message,
            parse_mode="HTML"
        )
        print(f"[DEBUG] Sent summary to user {user_id}")



# Functions to compute alerts
def calculate_sma(ticker, period=20):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period=f"{period *3}d")
        closes = hist['Close'].tail(period)
        if len(closes) < period:
            logger.error(f"Not enough trading days to calculate SMA for {ticker}. Needed {period}, got {len(closes)}.")
            return None
        return closes.mean()
    except Exception as e:
        logger.error(f"Error calculating SMA for {ticker}: {e}")
        return None

def calculate_custom_line(date1, price1, date2, price2):
    if isinstance(date1, str):
        date1 = datetime.strptime(date1, '%Y-%m-%d').date()
    if isinstance(date2, str):
        date2 = datetime.strptime(date2, '%Y-%m-%d').date()
    ordinal1 = date1.toordinal()
    ordinal2 = date2.toordinal()
    today_ordinal = datetime.now().toordinal()
    slope = (price2 - price1) / (ordinal2 - ordinal1)
    return price1 + slope * (today_ordinal - ordinal1)

def save_alert(user_id, alert):
    cursor.execute('''
        INSERT INTO alerts (
            user_id, alert_type, ticker, period, target_price, direction,
            date1, price1, date2, price2, threshold
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        user_id,
        alert.get('type'),
        alert.get('ticker'),
        alert.get('period'),
        alert.get('target_price'),
        alert.get('direction'),
        str(alert.get('date1')) if alert.get('date1') else None,
        alert.get('price1'),
        str(alert.get('date2')) if alert.get('date2') else None,
        alert.get('price2'),
        alert.get('threshold')
    ))
    conn.commit()
    alert_id = cursor.lastrowid  # Retrieve the unique ID from the database
    alert['id'] = alert_id         # Store it in the alert dictionary
    return alert_id

def debug_save_alert(user_id, alert):
    # Save the alert
    save_alert(user_id, alert)

    # Retrieve the last inserted alert for this user
    cursor.execute('''
        SELECT id, user_id, alert_type, ticker, period, target_price, direction,
               date1, price1, date2, price2, threshold
        FROM alerts
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 1
    ''', (user_id,))
    result = cursor.fetchone()
    print("Debug: Last saved alert for user", user_id, ":", result)


def load_alerts():
    cursor.execute("""
        SELECT id, user_id, alert_type, ticker, period, target_price, direction,
               date1, price1, date2, price2, threshold
        FROM alerts
    """)
    rows = cursor.fetchall()
    alerts = {}
    for row in rows:
        user_id = row[1]
        alert = {
            'id': row[0],
            'type': row[2],
            'ticker': row[3],
            'period': row[4],
            'target_price': row[5],
            'direction': row[6],
            'date1': row[7],
            'price1': row[8],
            'date2': row[9],
            'price2': row[10],
            'threshold': row[11]
        }
        user_id = row[1]
        alerts.setdefault(user_id, []).append(alert)
    return alerts


# Async function to check alerts every 15 minutes (only during market hours)
async def check_alerts(context: ContextTypes.DEFAULT_TYPE):
    tz = timezone('America/New_York')
    now = datetime.now(tz)
    # If the market is closed, schedule the next check at market open and exit.
    print(market_is_open())
    if not market_is_open():
        wait_time = seconds_until_market_open()
        logger.info("Market is closed. Next check in %.0f seconds.", wait_time)
        context.job_queue.run_once(check_alerts, wait_time, data=context)
        return

    for user_id, alerts in list(user_alerts.items()):
        for alert in alerts.copy():
            ticker = alert.get('ticker')
            stock = yf.Ticker(ticker)
            data = stock.history(period='1d', interval='1m')
            if data.empty:
                continue
            current_price = data['Close'].iloc[-1]
            # SMA alert check
            if alert['type'] == 'sma':
                sma_value = calculate_sma(ticker, period=alert.get('period', 20))
                if sma_value is None:
                    continue
                condition = False
                if alert['direction'] == 'above' and current_price > sma_value:
                    condition = True
                elif alert['direction'] == 'below' and current_price < sma_value:
                    condition = True

                if condition:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            f"📈 *SMA Alert Triggered!*\n\n"
                            f"*{ticker}*\n"
                            f"Current Price: *{current_price:.2f}*\n"
                            f"SMA({alert.get('period',20)}): *{sma_value:.2f}*\n"
                            f"Direction: *{alert['direction']}*"
                        ),
                        parse_mode="Markdown"
                    )
                    alerts.remove(alert)
                    await send_alert_graph(context, user_id, alert, current_price)


            # Price alert check
            elif alert['type'] == 'price':
                target_price = alert['target_price']
                condition = False
                if alert['direction'] == 'above' and current_price > target_price:
                    condition = True
                elif alert['direction'] == 'below' and current_price < target_price:
                    condition = True

                if condition:
                    keyboard = [
                        [InlineKeyboardButton("✅ Remove Alert", callback_data=f"remove_{alert['id']}")],
                        [InlineKeyboardButton("❌ Keep Alert", callback_data=f"keep_{alert['id']}")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            f"💰 *Price Alert Triggered!*\n\n"
                            f"*{ticker}*\n"
                            f"Current Price: *{current_price:.2f}*\n"
                            f"Target Price: *{target_price:.2f}*\n"
                            f"Direction: *{alert['direction']}*\n\n"
                            "Do you want to remove this alert?"
                        ),
                        parse_mode="Markdown",
                        reply_markup=reply_markup
                    )
                    # Do not remove the alert here; wait for the user's callback response.
                    alerts.remove(alert)
                    await send_alert_graph(context, user_id, alert, current_price)


            # Custom line alert check
            elif alert['type'] == 'custom_line':
                date1 = alert['date1']
                price1 = alert['price1']
                date2 = alert['date2']
                price2 = alert['price2']
                projected_price = calculate_custom_line_trading_days(date1, price1, date2, price2)
                threshold = alert.get('threshold', 0.5)
                if abs(current_price - projected_price) <= threshold:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            f"📊 *Custom Line Alert Triggered!*\n\n"
                            f"*{ticker}*\n"
                            f"Current Price: *{current_price:.2f}*\n"
                            f"Projected Price: *{projected_price:.2f}*\n"
                            f"(Threshold: ±{threshold})"
                        ),
                        parse_mode="Markdown"
                    )
                    alerts.remove(alert)
                    await send_alert_graph(context, user_id, alert, current_price)

    logger.info("Price check complete, next check in 15 secounds")
    # Schedule the next check in 15 seconds
    context.job_queue.run_once(check_alerts, 15, data=context)

async def send_alert_graph(context: ContextTypes.DEFAULT_TYPE, chat_id: int, alert: dict, current_price: float):
    ticker = alert['ticker']
    loop = asyncio.get_running_loop()
    # Define the date range (20 days for data)
    start_date = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")
    
    # Fetch complete daily data (with today's candle)
    df = await loop.run_in_executor(None, lambda: get_complete_daily_data(ticker, start_date, end_date))
    if df.empty:
        await context.bot.send_message(chat_id, f"No historical data available for {ticker} starting from {start_date}.")
        return

    # Build base candlestick chart
    fig = go.Figure(data=[go.Candlestick(
        x=df.index,
        open=df['Open'],
        high=df['High'],
        low=df['Low'],
        close=df['Close'],
        increasing_line_color='green',
        decreasing_line_color='red',
        showlegend=False
    )])
    
    # Update layout with rangebreaks to skip weekends
    fig.update_layout(
        template='plotly_dark',
        title={'text': f"{ticker} Alert Graph (Latest 14 Days)", 'x': 0.5},
        xaxis=dict(
            title="Date",
            rangeslider=dict(visible=False),
            rangebreaks=[dict(bounds=["sat", "mon"])]
        ),
        showlegend=False,
        yaxis=dict(title="Price"),
        margin=dict(l=50, r=50, t=80, b=50)
    )
    
    # Use alert-specific helpers with proper parameters:
    threshold = alert.get('threshold', 0.5)
    alert_type = alert['type']
    if alert_type == "custom_line":
        # Call with (fig, alert, current_price, threshold)
        add_custom_line_trace(fig, alert, current_price, threshold)
    elif alert_type == "sma":
        # Call SMA helper with additional parameters: ticker, alert, current_price, threshold, start_date, end_date, loop
        success = await add_sma_trace(fig, ticker, alert, current_price, threshold, start_date, end_date, loop)
        if not success:
            await context.bot.send_message(chat_id, f"Failed to generate SMA data for {ticker}.")
            return
    elif alert_type == "price":
        # Call with (fig, df, alert, current_price, threshold)
        add_price_trace(fig, df, alert, current_price, threshold)
    else:
        # Skip unknown alert types
        return

    # Convert the figure to an image and send it
    def convert_fig():
        buf = BytesIO()
        fig.write_image(buf, format="png", width=1200, height=800, scale=2)
        buf.seek(0)
        return buf.getvalue()

    img_bytes = await loop.run_in_executor(None, convert_fig)
    if img_bytes:
        await context.bot.send_photo(
            chat_id,
            photo=img_bytes,
            caption=f"Graph for {ticker} alert."
        )
    else:
        await context.bot.send_message(chat_id, f"Failed to generate chart for {ticker}.")


def get_complete_daily_data(ticker, start_date, end_date):
    """
    Downloads historical daily data and appends today's aggregated candle (from intraday data)
    if today's candle is missing.
    """
    df = yf.download(ticker, start=start_date, end=end_date)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    tz = timezone('America/New_York')
    today_date = datetime.now(tz).date()
    if df.empty or df.index[-1].date() < today_date:
        today_str = today_date.strftime("%Y-%m-%d")
        next_day_str = (today_date + timedelta(days=1)).strftime("%Y-%m-%d")
        df_intraday = yf.download(ticker, start=today_str, end=next_day_str, interval="1m")
        if not df_intraday.empty:
            if isinstance(df_intraday.columns, pd.MultiIndex):
                df_intraday.columns = df_intraday.columns.droplevel(1)
            open_price = df_intraday['Open'].iloc[0]
            high_price = df_intraday['High'].max()
            low_price = df_intraday['Low'].min()
            close_price = df_intraday['Close'].iloc[-1]
            volume = df_intraday['Volume'].sum()
            df_today = pd.DataFrame({
                'Open': [open_price],
                'High': [high_price],
                'Low': [low_price],
                'Close': [close_price],
                'Volume': [volume]
            }, index=[pd.to_datetime(today_str)])
            df = pd.concat([df, df_today])
            df.sort_index(inplace=True)
    return df

def add_custom_line_trace(fig, alert, current_price, threshold):
    """
    Adds a custom line trace and, if the current price is near the projection, a crossing marker.
    Assumes you have a function called calculate_custom_line_trading_days_target.
    """
    date1 = pd.to_datetime(alert['date1'])
    price1 = alert['price1']
    date2 = pd.to_datetime(alert['date2'])
    price2 = alert['price2']
    today_ts = pd.Timestamp(datetime.now().date())
    # Calculate projected prices (your custom function must be defined)
    projected_price_today = calculate_custom_line_trading_days_target(date1, price1, date2, price2, today_ts)
    future_trading_days = pd.bdate_range(start=today_ts, periods=7)
    future_date = future_trading_days[-1] if len(future_trading_days) > 0 else today_ts
    projected_price_future = calculate_custom_line_trading_days_target(date1, price1, date2, price2, future_date)
    line_dates = [date1, date2, today_ts, future_date]
    line_prices = [price1, price2, projected_price_today, projected_price_future]
    fig.add_trace(go.Scatter(
        x=line_dates,
        y=line_prices,
        mode='lines',
        line=dict(color='yellow', width=4),
        name='Custom Line'
    ))
    if abs(current_price - projected_price_today) <= threshold:
        fig.add_trace(go.Scatter(
            x=[today_ts],
            y=[current_price],
            mode='markers',
            marker=dict(color='red', size=12, symbol='x'),
            name='Cross'
        ))

async def add_sma_trace(fig, ticker, alert, current_price, threshold, start_date, end_date, loop):
    # Ensure threshold has a default value if it's None
    threshold = threshold or 0.5

    period = alert.get('period', 20)
    extended_days = max(7, period * 2)
    start_date_extended = (datetime.now() - timedelta(days=extended_days)).strftime("%Y-%m-%d")
    df_extended = await loop.run_in_executor(
        None,
        lambda: get_complete_daily_data(ticker, start_date_extended, end_date)
    )
    if df_extended.empty:
        return False
    if isinstance(df_extended.columns, pd.MultiIndex):
        df_extended.columns = df_extended.columns.droplevel(1)
    df_extended['SMA'] = df_extended['Close'].rolling(window=period, min_periods=1).mean()
    # Restrict plotting to the chosen period (e.g., last 14 days)
    df_plot = df_extended.loc[start_date:]
    fig.data = []  # Clear existing traces
    fig.add_trace(go.Candlestick(
        x=df_plot.index,
        open=df_plot['Open'],
        high=df_plot['High'],
        low=df_plot['Low'],
        close=df_plot['Close'],
        increasing_line_color='green',
        decreasing_line_color='red',
        showlegend=False
    ))
    sma_series = df_extended.loc[start_date:]['SMA']
    if sma_series.empty or sma_series.isna().all():
        print("DEBUG: SMA series is empty or all NaN")
        return True
    fig.add_trace(go.Scatter(
        x=df_extended.loc[start_date:].index,
        y=sma_series,
        mode='lines',
        line=dict(color='orange', width=3),
        name=f"SMA({period})"
    ))
    last_sma = sma_series.iloc[-1]
    print(f"DEBUG: current_price: {current_price}, last_sma: {last_sma}, threshold: {threshold}")
    # Check explicitly if last_sma is a number before subtracting
    if last_sma is None or pd.isna(last_sma):
        print("DEBUG: last_sma is None or NaN; skipping marker")
        return True
    else:
        if abs(current_price - last_sma) <= threshold:
            last_date = df_extended.loc[start_date:].index[-1]
            fig.add_trace(go.Scatter(
                x=[last_date],
                y=[current_price],
                mode='markers+text',
                marker=dict(color='red', size=16, symbol='star-diamond', line=dict(color='black', width=2)),
                text=["Target"],
                textposition="top center",
                name='Target Marker'
            ))
    return True

def add_price_trace(fig, df, alert, current_price, threshold):
    """
    Adds a horizontal line at the target price and a marker for the price alert.
    """
    target_price = alert['target_price']
    fig.add_shape(
        type="line",
        x0=df.index.min(),
        y0=target_price,
        x1=df.index.max(),
        y1=target_price,
        line=dict(color="blue", width=3, dash="dash"),
        name='Price Level'
    )
    last_date = df.index[-1]
    fig.add_trace(go.Scatter(
        x=[last_date],
        y=[current_price],
        mode='markers+text',
        marker=dict(color='red', size=16, symbol='star-diamond', line=dict(color='black', width=2)),
        text=["Target"],
        textposition="top center",
        name='Target Marker'
    ))


async def alert_response_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    alert_id = data.split("_")[1]

    if data.startswith("remove_"):
        # Remove alert from database and optionally from memory
        cursor.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
        conn.commit()
        await query.delete_message()
        await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="✅ Alert removed."
        )
    elif data.startswith("keep_"):
        await query.delete_message()
        await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="ℹ️ Alert kept."
        )

# Command to start the bot
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Welcome to the Stock Alert Bot! Use /newalert to add a new alert or /listalerts to view your active alerts.")

async def handle_new_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.delete_message()
    context.user_data.clear()
    # Restart the alert creation flow (for example, by calling newalert_entry)
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="/newalert"
    )

async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    chat_id = update.message.chat_id if update.message else update.callback_query.message.chat_id

    keyboard = [
        [InlineKeyboardButton("➕ New Alert", callback_data="new_alert")],
        [InlineKeyboardButton("🔔 List Alerts", callback_data="list_alerts")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "🏠 *Main Menu*\n\nPlease choose an option:"

    # Use the appropriate method based on how the update was triggered.
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode="Markdown", reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            text, parse_mode="Markdown", reply_markup=reply_markup
        )


async def handle_list_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # Delete the main menu message and display the alerts
    await query.delete_message()
    await list_alerts(update, context)

async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # Update message with help information; you can extend this text as needed
    await query.edit_message_text(
        "ℹ️ *Help*\n\n"
        "• Use *New Alert* to create a new alert.\n"
        "• Use *List Alerts* to view or remove existing alerts.\n"
        "• *Settings* are coming soon!",
        parse_mode="Markdown"
    )

async def handle_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # Update message with settings information
    await query.edit_message_text(
        "⚙️ *Settings*\n\n"
        "Settings functionality is not implemented yet.",
        parse_mode="Markdown"
    )


async def list_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    cursor.execute("""
        SELECT id, alert_type, ticker, period, target_price, direction, date1, price1, date2, price2, threshold
        FROM alerts
        WHERE user_id = ?
    """, (chat_id,))
    rows = cursor.fetchall()

    if not rows:
        if update.message:
            await update.message.reply_text("😅 You have no active alerts.")
        else:
            await context.bot.send_message(chat_id, "😅 You have no active alerts.")
        return

    text = "🔔 <b>Active Alerts:</b>\n"
    keyboard_buttons = []
    counter = 1
    for row in rows:
        alert_id = row[0]
        alert_type = row[1]
        ticker = row[2]
        if alert_type == "sma":
            alert_text = f"<b>{ticker}</b> SMA alert: {row[5]} SMA({row[3]})"
        elif alert_type == "price":
            alert_text = f"<b>{ticker}</b> Price alert: {row[5]} {row[4]}"
        elif alert_type == "custom_line":
            alert_text = (f"<b>{ticker}</b> Custom Line alert: from {row[6]} ({row[7]}) "
                          f"to {row[8]} ({row[9]}), ±{row[10]}")
        else:
            alert_text = f"<b>{ticker}</b> {alert_type} alert"
        text += f"<b>{counter}</b>. {alert_text}\n"
        # Create a remove button for each alert
        keyboard_buttons.append([InlineKeyboardButton(f"Remove alert {counter}", callback_data=f"remove_{alert_id}")])
        counter += 1

    # Add a button to send graphs for all active alerts
    keyboard_buttons.append([InlineKeyboardButton("📊 Send All Graphs", callback_data="send_all_graphs")])
    # Add a back to menu button
    keyboard_buttons.append([InlineKeyboardButton("🏠 Back to Menu", callback_data="main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard_buttons)

    if update.message:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await context.bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=reply_markup)

async def send_all_graphs_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # Acknowledge the button press
    # Remove the inline keyboard so the button is disabled
    await query.edit_message_reply_markup(reply_markup=None)
    # Edit the message text to let the user know that graphs are loading
    await query.edit_message_text("Please wait, graphs are being loaded...")
    # Now call your function to generate and send the graphs
    await send_all_graphs(update, context)
    return ConversationHandler.END


# ---------- Main send_all_graphs Function ----------

async def send_all_graphs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    cursor.execute("""
        SELECT alert_type, ticker, date1, price1, date2, price2, threshold, period, target_price, direction
        FROM alerts
        WHERE user_id = ?
    """, (chat_id,))
    rows = cursor.fetchall()
    if not rows:
        await context.bot.send_message(chat_id, "😅 You have no active alerts.")
        return

    loop = asyncio.get_running_loop()

    for row in rows:
        try:
            # Convert row tuple to a dictionary for clarity
            alert = {
                'type': row[0],
                'ticker': row[1],
                'date1': row[2],
                'price1': row[3],
                'date2': row[4],
                'price2': row[5],
                'threshold': row[6],
                'period': row[7],
                'target_price': row[8],
                'direction': row[9]
            }
            alert_type = alert['type']
            ticker = alert['ticker']
            # For "sma" and "price" alerts, use a longer history; for custom_line, use the alert's date1
            if alert_type in ["sma", "price"]:
                start_date_str = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
            else:  # custom_line
                start_date_str = pd.to_datetime(alert['date1']).strftime("%Y-%m-%d")
            end_date_str = datetime.now().strftime("%Y-%m-%d")

            # Fetch complete daily data with today's candle included
            df = await loop.run_in_executor(
                None,
                lambda: get_complete_daily_data(ticker, start_date_str, end_date_str)
            )
            if df.empty:
                await context.bot.send_message(chat_id, f"No historical data available for {ticker} starting from {start_date_str}.")
                continue

            # Update current_price from the last candle's close
            current_price = df['Close'].iloc[-1]

            # Build the base candlestick chart
            fig = go.Figure(data=[go.Candlestick(
                x=df.index,
                open=df['Open'],
                high=df['High'],
                low=df['Low'],
                close=df['Close'],
                increasing_line_color='green',
                decreasing_line_color='red',
                showlegend=False
            )])

            # Use alert-specific helper functions
            threshold_val = alert.get('threshold', 0.5)
            if alert_type == "custom_line":
                add_custom_line_trace(fig, alert, current_price, threshold_val)
            elif alert_type == "sma":
                # Pass the loop and the start and end date strings to our SMA helper
                success = await add_sma_trace(fig, ticker, alert, current_price, threshold_val, start_date_str, end_date_str, loop)
                if not success:
                    await context.bot.send_message(chat_id, f"Failed to generate SMA data for {ticker}.")
                    continue
            elif alert_type == "price":
                add_price_trace(fig, df, alert, current_price, threshold_val)
            else:
                continue

            # Update layout with rangebreaks to remove weekends
            fig.update_layout(
                template='plotly_dark',
                title={'text': f"{ticker} Alert Graph (Latest 14 Days)", 'x': 0.5},
                xaxis=dict(
                    title="Date",
                    rangeslider=dict(visible=False),
                    rangebreaks=[dict(bounds=["sat", "mon"])]
                ),
                showlegend=False,
                yaxis=dict(title="Price"),
                margin=dict(l=50, r=50, t=80, b=50)
            )

            def convert_fig():
                buf = BytesIO()
                fig.write_image(buf, format="png", width=1200, height=800, scale=2)
                buf.seek(0)
                return buf.getvalue()

            img_bytes = await loop.run_in_executor(None, convert_fig)
            if not img_bytes:
                await context.bot.send_message(chat_id, f"Failed to generate chart for {ticker}.")
                continue
            await context.bot.send_photo(
                chat_id,
                photo=img_bytes,
                caption=f"Graph for {ticker} alert."
            )
        except Exception as e:
            await context.bot.send_message(chat_id, f"Error generating graph for {ticker}: {e}")


def calculate_custom_line_trading_days_target(date1, price1, date2, price2, target_date):
    # Convert dates to Timestamps
    d1 = pd.to_datetime(date1)
    d2 = pd.to_datetime(date2)
    target = pd.to_datetime(target_date)

    # Count the number of trading days between d1 and d2
    trading_days_between = pd.bdate_range(start=d1, end=d2)
    num_trading_days = len(trading_days_between)
    if num_trading_days == 0:
        return price2  # Avoid division by zero

    # Calculate the slope based on trading days
    slope = (price2 - price1) / num_trading_days

    # Count trading days from d1 to the target date
    trading_days_to_target = pd.bdate_range(start=d1, end=target)
    num_trading_days_to_target = len(trading_days_to_target)

    # Project the price using the trading day slope
    return price1 + slope * num_trading_days_to_target


async def remove_alert_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    alert_id = query.data.split("_")[1]
    cursor.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
    conn.commit()
    await query.delete_message()
    # Re-display updated list of alerts by calling list_alerts:
    await list_alerts(update, context)


async def cancel_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🚫 Alert creation cancelled. Use /menu to return to the main menu.")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Alert creation cancelled. Use /menu to return to the main menu.")
    return ConversationHandler.END

# ----- Conversation for New Alert -----
async def newalert_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Determine the chat_id whether this update comes from a message or a callback query.
    chat_id = update.message.chat_id if update.message else update.callback_query.message.chat_id
    keyboard = [
        [InlineKeyboardButton("📈 SMA Alert", callback_data="sma")],
        [InlineKeyboardButton("💰 Price Alert", callback_data="price")],
        [InlineKeyboardButton("📊 Custom Line Alert", callback_data="custom_line")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_alert")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(
        chat_id=chat_id,
        text="Please choose the type of alert you'd like to set:",
        reply_markup=reply_markup
    )
    return ALERT_TYPE

async def alert_type_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    alert_type = query.data
    context.user_data['alert_type'] = alert_type
    # Delete the original message (with the inline keyboard)
    await query.delete_message()
    # Send a new message without any inline keyboard
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="✍️ Please enter the stock ticker (e.g., AAPL):"
    )
    return GET_TICKER

async def get_ticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ticker = update.message.text.strip().upper()
    context.user_data['ticker'] = ticker
    alert_type = context.user_data.get('alert_type')
    if alert_type == "sma":
        await update.message.reply_text("✍️ Please enter the SMA period (e.g., 20):")
        return GET_PERIOD
    elif alert_type == "price":
        await update.message.reply_text("✍️ Please enter the target price (numeric):")
        return GET_PRICE
    elif alert_type == "custom_line":
        await update.message.reply_text("✍️ Please enter the first date (YYYY-MM-DD):")
        return GET_DATE1

async def get_period(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        period = int(update.message.text.strip())
        context.user_data['period'] = period
        keyboard = [
            [InlineKeyboardButton("⬆️ Above", callback_data="above"),
             InlineKeyboardButton("⬇️ Below", callback_data="below")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Please choose the direction:", reply_markup=reply_markup)
        return GET_DIRECTION
    except ValueError:
        await update.message.reply_text("❌ Invalid input. Please enter a numeric period (e.g., 20):")
        return GET_PERIOD

async def get_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        target_price = float(update.message.text.strip())
        context.user_data['target_price'] = target_price
        keyboard = [
            [InlineKeyboardButton("⬆️ Above", callback_data="above"),
             InlineKeyboardButton("⬇️ Below", callback_data="below")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Please choose the direction:", reply_markup=reply_markup)
        return GET_DIRECTION
    except ValueError:
        await update.message.reply_text("❌ Invalid input. Please enter a numeric target price:")
        return GET_PRICE

async def get_direction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    direction = query.data
    context.user_data['direction'] = direction

    alert_type = context.user_data.get('alert_type')
    ticker = context.user_data.get('ticker')

    if alert_type == "sma":
        alert = {
            'type': 'sma',
            'ticker': ticker,
            'period': context.user_data.get('period'),
            'direction': direction
        }
        save_alert(query.message.chat_id, alert)
        user_alerts.setdefault(query.message.chat_id, []).append(alert)
        text = f"✅ SMA alert set for *{ticker}* when price goes *{direction}* SMA({context.user_data.get('period')})!"
    elif alert_type == "price":
        alert = {
            'type': 'price',
            'ticker': ticker,
            'target_price': context.user_data.get('target_price'),
            'direction': direction
        }
        save_alert(query.message.chat_id, alert)
        user_alerts.setdefault(query.message.chat_id, []).append(alert)
        text = f"✅ Price alert set for *{ticker}* when price goes *{direction}* *{context.user_data.get('target_price')}*!"
    elif alert_type == "custom_line":
        # Continue the custom line flow
        await query.edit_message_text("✍️ Please enter the price on the first date:")
        return GET_PRICE1

    keyboard = [
        [InlineKeyboardButton("➕ Add Another Alert", callback_data="new_alert")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text=text, parse_mode="Markdown", reply_markup=reply_markup)
    return ConversationHandler.END

async def get_date1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        date1 = datetime.strptime(update.message.text.strip(), '%Y-%m-%d').date()
        context.user_data['date1'] = date1

        ticker = context.user_data.get('ticker')
        stock = yf.Ticker(ticker)
        start_str = date1.strftime('%Y-%m-%d')
        end_str = (date1 + timedelta(days=1)).strftime('%Y-%m-%d')
        hist = stock.history(start=start_str, end=end_str)
        if not hist.empty:
            low_price = hist['Low'].min()
            context.user_data['price1'] = low_price
            await update.message.reply_text(
                f"For {date1}, the lowest price was {low_price:.2f} (automatically detected).\n"
                "If you want to change this value, please enter a new price.\n"
                "Or tap the 'Accept' button to keep the auto‑detected price.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Accept", callback_data="accept_price1")]])
            )
            return GET_PRICE1_OVERRIDE
        else:
            await update.message.reply_text(
                f"No data available for {date1}. Please manually enter the price on that date:"
            )
            return GET_PRICE1_OVERRIDE
    except ValueError:
        await update.message.reply_text("❌ Invalid date format. Please use YYYY-MM-DD:")
        return GET_DATE1

async def accept_price1_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    confirmed_price1 = context.user_data.get('price1')
    await query.edit_message_text(
        f"Accepted auto‑detected price for {context.user_data.get('date1')}: {confirmed_price1:.2f}.\n"
        "Please enter the second date (YYYY-MM-DD):"
    )
    return GET_DATE2

async def get_price1_override(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price1 = float(update.message.text.strip())
        context.user_data['price1'] = price1
        await update.message.reply_text(
            f"Custom price for {context.user_data.get('date1')} set to {price1:.2f}.\n"
            "Please enter the second date (YYYY-MM-DD):"
        )
        return GET_DATE2
    except ValueError:
        await update.message.reply_text("❌ Invalid input. Please enter a numeric price:")
        return GET_PRICE1_OVERRIDE

async def get_date2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        date2 = datetime.strptime(update.message.text.strip(), '%Y-%m-%d').date()
        context.user_data['date2'] = date2

        ticker = context.user_data.get('ticker')
        stock = yf.Ticker(ticker)
        start_str = date2.strftime('%Y-%m-%d')
        end_str = (date2 + timedelta(days=1)).strftime('%Y-%m-%d')
        hist = stock.history(start=start_str, end=end_str)
        if not hist.empty:
            auto_price2 = hist['Low'].min()
            context.user_data['price2'] = auto_price2
            await update.message.reply_text(
                f"For {date2}, the lowest price was {auto_price2:.2f} (automatically detected).\n"
                "If you want to change this value, please enter a new price.\n"
                "Or tap the 'Accept' button to keep the auto‑detected price.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Accept", callback_data="accept_price2")]])
            )
            return GET_PRICE2_OVERRIDE
        else:
            await update.message.reply_text(
                f"No data available for {date2}. Please manually enter the price on that date:"
            )
            return GET_PRICE2_OVERRIDE
    except ValueError:
        await update.message.reply_text("❌ Invalid date format. Please use YYYY-MM-DD:")
        return GET_DATE2

async def accept_price2_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    confirmed_price2 = context.user_data.get('price2')
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("0.5", callback_data="default_threshold")]])
    await query.edit_message_text(
        text=(
            f"Accepted auto‑detected price for {context.user_data.get('date2')}: {confirmed_price2:.2f}.\n"
            "Now, please enter a threshold value (default is 0.5) or tap the button."
        ),
        reply_markup=keyboard
    )
    return GET_THRESHOLD

async def get_price2_override(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    try:
        custom_price = float(user_input)
        context.user_data['price2'] = custom_price
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Default", callback_data="default_threshold")]
        ])
        await update.message.reply_text(
            f"Custom price for {context.user_data.get('date2')} set to {custom_price:.2f}.\n"
            "Now, please enter a threshold value (default is 0.5) or tap the button.",
            reply_markup=keyboard
        )
        return GET_THRESHOLD
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid input. Please enter a numeric price or tap the 'Accept' button to use the auto‑detected value:"
        )
        return GET_PRICE2_OVERRIDE

async def default_threshold_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # Acknowledge the callback
    # Set the threshold to 0.5 by default
    context.user_data['threshold'] = 0.5
    await query.edit_message_text(
        "Default threshold of 0.5 accepted.\n"
        "You will receive the chart shortly..."
    )
    # Proceed with chart generation or next step here...
    return GET_THRESHOLD

def calculate_custom_line_trading_days(date1, price1, date2, price2):
    # Convert input dates to pandas Timestamps
    d1 = pd.to_datetime(date1)
    d2 = pd.to_datetime(date2)

    # Generate a range of business days between d1 and d2 (inclusive)
    trading_days_between = pd.bdate_range(start=d1, end=d2)
    num_trading_days = len(trading_days_between)

    # Guard against division by zero
    if num_trading_days == 0:
        return price2

    # Calculate the slope using trading days
    slope = (price2 - price1) / num_trading_days

    # Convert today’s date to a pandas Timestamp
    today = pd.to_datetime(datetime.now().date())
    # Generate the business day range from d1 to today
    trading_days_since_d1 = pd.bdate_range(start=d1, end=today)
    num_trading_days_since_d1 = len(trading_days_since_d1)

    # Project the price by applying the slope to the trading days elapsed
    projected_price = price1 + slope * num_trading_days_since_d1
    return projected_price


async def get_threshold(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    if user_input.lower() == 'skip':
        threshold = 0.5
    else:
        try:
            threshold = float(user_input)
        except ValueError:
            await update.message.reply_text("❌ Invalid input. Please enter a numeric threshold or type 'skip':")
            return GET_THRESHOLD
    context.user_data['threshold'] = threshold

    # Save the custom line alert (and update your in-memory store)
    alert = {
        'type': 'custom_line',
        'ticker': context.user_data.get('ticker'),
        'date1': context.user_data.get('date1'),
        'price1': context.user_data.get('price1'),
        'date2': context.user_data.get('date2'),
        'price2': context.user_data.get('price2'),
        'threshold': threshold
    }
    debug_save_alert(update.effective_chat.id, alert)
    user_alerts.setdefault(update.effective_chat.id, []).append(alert)

    text_message = (
        f"✅ Custom Line alert set for *{context.user_data.get('ticker')}* from {context.user_data.get('date1')} "
        f"({context.user_data.get('price1'):.2f}) to {context.user_data.get('date2')} "
        f"({context.user_data.get('price2'):.2f}) with threshold ±{threshold}!\n"
        "You will receive the chart shortly..."
    )
    keyboard = [
        [InlineKeyboardButton("➕ Add Another Alert", callback_data="new_alert")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text_message, parse_mode="Markdown", reply_markup=reply_markup)
    print("DEBUG: Confirmation message sent.", flush=True)
    ticker = context.user_data.get('ticker')
    # Historical data: start from date1 until today
    date1 = pd.to_datetime(context.user_data.get('date1'))
    start_date_str = date1.strftime("%Y-%m-%d")
    end_date_str = datetime.now().strftime("%Y-%m-%d")
    print("DEBUG: Starting chart generation for custom line alert.", flush=True)

    loop = asyncio.get_running_loop()

    try:
        df = await loop.run_in_executor(
            None,
            lambda: yf.download(ticker, start=start_date_str, end=end_date_str)
        )
        if df.empty:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="No data available to generate the chart."
            )
            return ConversationHandler.END
        print("DEBUG: Historical data downloaded successfully.", flush=True)
    except Exception as e:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="An error occurred while downloading historical data."
        )
        return ConversationHandler.END

    try:
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)

        # Create candlestick trace using data from date1 until today
        candlestick = go.Candlestick(
            x=df.index,
            open=df['Open'],
            high=df['High'],
            low=df['Low'],
            close=df['Close'],
            increasing_line_color='green',
            decreasing_line_color='red',
            showlegend=False
        )
        fig = go.Figure(data=[candlestick])

        # Get user-provided custom line points
        price1 = context.user_data.get('price1')
        date2 = pd.to_datetime(context.user_data.get('date2'))
        price2 = context.user_data.get('price2')  # This is the final confirmed price
        today = datetime.now().date()
        # Extend the line 7 days into the future
        future_date = pd.Timestamp(today) + timedelta(days=7)

        # Helper to calculate projected price at a target date
        def calculate_custom_line_at(date1, price1, date2, price2, target_date):
            days_diff = (date2 - date1).days
            if days_diff == 0:
                return price2
            slope = (price2 - price1) / days_diff
            days_to_target = (pd.Timestamp(target_date) - date2).days
            return price2 + slope * days_to_target

        projected_price_today = calculate_custom_line_at(date1, price1, date2, price2, today)
        projected_price_future = calculate_custom_line_at(date1, price1, date2, price2, future_date)

        # Build the trend line: start at date1, pass through date2, through today, and extend to future_date
        line_dates = [date1, date2, pd.Timestamp(today), future_date]
        line_prices = [price1, price2, projected_price_today, projected_price_future]

        # Add custom trend line in yellow
        fig.add_trace(go.Scatter(
            x=line_dates,
            y=line_prices,
            mode='lines',
            line=dict(color='yellow', width=4),
            showlegend=False
        ))

        fig.update_layout(
            template='plotly_dark',
            title=dict(
                text=ticker,
                x=0.5,
                xanchor='center'
            ),
            xaxis=dict(
                title="Date",
                rangeslider=dict(visible=False),
                rangebreaks=[dict(bounds=["sat", "mon"])],
            ),
            yaxis=dict(title="Price"),
            margin=dict(l=50, r=50, t=80, b=50),
            showlegend=False
        )
        print("DEBUG: Chart created successfully.", flush=True)
    except Exception as e:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="An error occurred while creating the chart."
        )
        return ConversationHandler.END

    try:
        def convert_fig():
            buf = BytesIO()
            # Increase resolution for better clarity
            fig.write_image(buf, format="png", width=1200, height=800, scale=2)
            buf.seek(0)
            return buf.getvalue()
        img_bytes = await loop.run_in_executor(None, convert_fig)
        if not img_bytes:
            print("DEBUG: No image bytes returned.", flush=True)
        else:
            print("DEBUG: Chart image generated successfully.", flush=True)
    except Exception as e:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="An error occurred while generating the chart image."
        )
        return ConversationHandler.END

    try:
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=img_bytes,
            caption="Here is your candlestick chart with the custom line!"
        )
        print("DEBUG: Chart image sent to user successfully.", flush=True)
    except Exception as e:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="An error occurred while sending the chart image."
        )
    print("DEBUG: End of get_threshold.", flush=True)
    return ConversationHandler.END



# -----------------------------------------
def main():
    global user_alerts
    user_alerts = load_alerts()  # Load persisted alerts from the database
    print("Loaded alerts:", user_alerts)  # Debug print
    API_TOKEN = os.getenv("TELEGRAM_API_TOKEN")
    print("API Token:", API_TOKEN)
    application = ApplicationBuilder().token(API_TOKEN).build()

    # Command Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("listalerts", list_alerts))
    application.add_handler(CommandHandler("menu", handle_main_menu))


    # Conversation Handler for New Alerts
    conv_handler = ConversationHandler(
        entry_points=[
        CommandHandler("newalert", newalert_entry),
        CallbackQueryHandler(newalert_entry, pattern="^new_alert$")
        ],
        states={
            GET_DATE1: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_date1)],
            GET_PRICE1_OVERRIDE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_price1_override),
                CallbackQueryHandler(accept_price1_callback, pattern="^accept_price1$")
            ],
            GET_DATE2: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_date2)],
            GET_PRICE2_OVERRIDE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_price2_override),
                CallbackQueryHandler(accept_price2_callback, pattern="^accept_price2$")
            ],
            GET_THRESHOLD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_threshold),
                CallbackQueryHandler(default_threshold_callback, pattern="^default_threshold$")
            ],
            ALERT_TYPE: [CallbackQueryHandler(alert_type_choice)],
            LIST_ALERTS: [
                # Your existing handlers for alert listing...
                CallbackQueryHandler(send_all_graphs_callback, pattern="^send_all_graphs$")
            ],
            GET_TICKER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_ticker)],
            GET_PERIOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_period)],
            GET_DIRECTION: [CallbackQueryHandler(get_direction)],
            GET_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_price)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    application.add_handler(conv_handler)

    # Callback Query Handlers for Main Menu and Inline Buttons
    application.add_handler(CallbackQueryHandler(handle_new_alert, pattern="^new_alert$"))
    application.add_handler(CallbackQueryHandler(handle_main_menu, pattern="^main_menu$"))
    application.add_handler(CallbackQueryHandler(handle_list_alerts, pattern="^list_alerts$"))
    application.add_handler(CallbackQueryHandler(handle_help, pattern="^help$"))
    application.add_handler(CallbackQueryHandler(handle_settings, pattern="^settings$"))
    application.add_handler(CallbackQueryHandler(remove_alert_callback, pattern="^remove_"))
    application.add_handler(CallbackQueryHandler(alert_response_handler, pattern="^(remove_|keep_)"))
    application.add_handler(CallbackQueryHandler(cancel_alert, pattern="^cancel_alert$"))
    application.add_handler(CallbackQueryHandler(send_all_graphs_callback, pattern="^send_all_graphs$"))



    # JobQueue to check alerts every 15 seconds (adjust interval as needed)
    application.job_queue.run_repeating(check_alerts, interval=15, first=10)
    # Define Israel's timezone.
    israel_tz = zoneinfo.ZoneInfo("Asia/Jerusalem")
    application.job_queue.run_once(send_summary, when=0)

    # Schedule the job to run daily at 17:30 local time.
    application.job_queue.run_daily(send_summary, time=time(hour=17, minute=30, tzinfo=israel_tz))
    # Schedule the job to run daily at 23:30 local time.
    application.job_queue.run_daily(send_summary, time=time(hour=23, minute=30, tzinfo=israel_tz))



    # Start the Bot
    application.run_polling()


if __name__ == '__main__':
    main()
