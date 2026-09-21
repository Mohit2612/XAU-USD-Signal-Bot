import db
import math
import time
import requests
import xml.etree.ElementTree as ET
import pytz
from datetime import datetime

NEWS_CACHE = {"data": [], "last_fetched": 0}

def fetch_high_impact_news():
    global NEWS_CACHE
    current_time = time.time()
    # Cache for 4 hours (14400 seconds)
    if current_time - NEWS_CACHE["last_fetched"] < 14400 and NEWS_CACHE["data"]:
        return NEWS_CACHE["data"]
        
    try:
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return NEWS_CACHE["data"]
            
        root = ET.fromstring(response.content)
        news_list = []
        
        # FF XML usually uses Eastern Time (ET) for the time field
        eastern = pytz.timezone('US/Eastern')
        
        for event in root.findall('event'):
            country = event.find('country').text if event.find('country') is not None else ""
            impact = event.find('impact').text if event.find('impact') is not None else ""
            title = event.find('title').text if event.find('title') is not None else ""
            date_str = event.find('date').text if event.find('date') is not None else ""
            time_str = event.find('time').text if event.find('time') is not None else ""
            
            if country in ("USD", "INR", "EUR", "GBP") and impact == "High" and time_str and date_str:
                if time_str.lower() == "all day" or time_str.lower() == "tentative":
                    continue
                try:
                    dt_str = f"{date_str} {time_str}"
                    dt_obj = datetime.strptime(dt_str, "%m-%d-%Y %I:%M%p")
                    dt_aware = eastern.localize(dt_obj)
                    news_list.append({
                        "title": title,
                        "time": dt_aware,
                        "country": country
                    })
                except Exception:
                    pass
                    
        NEWS_CACHE["data"] = news_list
        NEWS_CACHE["last_fetched"] = current_time
        return news_list
    except Exception as e:
        print(f"News fetch error: {e}")
        return NEWS_CACHE["data"]

def check_news_block(symbol="XAU/USD"):
    news_list = fetch_high_impact_news()
    if not news_list:
        return False, ""
        
    now = datetime.now(pytz.utc)
    for news in news_list:
        # Check if the news affects the current symbol
        affects = False
        if "USD" in symbol and news["country"] == "USD": affects = True
        if "EUR" in symbol and news["country"] == "EUR": affects = True
        if "GBP" in symbol and news["country"] == "GBP": affects = True
        
        if not affects:
            continue
            
        news_time_utc = news["time"].astimezone(pytz.utc)
        time_diff = (news_time_utc - now).total_seconds() / 60.0
        
        # Block 30 mins before and 30 mins after high impact news
        if -30 <= time_diff <= 30:
            return True, f"[{news['country']}] {news['title']}"
            
    return False, ""


def calculate_ema(values, period):
    if len(values) < period:
        return sum(values) / len(values) if values else 0

    multiplier = 2 / (period + 1)
    ema = sum(values[:period]) / period  # SMA seed

    for val in values[period:]:
        ema = (val - ema) * multiplier + ema

    return round(ema, 4)

def find_support_resistance(candles):
    """
    Find major support and resistance levels from the given candles.
    Uses a simple clustering/swing approach.
    """
    if not candles:
        return None, None
        
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    
    # Simple approach: max high and min low over the period
    res = max(highs)
    sup = min(lows)
    
    return sup, res

def analyze_macro_trend(symbol):
    """
    Analyzes macro trend using the last 7-14 days of 1H candles from DB.
    """
    # Fetch last 300 1H candles (roughly 12 days)
    candles_1h = db.get_historical_candles(symbol, "1h", limit=300)
    
    if not candles_1h or len(candles_1h) < 50:
        return {
            "bias": "NEUTRAL",
            "support": None,
            "resistance": None,
            "prediction": "Not enough historical data."
        }
        
    closes = [c["close"] for c in candles_1h]
    current_price = closes[-1]
    
    # Use 50-EMA and 200-EMA on 1H for macro trend
    ema50 = calculate_ema(closes, 50)
    ema200 = calculate_ema(closes, 200) if len(closes) >= 200 else calculate_ema(closes, len(closes)-1)
    
    bias = "NEUTRAL"
    if ema50 > ema200 and current_price > ema50:
        bias = "BULLISH"
    elif ema50 < ema200 and current_price < ema50:
        bias = "BEARISH"
        
    # Find support/resistance over the last 100 hours
    sup, res = find_support_resistance(candles_1h[-100:])
    
    prediction = f"Trend is {bias}."
    if bias == "BULLISH" and res:
        prediction += f" Likely to test resistance at {res:.2f}."
    elif bias == "BEARISH" and sup:
        prediction += f" Likely to test support at {sup:.2f}."
    else:
        prediction += " Ranging between support and resistance."
        
    return {
        "bias": bias,
        "support": sup,
        "resistance": res,
        "prediction": prediction,
        "ema50": ema50,
        "ema200": ema200
    }
