import asyncio
from datetime import datetime, timedelta
from io import BytesIO
import pandas as pd
from plotly import graph_objects as go
from telegram import Update
from telegram.ext import ContextTypes
import yfinance as yf
import logging

logger = logging.getLogger(__name__)

def add_custom_line_trace(fig, alert, current_price, threshold, alert_manager):
    """
    Adds a custom line trace and, if the current price is near the projection, a crossing marker.
    """
    date1 = pd.to_datetime(alert['date1'])
    price1 = alert['price1']
    date2 = pd.to_datetime(alert['date2'])
    price2 = alert['price2']
    today_ts = pd.Timestamp(datetime.now().date())
    
    # Use the alert_manager's calculation method
    projected_price_today = alert_manager._calculate_custom_line_trading_days(
        alert["date1"], alert["price1"], alert["date2"], alert["price2"]
    )

    # For future projection, we can reuse the logic but with a future date
    future_trading_days = pd.bdate_range(start=today_ts, periods=7)
    future_date = future_trading_days[-1] if len(future_trading_days) > 0 else today_ts
    
    # This is a bit of a trick: to calculate a future point, we can't directly use the alert manager's
    # method as it's designed for the present. We'll replicate the slope calculation for the future point.
    trading_days_between = pd.bdate_range(start=date1, end=date2)
    num_trading_days = len(trading_days_between)
    slope = (price2 - price1) / num_trading_days if num_trading_days > 0 else 0
    
    days_to_future = len(pd.bdate_range(start=date1, end=future_date))
    projected_price_future = price1 + slope * days_to_future

    line_dates = [date1, date2, today_ts, future_date]
    line_prices = [price1, price2, projected_price_today, projected_price_future]
    fig.add_trace(go.Scatter(
        x=line_dates,
        y=line_prices,
        mode='lines',
        line=dict(color='yellow', width=4),
        name='Custom Line'
    ))
    if threshold is not None and abs(current_price - projected_price_today) <= threshold:
        fig.add_trace(go.Scatter(
            x=[today_ts],
            y=[projected_price_today],
            mode='markers',
            marker=dict(color='red', size=12, symbol='x'),
            name='Cross'
        ))

async def add_sma_trace(fig, ticker, alert, current_price, threshold, start_date, end_date, loop, stock_service):
    # Ensure threshold has a default value if it's None
    threshold = threshold or 0.5

    period = alert.get('period', 20)
    extended_days = max(7, period * 2)
    start_date_extended = (datetime.now() - timedelta(days=extended_days)).strftime("%Y-%m-%d")
    df_extended = await loop.run_in_executor(
        None,
        lambda: stock_service.get_complete_daily_data(ticker, start_date_extended, end_date)
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
        logger.warning("SMA series is empty or all NaN")
        return True
    fig.add_trace(go.Scatter(
        x=df_extended.loc[start_date:].index,
        y=sma_series,
        mode='lines',
        line=dict(color='orange', width=3),
        name=f"SMA({period})"
    ))
    last_sma = sma_series.iloc[-1]
    # Check explicitly if last_sma is a number before subtracting
    if last_sma is None or pd.isna(last_sma):
        logger.warning("last_sma is None or NaN; skipping marker")
        return True
    else:
        #if abs(current_price - last_sma) <= threshold:
            last_date = df_extended.loc[start_date:].index[-1]
            fig.add_trace(go.Scatter(
                x=[last_date],
                y=[last_sma],
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
        x0=df.index[0],
        y0=target_price,
        x1=df.index[-1],
        y1=target_price,
        line=dict(color="cyan", width=2, dash="dash"),
        name="Target Price"
    )
    if threshold is not None and abs(current_price - target_price) <= threshold:
        fig.add_trace(go.Scatter(
            x=[df.index[-1]],
            y=[current_price],
            mode='markers',
            marker=dict(color='red', size=12, symbol='x'),
            name='Current Price'
        ))
async def generate_alert_graph(alert: dict, stock_service, alert_manager) -> bytes:
    """
    Generates a Plotly graph for a given alert and returns it as image bytes.
    This function consolidates the graphing logic from the old bot.
    """
    ticker = alert['ticker']
    loop = asyncio.get_running_loop()
    
    # Define the date range (20 days for data)
    start_date = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")

    # Fetch complete daily data using the stock_service
    df = await loop.run_in_executor(
        None, lambda: stock_service.get_complete_daily_data(ticker, start_date, end_date)
    )
    if df.empty:
        logger.warning(f"No historical data for {ticker} to generate a graph.")
        return None

    # Get current price from the last data point
    current_price = df['Close'].iloc[-1]

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

    # Use alert-specific helpers with proper parameters
    threshold = alert.get('threshold', 0.5)
    alert_type = alert['type']

    if alert_type == "custom_line":
        add_custom_line_trace(fig, alert, current_price, threshold, alert_manager)
    elif alert_type == "sma":
        success = await add_sma_trace(fig, ticker, alert, current_price, threshold, start_date, end_date, loop, stock_service)
        if not success:
            logger.warning(f"Failed to generate SMA data for {ticker}.")
    elif alert_type == "price":
        add_price_trace(fig, df, alert, current_price, threshold)

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

    # Convert the figure to an image
    img_bytes = await loop.run_in_executor(
        None, lambda: fig.to_image(format="png", width=1200, height=800, scale=2)
    )
    
    return img_bytes