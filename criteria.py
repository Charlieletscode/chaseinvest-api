import yfinance as yf
import requests
import concurrent.futures
from datetime import datetime, timedelta
from dateutil import parser
import re
import os
ALPHA_VANTAGE_API_KEY = "X5Q6LAGRT4V90DWO"
global globalStocks
# ** List of stocks to scan **
stock_list = [
    "APLY", "TSLY", "NVDY", "AMDY", "MSFO", "SPXL", "TQQQ", "AMZY", "GOOY",
    "PLTR", "BABA", "NIO", "FBY", "CONY", "NFLY", "DISO", "XOMO", "JPMO",
    "PYPY", "SQY", "MRNY", "AIYY", "MSTY", "YMAG", "YMAX", "QUBT", "RUM", "GME", "CRMD"]

fallback_map = {
    "APLY": "AAPL", "TSLY": "TSLA", "NVDY": "NVDA", "AMDY": "AMD", "MSFO": "MSFT",
    "SPXL": "SPY", "TQQQ": "QQQ", "AMZY": "AMZN", "GOOY": "GOOGL", "FBY": "META",
    "CONY": "COIN", "NFLY": "NFLX", "DISO": "DIS", "XOMO": "XOM", "JPMO": "JPM",
    "PYPY": "PYPL", "SQY": "SQ", "MRNY": "MRNA", "AIYY": "AI", "MSTY": "MSTR"
}

def check_fallback_float(symbol):
    """Fallback check for x1 stocks if x2 or x3 has no float data"""
    return fallback_map.get(symbol, symbol)  # Return fallback symbol or the original symbol

def get_stock_float(symbol):
    """Fetch float shares from Alpha Vantage and Yahoo Finance, and normalize score (0-10)."""
    # print(f"Checking float for symbol: {symbol}")
    # Resolve fallback symbol
    resolved_symbol = check_fallback_float(symbol)
    if resolved_symbol != symbol:
        return get_stock_float(resolved_symbol)  # Re-run with fallback stock

    # **Fallback to Yahoo Finance**
    try:
        stock = yf.Ticker(symbol)
        info = stock.info

        if "floatShares" in info:
            float_val = info["floatShares"] / 1e6  # Convert to millions
            float_score = min(10, max(0, (100 - float_val) / 10))

            print(f"🔍 {symbol} (Yahoo Finance) | Float: {float_val:.2f}M | Score: {float_score}")
            target_float = 100.0
            difference = abs(float_val - target_float)
            score = max(0, 10 - (difference / 10))
            return float_score

    except Exception as e:
        print(f"⚠️ Yahoo Finance error for {symbol}: {e}")

    # Return 0 if no valid float data is found
    return 0
def check_fallback_float(symbol, visited=None):
    """Fallback check for x1 stocks if x2 or x3 has no float data."""
    if visited is None:
        visited = set()
    if symbol in visited:
        raise ValueError(f"Circular reference detected for symbol: {symbol}")
    visited.add(symbol)
    base_symbol = fallback_map.get(symbol)
    if base_symbol:
        return check_fallback_float(base_symbol, visited)
    return symbol

def check_moving_averages(symbol):
    """Ensure stock is above the 50 & 200 SMA, with fallback if data is missing."""
    
    # Get stock data
    resolved_symbol = check_fallback_float(symbol)
    stock = yf.Ticker(resolved_symbol)
    df = stock.history(period="1y")  # Download 1 year of data

    # Ensure we have enough data
    if len(df) < 200:  
        print(f"⚠️ {resolved_symbol} - Not enough data for moving averages (rows={len(df)})")
        return 0

    # Calculate Moving Averages
    df["SMA_50"] = df["Close"].rolling(window=50).mean()
    df["SMA_200"] = df["Close"].rolling(window=200).mean()

    # Drop rows with NaN values in SMA columns
    df = df.dropna(subset=["SMA_50", "SMA_200"])  

    if df.empty:
        print(f"⚠️ {resolved_symbol} - Insufficient data for moving averages.")
        return 0

    # Get latest values
    latest_price = df["Close"].iloc[-1]
    latest_sma50 = df["SMA_50"].iloc[-1]
    latest_sma200 = df["SMA_200"].iloc[-1]

    # Assign score
    if latest_price > latest_sma50 and latest_price > latest_sma200:
        return 10  # Strong uptrend
    elif latest_price > latest_sma50:
        return 5  # Medium uptrend
    else:
        return 0  # No uptrend

### **3️⃣ Check Relative Volume (RVOL Score: 0-10)**
def check_relative_volume(symbol):
    """Compare today's volume to the average"""
    stock = yf.Ticker(symbol)
    df = stock.history(period="5d", interval="5m")
    if df.empty:
        return 0
    avg_vol = df["Volume"].mean()
    latest_vol = df["Volume"].iloc[-1]
    rvol = latest_vol / avg_vol if avg_vol > 0 else 0
    return min(10, max(0, rvol * 5))  # Normalize score (0-10)

### **4️⃣ Check for Fundamental Catalysts (Score: 0-10, 0 if bad news)**
def get_stock_news(symbol):
    """Fetch latest news from Yahoo Finance"""
    try:
        url = f"https://query1.finance.yahoo.com/v1/finance/search?q={symbol}"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers).json()
        return [{"title": art["title"], "link": art["link"]} for art in response.get("news", [])[:3]]
    except Exception as e:
        print(f"Error fetching news for {symbol}: {e}")
    return []


