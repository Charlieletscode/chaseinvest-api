import yfinance as yf
import matplotlib.pyplot as plt
import pandas as pd
import talib as ta
import pytz
import numpy as np
import time

# Set timezone to Eastern Time (New York)
eastern_tz = pytz.timezone("US/Eastern")

# Define stock symbols
symbols = ['NIO', 'BABA', 'YMAG', 'TSLY', 'NVDY', 'SPXL', 'TQQQ', 'PLTR', 'CONY']
def fetch_latest_data():
    """Fetch the latest stock data for given symbols."""
    data = yf.download(symbols, period='1d', interval='1m')
    # ✅ Remove failed downloads (possibly delisted stocks)
    failed_stocks = [s for s in symbols if s not in data.columns.get_level_values(0)]
    if failed_stocks:
        print(f"⚠️ Failed downloads: {failed_stocks} (Possibly delisted or no price data available)")

    # ✅ Convert to Eastern Time
    if isinstance(data.columns, pd.MultiIndex):
        data = data.stack(level=1).rename_axis(['Datetime', 'Symbol']).reset_index()

    # ✅ Ensure "Datetime" column is properly formatted
    if "Datetime" in data.columns:
        data["Datetime"] = pd.to_datetime(data["Datetime"]).dt.tz_convert(eastern_tz)

    return data

def detect_buy_limit_points(data):
    """Identify the best buy limit points based on momentum strategy."""
    # ✅ Flatten MultiIndex DataFrame from yfinance
    if isinstance(data.columns, pd.MultiIndex):
        data = data.stack(level=1).rename_axis(['Datetime', 'Symbol']).reset_index()

    # ✅ Ensure required columns exist
    required_cols = {'Open', 'High', 'Low', 'Close', 'Volume'}
    if not required_cols.issubset(data.columns):
        raise ValueError(f"Missing required columns: {required_cols - set(data.columns)}")

    # ✅ Compute Moving Averages
    data['EMA_9'] = data.groupby('Symbol')['Close'].transform(lambda x: x.ewm(span=9, adjust=False).mean())
    data['EMA_21'] = data.groupby('Symbol')['Close'].transform(lambda x: x.ewm(span=21, adjust=False).mean())

    # ✅ VWAP Calculation
    data['VWAP'] = data.groupby('Symbol', group_keys=False).apply(
        lambda x: (x['Volume'] * x['Close']).cumsum() / x['Volume'].cumsum()
    )

    # ✅ Compute Relative Volume (RVOL)
    data['Volume_SMA_50'] = data.groupby('Symbol')['Volume'].transform(lambda x: x.rolling(window=50).mean())
    data['RVOL'] = data['Volume'] / data['Volume_SMA_50']
    data['High_RVOL'] = data['RVOL'] >= 2  # Must be at least 2x the average volume

    # ✅ Detect Candlestick Patterns
    data['Hammer'] = ta.CDLHAMMER(data["Open"], data["High"], data["Low"], data["Close"])
    data['Engulfing'] = ta.CDLENGULFING(data["Open"], data["High"], data["Low"], data["Close"])
    data['MorningStar'] = ta.CDLMORNINGSTAR(data["Open"], data["High"], data["Low"], data["Close"])

    # ✅ Filter for the first trading hour (9:30 AM - 11:30 AM ET)
    # data = data[(data['Datetime'].dt.time >= pd.to_datetime("09:30:00").time()) &
    #             (data['Datetime'].dt.time <= pd.to_datetime("11:30:00").time())]

    # ✅ Identify First Pullback (Bull Flag Formation)
    data['Bull_Flag'] = (data['Close'].shift(1) > data['Close']) & (data['Close'] > data['EMA_9'])

    # ✅ Confirm EMA & VWAP Support
    data['EMA_Support'] = (data['Close'] > data['EMA_9']) & (data['Close'] > data['EMA_21'])
    data['VWAP_Support'] = data['Close'] > data['VWAP']

    # ✅ Identify Buy Signal
    data['Buy_Signal'] = data['Bull_Flag'] & data['EMA_Support'] & data['VWAP_Support'] & data['High_RVOL']

    return data[data['Buy_Signal']]

def monitor_stock(symbol):
    """Continuously monitor stock data and detect buy limit points."""
    global buy_limit_data

    while True:
        data = fetch_latest_data(symbol)
        buy_point = detect_buy_limit_points(data, symbol)

        if buy_point:
            # Update the global DataFrame
            buy_limit_data = pd.concat([buy_limit_data, pd.DataFrame([buy_point])]).drop_duplicates(subset=["Symbol"], keep="last")

        # ✅ Print updated buy limit points
        print("\n📊 Updated Buy Limit Points:")
        print(buy_limit_data)

        time.sleep(1)  # Run every second

# ✅ Fetch & Process Data
print("\n🔍 Fetching latest data...")
data = fetch_latest_data()

# ✅ Detect Buy Limit Points
buy_limit_data = detect_buy_limit_points(data)

buy_limit_points = buy_limit_data[buy_limit_data['Buy_Signal'] == 1].groupby("Symbol")["Close"].min().reset_index()
buy_limit_points.rename(columns={"Close": "Limit Buy Point"}, inplace=True)

# ✅ Show Results
print("\n📊 Best Buy Limit Points Identified:")
if buy_limit_data.empty:
    print("❌ No valid buy signals found.")
else:
    print(buy_limit_data[['Datetime', 'Symbol', 'Close', 'VWAP', 'EMA_9', 'EMA_21', 'High_RVOL', 'Bull_Flag', 'Buy_Signal']])
print(buy_limit_points)