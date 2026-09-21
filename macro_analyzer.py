import db
import math

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
    
    # Try to find recent swing high/low instead of absolute extremes
    # (Simplified for now)
    
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
            
    return res
