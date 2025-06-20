import asyncio
import logging
from io import BytesIO
from datetime import datetime, timedelta
import pandas as pd
from plotly import graph_objects as go
from pytz import timezone

from bot_core.utils.helpers import market_is_open, seconds_until_market_open

logger = logging.getLogger(__name__)


class AlertManager:
    def __init__(self, db_manager, stock_service, bot, user_alerts):
        self.db_manager = db_manager
        self.stock_service = stock_service
        self.bot = bot
        self.user_alerts = user_alerts # The global user_alerts dict

    def _calculate_custom_line_trading_days(self, date1, price1, date2, price2):
        d1 = pd.to_datetime(date1)
        d2 = pd.to_datetime(date2)
        trading_days_between = pd.bdate_range(start=d1, end=d2)
        num_trading_days = len(trading_days_between)
        if num_trading_days == 0:
            return price2

        slope = (price2 - price1) / num_trading_days
        today = pd.to_datetime(datetime.now().date())
        trading_days_since_d1 = pd.bdate_range(start=d1, end=today)
        num_trading_days_since_d1 = len(trading_days_since_d1)
        
        projected_price = price1 + slope * num_trading_days_since_d1
        return projected_price

    async def check_alerts(self, context):
        """The core logic for checking all active user alerts."""
        #Testin - removed not
        if not market_is_open():
            wait_time = seconds_until_market_open()
            logger.info(f"Market is closed. Next alert check in {wait_time:.0f} seconds.")
            # This job will be rescheduled by the main bot loop
            return

        tickers = {alert["ticker"] for alerts in self.user_alerts.values() for alert in alerts}
        if not tickers:
            logger.info("No active alerts to check.")
            return

        logger.info(f"Downloading data for {len(tickers)} tickers: {tickers}")
        try:
            data = self.stock_service.download_intraday_data(list(tickers))
        except Exception as e:
            logger.error(f"Error fetching stock data: {e}")
            return
            
        for user_id, alerts in list(self.user_alerts.items()):
            for alert in alerts.copy():
                ticker = alert["ticker"]
                try:
                    current_price = data[ticker]["Close"].iloc[-1]
                except (KeyError, IndexError):
                    logger.warning(f"No data available for {ticker}, skipping.")
                    continue

                if alert["type"] == "sma":
                    sma_value = self.stock_service.calculate_sma(ticker, period=alert.get("period", 20))
                    if sma_value and (
                        (alert["direction"] == "above" and current_price > sma_value) or
                        (alert["direction"] == "below" and current_price < sma_value)
                    ):
                        await self.send_sma_alert(user_id, alert, current_price, sma_value)
                        self.db_manager.remove_alert(alert['id'])
                        alerts.remove(alert)
                
                elif alert["type"] == "price":
                    target_price = alert["target_price"]
                    if (
                        (alert["direction"] == "above" and current_price > target_price) or
                        (alert["direction"] == "below" and current_price < target_price)
                    ):
                        await self.send_price_alert(user_id, alert, current_price)
                        # User decides to remove via callback
                
                elif alert["type"] == "custom_line":
                    projected_price = self._calculate_custom_line_trading_days(
                        alert["date1"], alert["price1"], alert["date2"], alert["price2"]
                    )
                    threshold = alert.get("threshold", 0.5)
                    if abs(current_price - projected_price) <= threshold:
                        await self.send_custom_line_alert(user_id, alert, current_price, projected_price)
                        self.db_manager.remove_alert(alert['id'])
                        alerts.remove(alert)

    async def send_sma_alert(self, user_id, alert, current_price, sma_value):
        """Sends a notification for a triggered SMA alert."""
        await self.bot.send_message(
            chat_id=user_id,
            text=(
                f"📈 *SMA Alert Triggered!*\n\n"
                f"*{alert['ticker']}*\n"
                f"Current Price: *{current_price:.2f}*\n"
                f"SMA({alert.get('period', 20)}): *{sma_value:.2f}*\n"
                f"Direction: *{alert['direction']}*"
            ),
            parse_mode="Markdown"
        )
        await self.send_alert_graph(user_id, alert, current_price)

    async def send_price_alert(self, user_id, alert, current_price):
        """Sends a notification for a triggered price alert with action buttons."""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        keyboard = [
            [InlineKeyboardButton("✅ Remove Alert", callback_data=f"remove_{alert['id']}")],
            [InlineKeyboardButton("❌ Keep Alert", callback_data=f"keep_{alert['id']}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await self.bot.send_message(
            chat_id=user_id,
            text=(
                f"💰 *Price Alert Triggered!*\n\n"
                f"*{alert['ticker']}*\n"
                f"Current Price: *{current_price:.2f}*\n"
                f"Target Price: *{alert['target_price']:.2f}*\n"
                f"Direction: *{alert['direction']}*\n\n"
                "Do you want to remove this alert?"
            ),
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        await self.send_alert_graph(user_id, alert, current_price)

    async def send_custom_line_alert(self, user_id, alert, current_price, projected_price):
        """Sends a notification for a triggered custom line alert."""
        await self.bot.send_message(
            chat_id=user_id,
            text=(
                f"📊 *Custom Line Alert Triggered!*\n\n"
                f"*{alert['ticker']}*\n"
                f"Current Price: *{current_price:.2f}*\n"
                f"Projected Price: *{projected_price:.2f}*\n"
                f"(Threshold: ±{alert.get('threshold', 0.5)})"
            ),
            parse_mode="Markdown"
        )
        await self.send_alert_graph(user_id, alert, current_price)
        
    async def send_alert_graph(self, chat_id: int, alert: dict, current_price: float):
        """Generates and sends a graph for a triggered alert."""
        ticker = alert['ticker']
        loop = asyncio.get_running_loop()
        start_date = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d")
        end_date = datetime.now().strftime("%Y-%m-%d")

        df = await loop.run_in_executor(
            None, lambda: self.stock_service.get_complete_daily_data(ticker, start_date, end_date)
        )
        if df.empty:
            logger.warning(f"No data for {ticker} to generate graph.")
            return

        fig = go.Figure(data=[go.Candlestick(
            x=df.index,
            open=df['Open'],
            high=df['High'],
            low=df['Low'],
            close=df['Close'],
            increasing_line_color='green',
            decreasing_line_color='red',
        )])

        fig.update_layout(
            template='plotly_dark',
            title={'text': f"{ticker} Alert Graph", 'x': 0.5},
            xaxis_rangeslider_visible=False
        )

        # Here you would call the specific trace adders (add_sma_trace, etc.)
        # For now, this is a simplified version. The logic will be moved here.

        img_bytes = await loop.run_in_executor(
            None, lambda: fig.to_image(format="png", width=1200, height=800, scale=2)
        )
        
        await self.bot.send_photo(
            chat_id,
            photo=img_bytes,
            caption=f"Graph for {ticker} alert."
        )