def extract_date_from_title(title):
    """Extracts a date from a news title, handling multiple formats."""
    title = title.lower()

    # **Common date patterns found in news headlines**
    date_patterns = [
        r"\b(?:mon|tue|wed|thu|fri|sat|sun),?\s+(\w{3,9}\s+\d{1,2},\s+\d{4})\b",  # Example: "Fri, March 14, 2025"
        r"\b(\d{1,2}\s+\w{3,9}\s+\d{4})\b",  # Example: "14 March 2025"
        r"\b(\w{3,9}\s+\d{1,2},\s+\d{4})\b",  # Example: "March 14, 2025"
        r"\b(\d{4}-\d{2}-\d{2})\b",  # Example: "2025-03-14"
    ]

    for pattern in date_patterns:
        match = re.search(pattern, title)
        if match:
            try:
                extracted_date = match.group(1)
                return parser.parse(extracted_date).strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                continue  # Skip if parsing fails

    return None  # No valid date found

def has_catalyst(news_list):
    """Check if news contains a positive or negative catalyst and extract date from title."""
    positive_keywords = ["earnings", "FDA", "merger", "acquisition", "approval", "partnership", "investment"]
    negative_keywords = ["lawsuit", "fraud", "scandal", "downgrade", "investigation", "layoff", "bankruptcy"]

    score = 0
    now = datetime.utcnow()

    for news in news_list:
        title = news["title"].lower()
        
        # **Extract date from title**
        news_time_str = extract_date_from_title(news["title"])
        if news_time_str:
            news_time = datetime.strptime(news_time_str, "%Y-%m-%d %H:%M:%S")
        else:
            # print(f"⚠️ No date found in title: '{news['title']}'. Assigning 2 days.")
            news_time = now - timedelta(days=2)  # Assume it's old (1 year ago)

        # **If negative news is found, return 0 immediately**
        if any(word in title for word in negative_keywords):
            return 0

        # **If positive catalyst is found, score based on recency**
        if any(word in title for word in positive_keywords):
            time_diff = (now - news_time).total_seconds() / 3600  # Convert to hours
            
            # **Scoring: More recent news gets higher weight**
            if time_diff <= 6:     # Last 6 hours → Very Strong
                score += 5
            elif time_diff <= 12:  # 6-12 hours → Strong
                score += 4
            elif time_diff <= 24:  # 12-24 hours → Moderate
                score += 3
            elif time_diff <= 48:  # 24-48 hours → Weak
                score += 2
            else:  # Older than 2 days → Very Weak
                score += 1

    return min(10, score)  # Max score is 10

### **5️⃣ Scan Stocks & Rank by Score**
def scan_stocks():
    """Filter stocks and rank by total score"""
    stock_scores = []
    
    with concurrent.futures.ThreadPoolExecutor() as executor:
        results = executor.map(lambda sym: {
            "Symbol": sym,
            "Float_Score": get_stock_float(sym),
            "MAs_Score": check_moving_averages(sym),
            "RVOL_Score": check_relative_volume(sym),
            "News": get_stock_news(sym),
        }, stock_list)

    for stock in results:
        stock["Catalyst_Score"] = has_catalyst(stock["News"])
        
        # **Total Score (out of 40, normalize to 10)**
        total_score = stock["Float_Score"] + stock["MAs_Score"] + stock["RVOL_Score"] + stock["Catalyst_Score"]
        
        # **Total Score (out of 40, normalize to 10)**
        total_score = stock["Float_Score"] + stock["MAs_Score"] + stock["RVOL_Score"] + stock["Catalyst_Score"]
        stock["Final_Score"] = round((total_score / 40) * 10, 2)  # Normalize to 10

        stock_scores.append(stock)

    # **Sort stocks by Final Score (descending)**
    stock_scores.sort(key=lambda x: x["Final_Score"], reverse=True)

    # **Find the top 10 matches**
    top_matches = stock_scores[:10] if stock_scores else []

    # **Print results**
    print("\n🟢 Top 10 Matching Stocks:")
    if not top_matches or top_matches[0]["Final_Score"] == 0:
        print("❌ No stocks met enough criteria.")
    else:
        for i, stock in enumerate(top_matches, start=1):
            print(f"{i}. {stock['Symbol']} | Score: {stock['Final_Score']}/10")
            print(f"   Float: {stock['Float_Score']}/10 | RVOL: {stock['RVOL_Score']}/10 | MAs: {stock['MAs_Score']}/10 | Catalyst: {stock['Catalyst_Score']}/10")
            for news in stock["News"]:
                print(f"   📰 {news['title']} → {news['link']}")
    
        symbol = [stock['Symbol'] for stock in top_matches]
        print(symbol)
        globalStocks = [stock['Symbol'] for stock in top_matches]
    return top_matches, globalStocks

### **Run Scanner**
print("\n🔎 Running Momentum Stock Scanner...")
top_stocks, globalStocks = scan_stocks()
# print(f"SYMBOL: {os.environ['symbol']}")
