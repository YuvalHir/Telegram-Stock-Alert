import logging
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf
from pytz import timezone
from bot_core.utils.helpers import market_is_open

logger = logging.getLogger(__name__)

class StockDataService:
    """A service for fetching stock data using yfinance."""

    def download_intraday_data(self, tickers: list, period: str = "1d", interval: str = "1m", **kwargs):
        """
        Downloads intraday data for a list of tickers.
        Wraps the yf.download call.
        """
        logger.info(f"Downloading intraday data for tickers: {tickers}")
        try:
            data = yf.download(
                tickers,
                period=period,
                interval=interval,
                group_by="ticker",
                auto_adjust=True,
                threads=True,
                progress=False,
                **kwargs
            )
            return data
        except Exception as e:
            logger.error(f"Error in yfinance download for {tickers}: {e}")
            return pd.DataFrame() # Return empty DataFrame on error

    def get_complete_daily_data(self, ticker, start_date, end_date):
        """
        Downloads historical daily data and appends today's aggregated candle (from intraday data)
        if today's candle is missing.
        """
        # yfinance's 'end' parameter is exclusive. To get data for a single day,
        # we need to set the end date to the next day.
        effective_end_date = end_date
        if start_date == end_date:
            effective_end_date = end_date + timedelta(days=1)
        
        df = yf.download(ticker, start=start_date, end=effective_end_date)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
        tz = timezone('America/New_York')
        today_date = datetime.now(tz).date()
        # Only try to append today's candle if the market is open and the daily data is outdated
        if (df.empty or df.index[-1].date() < today_date) and market_is_open():
            today_str = today_date.strftime("%Y-%m-%d")
            next_day_str = (today_date + timedelta(days=1)).strftime("%Y-%m-%d")
            df_intraday = yf.download(ticker, start=today_str, end=next_day_str, interval="1m", progress=False)
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

    def calculate_sma(self, ticker, period=20):
        """Calculates the Simple Moving Average (SMA) for a given ticker."""
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period=f"{period * 3}d")
            if hist.empty or len(hist['Close']) < period:
                logger.warning(f"Not enough data for {ticker} to calculate {period}-day SMA. Found {len(hist['Close'])} days.")
                # Attempt to fetch with a longer history just in case of non-trading days
                hist_longer = stock.history(period=f"{period * 5}d")
                if len(hist_longer['Close']) >= period:
                    closes = hist_longer['Close'].tail(period)
                    return closes.mean()
                return None
            
            closes = hist['Close'].tail(period)
            return closes.mean()
        except Exception as e:
            logger.error(f"Error calculating SMA for {ticker}: {e}")
            return None

    def get_multiple_market_info(self, symbols):
        """
        Downloads and formats market data for a list of symbols.
        """
        info = {}
        if not symbols:
            return info
        try:
            # Use a short period for efficiency
            data_1d = yf.download(
                " ".join(symbols), 
                period="5d", 
                interval="1d", 
                group_by="ticker", 
                threads=True,
                progress=False
            )
            for symbol in symbols:
                # Access data which might be under a multi-level index
                df = data_1d.get(symbol) if len(symbols) > 1 else data_1d
                
                if df is not None and not df.empty:
                    # Get the most recent valid closing price
                    last_close = df['Close'].dropna().iloc[-1]
                    # Get the opening price of the same day as the last close
                    last_open = df['Open'].loc[df['Close'].dropna().index[-1]]
                    
                    change = last_close - last_open
                    percent_change = (change / last_open) * 100 if last_open else 0
                    arrow = "📈" if change >= 0 else "📉"
                    info[symbol] = f"{last_close:.2f} {arrow} {abs(percent_change):.2f}%"
                else:
                    info[symbol] = "N/A"
        except Exception as e:
            logger.error(f"Error fetching 1d data for market info: {e}")
            for symbol in symbols:
                info.setdefault(symbol, "N/A")
        
        return info