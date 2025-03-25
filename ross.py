import yfinance as yf
import pandas as pd
import talib as ta
import pytz
import time
import threading

# ✅ Set timezone to Eastern Time (New York)
eastern_tz = pytz.timezone("US/Eastern")

# ✅ Define stock symbols


from criteria import globalStocks
# 8005667636

# tmr
symbols = globalStocks
# ✅ Global variables for tracking entries and exits
buy_limit_data = pd.DataFrame()
tracked_positions = pd.DataFrame(columns=["Symbol", "Entry_Price", "Quantity"])

### **1️⃣ Fetch Stock Data**
def fetch_latest_data():
    """Fetch the latest stock data for given symbols."""
    print("🔄 Fetching stock data from Yahoo Finance...")
    try:
        data = yf.download(symbols, period='1d', interval='1m', prepost=True)  
    except Exception as e:
        print(f"❌ Error fetching data: {e}")
        return pd.DataFrame()

    if data.empty:
        print("❌ No data returned from Yahoo Finance.")
        return pd.DataFrame()

    print(f"✅ Data Fetched:\n{data.tail(5)}")

    # ✅ Convert MultiIndex to normal DataFrame
    if isinstance(data.columns, pd.MultiIndex):
        data = data.stack(level=1, future_stack=True).rename_axis(['Datetime', 'Symbol']).reset_index()

    # ✅ Ensure Datetime column is in Eastern Time
    if "Datetime" in data.columns:
        data["Datetime"] = pd.to_datetime(data["Datetime"]).dt.tz_convert(eastern_tz)
    return data

### **2️⃣ Detect Buy Signals**
def detect_buy_limit_points(data):
    """Identify buy signals based on strategy."""
    if data.empty:
        print("❌ No data available for buy signal detection.")
        return pd.DataFrame()

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

    # ✅ Identify First Pullback (Bull Flag Formation)
    data['Bull_Flag'] = (data['Close'].shift(1) > data['Close']) & (data['Close'] > data['EMA_9'])

    # ✅ Confirm EMA & VWAP Support
    data['EMA_Support'] = (data['Close'] > data['EMA_9']) & (data['Close'] > data['EMA_21'])
    data['VWAP_Support'] = data['Close'] > data['VWAP']

    # ✅ Identify Buy Signal
    data['Buy_Signal'] = data['Bull_Flag'] & data['EMA_Support'] & data['VWAP_Support'] & data['High_RVOL']

    buy_signals = data[data['Buy_Signal']]
    
    if buy_signals.empty:
        print("❌ No buy signals detected.")
    else:
        print(f"✅ Buy signals detected:\n{buy_signals[['Symbol', 'Close', 'VWAP', 'EMA_9', 'EMA_21']].head(5)}")

    return buy_signals

### **3️⃣ Detect Exit Signals**
def detect_exit_indicators(data):
    """Find exit indicators for tracked positions."""
    global tracked_positions

    if tracked_positions.empty:
        print("❌ No active trades to monitor.")
        return []

    exit_signals = []
    for _, position in tracked_positions.iterrows():
        symbol = position["Symbol"]
        entry_price = position["Entry_Price"]

        symbol_data = data[data["Symbol"] == symbol]
        if symbol_data.empty:
            print(f"⚠️ No data for {symbol}. Skipping exit check.")
            continue

        latest_price = symbol_data.iloc[-1]["Close"]
        print(f"🔍 Checking {symbol} | Entry: {entry_price:.2f} | Current: {latest_price:.2f}")

        first_red_candle = symbol_data.iloc[-1]["Close"] < symbol_data.iloc[-2]["Close"]
        extension_spike = (latest_price - entry_price) >= (entry_price * 0.03)

        # ✅ Exit #1: Take profit at 2% gain
        if latest_price >= entry_price * 1.02:
            exit_signals.append((symbol, latest_price, "Take Profit (Sell 1/2)"))

        # ✅ Exit #2: First red candle
        elif first_red_candle:
            exit_signals.append((symbol, latest_price, "First Red Candle (Exit All)"))

        # ✅ Exit #3: Extension spike
        elif extension_spike:
            exit_signals.append((symbol, latest_price, "Extension Bar (Sell All)"))

    if not exit_signals:
        print("❌ No exit signals detected.")

    return exit_signals

### **4️⃣ Trading Execution & Monitoring**
def update_buy_limit_points():
    """Monitor & execute trades using Ross's Gap & Go strategy."""
    global buy_limit_data
    global tracked_positions

    while True:
        print("\n🔍 Fetching latest stock data...")
        data = fetch_latest_data()
        if data.empty:
            print("⚠️ No new data fetched. Retrying...")
            time.sleep(5)
            continue

        buy_limit_data = detect_buy_limit_points(data)

        if not buy_limit_data.empty:
            buy_limit_points = buy_limit_data.groupby("Symbol")["Close"].min().reset_index()
            buy_limit_points.rename(columns={"Close": "Limit Buy Point"}, inplace=True)
            print("\n📊 Best Buy Limit Points Identified:")
            print(buy_limit_points)

            # ✅ Execute trades
            for _, row in buy_limit_points.iterrows():
                symbol = row["Symbol"]
                if symbol not in tracked_positions["Symbol"].values:
                    tracked_positions = pd.concat([
                        tracked_positions,
                        pd.DataFrame([[symbol, row["Limit Buy Point"], 1]], columns=["Symbol", "Entry_Price", "Quantity"])
                    ], ignore_index=True)

        # ✅ Detect Exit Indicators
        exit_signals = detect_exit_indicators(data)
        if exit_signals:
            print("\n🚨 Exit Indicators Detected:")
            for exit_signal in exit_signals:
                print(f"🔴 {exit_signal[0]} | Price: {exit_signal[1]:.2f} | Signal: {exit_signal[2]}")

        time.sleep(5)  # ✅ Fetch data every 5 seconds

# ✅ Start Trading Thread
buy_limit_thread = threading.Thread(target=update_buy_limit_points, daemon=True)
buy_limit_thread.start()

# ✅ Prevent script from exiting
while True:
    time.sleep(1)  # Keeps the main thread running
