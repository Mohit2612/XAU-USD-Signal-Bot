"""
data_layer.py — Clean data interface for the Mentor Persona Engine.

This module wraps ALL existing market-data and indicator functions behind
two public entry-points:

    get_market_snapshot(pair, timeframe)  → normalized dict
    get_historical(pair, timeframe, bars) → list of OHLCV dicts

Every function below is extracted *verbatim* from the original bot.py so
the underlying API calls and logic are 100 % identical.
"""

import os
import sys
import requests
import time
import json
import math
from datetime import datetime, date, timedelta
from collections import deque
import pytz
import xml.etree.ElementTree as ET

import db
import macro_analyzer

# Fix Windows console encoding for emojis
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# ============================================
# CONFIGURATION (from env only — no hardcoded keys)
# ============================================
TELEGRAM_TOKEN     = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")
TWELVEDATA_API_KEY = os.environ.get("TWELVEDATA_API_KEY", "")
FINNHUB_API_KEY    = os.environ.get("FINNHUB_API_KEY", "")

# ============================================
# MULTI-ASSET CONFIGURATION REGISTRY
# ============================================
ASSETS = {
    "XAU/USD": {
        "type": "commodity",
        "label": "Gold 🥇",
        "yahoo_symbol": "GC=F",
        "pip_value": 1.0,
        "contract_size": 100,
        "min_fvg": 1.20,
        "equal_level_tol": 0.30,
        "min_sl": 3.0,
        "max_sl": 18.0,
        "rr_ratio": 2.5,
        "use_kill_zones": True,
        "use_asian_sweep": True,
        "min_displacement": 1.5,
        "min_ote_move": 2.0,
        "vwap_threshold": 1.0,
        "wick_min": 1.0,
        "enabled": True,
    },
    "EUR/USD": {
        "type": "forex",
        "label": "EUR/USD 🇪🇺🇺🇸",
        "yahoo_symbol": "EURUSD=X",
        "pip_value": 0.0001,
        "contract_size": 100000,
        "min_fvg": 0.0005,
        "equal_level_tol": 0.0003,
        "min_sl": 0.0010,
        "max_sl": 0.0050,
        "rr_ratio": 2.0,
        "use_kill_zones": True,
        "use_asian_sweep": False,
        "min_displacement": 0.0010,
        "min_ote_move": 0.0020,
        "vwap_threshold": 0.0005,
        "wick_min": 0.0005,
        "enabled": False,
    },
    "GBP/USD": {
        "type": "forex",
        "label": "GBP/USD 🇬🇧🇺🇸",
        "yahoo_symbol": "GBPUSD=X",
        "pip_value": 0.0001,
        "contract_size": 100000,
        "min_fvg": 0.0006,
        "equal_level_tol": 0.0003,
        "min_sl": 0.0012,
        "max_sl": 0.0060,
        "rr_ratio": 2.0,
        "use_kill_zones": True,
        "use_asian_sweep": False,
        "min_displacement": 0.0012,
        "min_ote_move": 0.0025,
        "vwap_threshold": 0.0006,
        "wick_min": 0.0006,
        "enabled": False,
    },
    "USD/JPY": {
        "type": "forex",
        "label": "USD/JPY 🇺🇸🇯🇵",
        "yahoo_symbol": "USDJPY=X",
        "pip_value": 0.01,
        "contract_size": 1000,
        "min_fvg": 0.05,
        "equal_level_tol": 0.03,
        "min_sl": 0.10,
        "max_sl": 0.50,
        "rr_ratio": 2.0,
        "use_kill_zones": True,
        "use_asian_sweep": False,
        "min_displacement": 0.10,
        "min_ote_move": 0.20,
        "vwap_threshold": 0.05,
        "wick_min": 0.05,
        "enabled": False,
    },
    "AUD/USD": {
        "type": "forex",
        "label": "AUD/USD 🇦🇺🇺🇸",
        "yahoo_symbol": "AUDUSD=X",
        "pip_value": 0.0001,
        "contract_size": 100000,
        "min_fvg": 0.0004,
        "equal_level_tol": 0.0003,
        "min_sl": 0.0008,
        "max_sl": 0.0045,
        "rr_ratio": 2.0,
        "use_kill_zones": True,
        "use_asian_sweep": False,
        "min_displacement": 0.0008,
        "min_ote_move": 0.0018,
        "vwap_threshold": 0.0004,
        "wick_min": 0.0004,
        "enabled": False,
    },
    "USD/CAD": {
        "type": "forex",
        "label": "USD/CAD 🇺🇸🇨🇦",
        "yahoo_symbol": "USDCAD=X",
        "pip_value": 0.0001,
        "min_fvg": 0.0004,
        "equal_level_tol": 0.0003,
        "min_sl": 0.0008,
        "max_sl": 0.0045,
        "rr_ratio": 2.0,
        "use_kill_zones": True,
        "use_asian_sweep": False,
        "min_displacement": 0.0008,
        "min_ote_move": 0.0018,
        "vwap_threshold": 0.0004,
        "wick_min": 0.0004,
        "enabled": False,
    },
    "BTC/USD": {
        "type": "crypto",
        "label": "Bitcoin ₿",
        "yahoo_symbol": "BTC-USD",
        "pip_value": 1.0,
        "contract_size": 1,
        "min_fvg": 50.0,
        "equal_level_tol": 30.0,
        "min_sl": 100.0,
        "max_sl": 1000.0,
        "rr_ratio": 2.0,
        "use_kill_zones": False,
        "use_asian_sweep": False,
        "min_displacement": 100.0,
        "min_ote_move": 200.0,
        "vwap_threshold": 50.0,
        "wick_min": 50.0,
        "enabled": False,
    },
    "ETH/USD": {
        "type": "crypto",
        "label": "Ethereum Ξ",
        "yahoo_symbol": "ETH-USD",
        "pip_value": 0.01,
        "min_fvg": 3.0,
        "equal_level_tol": 2.0,
        "min_sl": 5.0,
        "max_sl": 50.0,
        "rr_ratio": 2.0,
        "use_kill_zones": False,
        "use_asian_sweep": False,
        "min_displacement": 5.0,
        "min_ote_move": 10.0,
        "vwap_threshold": 3.0,
        "wick_min": 3.0,
        "enabled": False,
    },
}

IST = pytz.timezone('Asia/Kolkata')

# EMA periods (used by indicator functions)
EMA_FAST = 8
EMA_MID  = 21
EMA_SLOW = 50
ATR_PERIOD = 14

# ============================================
# KILL ZONE DEFINITIONS (IST times)
# ============================================
KILL_ZONES = {
    "LONDON": {"start_h": 12, "start_m": 30, "end_h": 15, "end_m": 30,
               "label": "London Kill Zone 🇬🇧", "risk_mult": 1.0},
    "NEW_YORK": {"start_h": 18, "start_m": 30, "end_h": 21, "end_m": 30,
                 "label": "New York Kill Zone 🗽", "risk_mult": 1.0},
    "LONDON_NY_OVERLAP": {"start_h": 18, "start_m": 30, "end_h": 20, "end_m": 0,
                          "label": "London-NY Overlap ⚡", "risk_mult": 1.0},
}

SILVER_BULLET_WINDOWS = {
    "LDN_OPEN": {"start_h": 13, "start_m": 30, "end_h": 14, "end_m": 30,
                 "label": "Silver Bullet: London Open 🎯"},
    "NY_AM": {"start_h": 20, "start_m": 30, "end_h": 21, "end_m": 30,
              "label": "Silver Bullet: NY AM Session 🎯"},
    "NY_PM": {"start_h": 0, "start_m": 30, "end_h": 1, "end_m": 30,
              "label": "Silver Bullet: NY PM Session 🎯"},
}

ASIAN_SESSION = {"start_h": 4, "start_m": 0, "end_h": 12, "end_m": 30}

# Asian range state
asian_range_high = None
asian_range_low  = None
asian_range_set_date = None


# ============================================
# CONFIG VALIDATION
# ============================================
def validate_config():
    missing = [k for k, v in {
        "TELEGRAM_TOKEN": TELEGRAM_TOKEN,
        "TELEGRAM_CHAT_ID": TELEGRAM_CHAT_ID,
        "TWELVEDATA_API_KEY": TWELVEDATA_API_KEY,
    }.items() if not v]
    if missing:
        print("FATAL: Missing environment variables: " + ", ".join(missing))
        print("Set them before running the bot. Exiting.")
        return False
    return True


# ============================================
# TELEGRAM
# ============================================
def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured; skipping send.")
        return
    url     = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        print(f"Telegram: {r.status_code}")
    except Exception as e:
        print(f"Telegram error: {e}")


# ============================================
# FETCH CANDLES (multi-asset, 3-tier fallback)
# ============================================
def get_candles(symbol="XAU/USD", interval="5m", range_str="5d"):
    td_interval_map = {"1m": "1min", "5m": "5min", "15m": "15min", "1h": "1h"}
    td_interval = td_interval_map.get(interval, "5min")

    exchange_param = "&exchange=OANDA" if symbol == "XAU/USD" else ""
    url = (f"https://api.twelvedata.com/time_series?symbol={symbol}"
           f"{exchange_param}&interval={td_interval}&outputsize=500"
           f"&apikey={TWELVEDATA_API_KEY}")
    try:
        r = requests.get(url, timeout=15)
        data = r.json()

        if "values" not in data:
            print(f"TwelveData Error for {symbol}: {data}. Falling back to alternative APIs...")

            # --- FINNHUB FALLBACK ---
            if FINNHUB_API_KEY and symbol == "XAU/USD":
                fh_interval_map = {"1m": "1", "5m": "5", "15m": "15", "1h": "60"}
                fh_res = fh_interval_map.get(interval, "5")
                end_ts = int(time.time())
                start_ts = end_ts - (10 * 24 * 60 * 60)
                fh_url = (f"https://finnhub.io/api/v1/forex/candle?symbol=OANDA:XAU_USD"
                          f"&resolution={fh_res}&from={start_ts}&to={end_ts}"
                          f"&token={FINNHUB_API_KEY}")
                print("Fetching from Finnhub...")
                try:
                    f_req = requests.get(fh_url, timeout=15)
                    f_data = f_req.json()
                    if f_data.get("s") == "ok":
                        candles = []
                        for i in range(len(f_data['t'])):
                            dt_str = datetime.fromtimestamp(f_data['t'][i]).strftime('%Y-%m-%d %H:%M:%S')
                            candles.append({
                                "datetime": dt_str,
                                "open": str(f_data['o'][i]),
                                "high": str(f_data['h'][i]),
                                "low": str(f_data['l'][i]),
                                "close": str(f_data['c'][i])
                            })
                        return candles[::-1]
                except Exception as e:
                    print(f"Finnhub Error: {e}")

            # --- YAHOO FINANCE FALLBACK ---
            print("Falling back to Yahoo Finance...")
            asset_config = ASSETS.get(symbol, {})
            yahoo_sym = asset_config.get("yahoo_symbol", "GC=F")
            y_url = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
                     f"{yahoo_sym}?interval={interval}&range={range_str}")
            yr = requests.get(y_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            y_data = yr.json()
            if "chart" not in y_data or not y_data["chart"]["result"]:
                return None
            result = y_data['chart']['result'][0]
            timestamps = result.get('timestamp', [])
            quote = result['indicators']['quote'][0]

            candles = []
            for i in range(len(timestamps)):
                if quote['open'][i] is None:
                    continue
                candles.append({
                    "time": datetime.fromtimestamp(timestamps[i]).strftime('%Y-%m-%d %H:%M:%S'),
                    "open": float(quote['open'][i]),
                    "high": float(quote['high'][i]),
                    "low": float(quote['low'][i]),
                    "close": float(quote['close'][i])
                })
            if candles:
                db.save_candles(symbol, interval, candles)
            return candles

        values = data["values"]
        values.reverse()

        candles = []
        for val in values:
            candles.append({
                "time": val["datetime"],
                "open": float(val["open"]),
                "high": float(val["high"]),
                "low": float(val["low"]),
                "close": float(val["close"])
            })
        if candles:
            db.save_candles(symbol, interval, candles)
        return candles
    except Exception as e:
        print(f"Candle fetch error ({symbol}): {e}")
        return None


def get_current_price(symbol="XAU/USD"):
    """Fetch latest price for trade monitoring."""
    candles = get_candles(symbol=symbol, interval="5m", range_str="1d")
    if candles and len(candles) > 0:
        return candles[-1]["close"]
    return None


# ============================================
# KILL ZONE & SESSION ENGINE
# ============================================
def get_active_kill_zone():
    """Check if current time is within a Kill Zone. Returns zone info or None."""
    now = datetime.now(IST)
    h, m = now.hour, now.minute
    current_minutes = h * 60 + m

    active_zone = None
    is_silver_bullet = False

    for zone_name, zone in KILL_ZONES.items():
        zone_start = zone["start_h"] * 60 + zone["start_m"]
        zone_end = zone["end_h"] * 60 + zone["end_m"]
        if zone_start <= current_minutes < zone_end:
            active_zone = {
                "name": zone_name,
                "label": zone["label"],
                "risk_mult": zone["risk_mult"],
            }
            break

    for sb_name, sb in SILVER_BULLET_WINDOWS.items():
        sb_start = sb["start_h"] * 60 + sb["start_m"]
        sb_end = sb["end_h"] * 60 + sb["end_m"]
        if sb_start < sb_end:
            if sb_start <= current_minutes < sb_end:
                is_silver_bullet = True
                if active_zone:
                    active_zone["label"] += f" + {sb['label']}"
                else:
                    active_zone = {
                        "name": sb_name,
                        "label": sb["label"],
                        "risk_mult": 1.0,
                    }
                break
        else:
            if current_minutes >= sb_start or current_minutes < sb_end:
                is_silver_bullet = True
                if active_zone:
                    active_zone["label"] += f" + {sb['label']}"
                else:
                    active_zone = {
                        "name": sb_name,
                        "label": sb["label"],
                        "risk_mult": 1.0,
                    }
                break

    if active_zone:
        active_zone["is_silver_bullet"] = is_silver_bullet

    return active_zone


def is_in_asian_session():
    """Check if currently in Asian session (for range building)."""
    now = datetime.now(IST)
    h, m = now.hour, now.minute
    current_minutes = h * 60 + m
    start = ASIAN_SESSION["start_h"] * 60 + ASIAN_SESSION["start_m"]
    end = ASIAN_SESSION["end_h"] * 60 + ASIAN_SESSION["end_m"]
    return start <= current_minutes < end


def get_session_label():
    """Human-readable session label."""
    zone = get_active_kill_zone()
    if zone:
        return zone["label"]
    now = datetime.now(IST)
    h = now.hour
    if 4 <= h < 12:
        return "Asian Session 🌏 (Building Range)"
    return "Off Hours 🌙 (No Trading)"


# ============================================
# ASIAN RANGE DETECTION & SWEEP
# ============================================
def update_asian_range(candles_5m):
    """Build the Asian session high/low from 5M candles."""
    global asian_range_high, asian_range_low, asian_range_set_date

    today = date.today()
    if asian_range_set_date == today:
        return

    asian_highs = []
    asian_lows = []
    for c in candles_5m:
        try:
            ct = datetime.strptime(c["time"], "%Y-%m-%d %H:%M:%S")
            ct = IST.localize(ct) if ct.tzinfo is None else ct
            h = ct.hour
            if ASIAN_SESSION["start_h"] <= h < ASIAN_SESSION["end_h"]:
                if ct.date() == today:
                    asian_highs.append(c["high"])
                    asian_lows.append(c["low"])
        except Exception:
            continue

    if asian_highs and asian_lows:
        asian_range_high = max(asian_highs)
        asian_range_low = min(asian_lows)
        asian_range_set_date = today
        print(f"📊 Asian Range set: High={asian_range_high:.2f} Low={asian_range_low:.2f}")


def detect_asian_sweep(candles, bias):
    """Detect if price has swept the Asian range (Judas Swing)."""
    if asian_range_high is None or asian_range_low is None:
        return False, 0

    curr = candles[-1]
    prev = candles[-2] if len(candles) >= 2 else None

    if bias == "BULLISH" and prev:
        swept = prev["low"] < asian_range_low
        rejected = curr["close"] > asian_range_low
        strong_rejection = curr["close"] > curr["open"]
        if swept and rejected and strong_rejection:
            return True, 15
    elif bias == "BEARISH" and prev:
        swept = prev["high"] > asian_range_high
        rejected = curr["close"] < asian_range_high
        strong_rejection = curr["close"] < curr["open"]
        if swept and rejected and strong_rejection:
            return True, 15

    return False, 0


# ============================================
# SWING HIGH / LOW DETECTION
# ============================================
def find_swing_highs(candles, lookback=3):
    swings = []
    for i in range(lookback, len(candles) - lookback):
        if all(candles[i]["high"] >= candles[i-j]["high"] and
               candles[i]["high"] >= candles[i+j]["high"]
               for j in range(1, lookback+1)):
            swings.append((i, candles[i]["high"]))
    return swings


def find_swing_lows(candles, lookback=3):
    swings = []
    for i in range(lookback, len(candles) - lookback):
        if all(candles[i]["low"] <= candles[i-j]["low"] and
               candles[i]["low"] <= candles[i+j]["low"]
               for j in range(1, lookback+1)):
            swings.append((i, candles[i]["low"]))
    return swings


# ============================================
# EMA (Exponential Moving Average)
# ============================================
def calculate_ema(values, period):
    """Calculate true EMA (not simple average)."""
    if len(values) < period:
        return sum(values) / len(values) if values else 0
    multiplier = 2 / (period + 1)
    ema = sum(values[:period]) / period
    for val in values[period:]:
        ema = (val - ema) * multiplier + ema
    return round(ema, 4)


def get_ema_confluence(candles):
    """Calculate 8/21/50 EMAs and check alignment."""
    closes = [c["close"] for c in candles]
    if len(closes) < EMA_SLOW:
        return None, None, None, "NEUTRAL", False, 0

    ema8 = calculate_ema(closes, EMA_FAST)
    ema21 = calculate_ema(closes, EMA_MID)
    ema50 = calculate_ema(closes, EMA_SLOW)

    bullish_aligned = ema8 > ema21 > ema50
    bearish_aligned = ema8 < ema21 < ema50

    curr_price = closes[-1]
    if bullish_aligned and curr_price > ema8:
        return ema8, ema21, ema50, "BULLISH", True, 8
    elif bearish_aligned and curr_price < ema8:
        return ema8, ema21, ema50, "BEARISH", True, 8
    elif ema8 > ema21:
        return ema8, ema21, ema50, "BULLISH", False, 3
    elif ema8 < ema21:
        return ema8, ema21, ema50, "BEARISH", False, 3
    else:
        return ema8, ema21, ema50, "NEUTRAL", False, 0


# ============================================
# VWAP (Volume Weighted Average Price)
# ============================================
def calculate_vwap(candles, asset_cfg=None):
    if len(candles) < 5:
        return None, "NEUTRAL", 0
    vwap_thresh = (asset_cfg or {}).get("vwap_threshold", 1.0)
    sum_tpv = 0
    sum_v = 0
    for c in candles:
        typical_price = (c["high"] + c["low"] + c["close"]) / 3
        vol_proxy = max(c["high"] - c["low"], 0.01)
        sum_tpv += typical_price * vol_proxy
        sum_v += vol_proxy
    if sum_v == 0:
        return None, "NEUTRAL", 0
    vwap = round(sum_tpv / sum_v, 6)
    curr_price = candles[-1]["close"]
    if curr_price > vwap + vwap_thresh:
        return vwap, "BULLISH", 10
    elif curr_price < vwap - vwap_thresh:
        return vwap, "BEARISH", 10
    elif curr_price > vwap:
        return vwap, "BULLISH", 5
    elif curr_price < vwap:
        return vwap, "BEARISH", 5
    else:
        return vwap, "NEUTRAL", 0


# ============================================
# OTE — OPTIMAL TRADE ENTRY (Fibonacci 62%-79%)
# ============================================
def detect_ote_zone(candles, bias, asset_cfg=None):
    if len(candles) < 15:
        return False, 0, None, None
    min_ote_move = (asset_cfg or {}).get("min_ote_move", 2.0)
    recent = candles[-15:]
    if bias == "BULLISH":
        low_val = min(c["low"] for c in recent[:-3])
        high_val = max(c["high"] for c in recent[-5:])
        move = high_val - low_val
        if move < min_ote_move:
            return False, 0, None, None
        ote_top = high_val - move * 0.618
        ote_bottom = high_val - move * 0.79
        curr = candles[-1]["close"]
        if ote_bottom <= curr <= ote_top:
            return True, 8, ote_bottom, ote_top
    elif bias == "BEARISH":
        high_val = max(c["high"] for c in recent[:-3])
        low_val = min(c["low"] for c in recent[-5:])
        move = high_val - low_val
        if move < min_ote_move:
            return False, 0, None, None
        ote_bottom = low_val + move * 0.618
        ote_top = low_val + move * 0.79
        curr = candles[-1]["close"]
        if ote_bottom <= curr <= ote_top:
            return True, 8, ote_bottom, ote_top
    return False, 0, None, None


# ============================================
# ATR (Average True Range)
# ============================================
def calculate_atr(candles, period=ATR_PERIOD):
    if len(candles) < period + 1:
        return None
    trs = []
    for i in range(1, len(candles)):
        h, l, pc = candles[i]["high"], candles[i]["low"], candles[i-1]["close"]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    return round(sum(trs[-period:]) / period, 3)


# ============================================
# ADX (Trend Strength)
# ============================================
def calculate_adx(candles, period=14):
    if len(candles) < period * 2:
        return 0
    plus_dm, minus_dm, trs = [], [], []
    for i in range(1, len(candles)):
        up   = candles[i]["high"] - candles[i-1]["high"]
        down = candles[i-1]["low"] - candles[i]["low"]
        plus_dm.append(up if (up > down and up > 0) else 0)
        minus_dm.append(down if (down > up and down > 0) else 0)
        h, l, pc = candles[i]["high"], candles[i]["low"], candles[i-1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))

    def smooth(vals):
        return sum(vals[-period:]) / period if len(vals) >= period else 0

    atr = smooth(trs)
    if atr == 0:
        return 0
    plus_di  = 100 * smooth(plus_dm) / atr
    minus_di = 100 * smooth(minus_dm) / atr
    denom = plus_di + minus_di
    if denom == 0:
        return 0
    dx = 100 * abs(plus_di - minus_di) / denom
    return round(dx, 1)


# ============================================
# MARKET STRUCTURE — BOS & CHoCH
# ============================================
def analyze_structure_bos(candles):
    if len(candles) < 20:
        return "NEUTRAL", None, False

    swing_highs = find_swing_highs(candles[-60:], lookback=3)
    swing_lows  = find_swing_lows(candles[-60:],  lookback=3)

    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return "NEUTRAL", None, False

    curr_price = candles[-1]["close"]
    last_sh    = swing_highs[-1][1]
    last_sl    = swing_lows[-1][1]
    prev_sh    = swing_highs[-2][1]
    prev_sl    = swing_lows[-2][1]

    closes   = [c["close"] for c in candles]
    ema_fast = calculate_ema(closes, 10)
    ema_slow = calculate_ema(closes, 30)
    ema_bias = "BULLISH" if ema_fast > ema_slow else "BEARISH"

    bullish_bos = curr_price > last_sh
    bearish_bos = curr_price < last_sl

    was_bearish  = last_sh < prev_sh and last_sl < prev_sl
    was_bullish  = last_sh > prev_sh and last_sl > prev_sl
    bullish_choch = was_bearish and bullish_bos
    bearish_choch = was_bullish and bearish_bos

    if bullish_choch:
        return "BULLISH", "CHoCH", True
    elif bearish_choch:
        return "BEARISH", "CHoCH", True
    elif bullish_bos and ema_bias == "BULLISH" and last_sh > prev_sh:
        return "BULLISH", "BOS", False
    elif bearish_bos and ema_bias == "BEARISH" and last_sl < prev_sl:
        return "BEARISH", "BOS", False
    elif ema_bias == "BULLISH" and last_sh > prev_sh and last_sl > prev_sl:
        return "BULLISH", None, False
    elif ema_bias == "BEARISH" and last_sh < prev_sh and last_sl < prev_sl:
        return "BEARISH", None, False
    else:
        return "NEUTRAL", None, False


def htf_trend(candles):
    """EMA-based trend for the highest timeframe gate."""
    if len(candles) < 50:
        if len(candles) < 20:
            return "NEUTRAL"
        closes = [c["close"] for c in candles]
        ema_fast = calculate_ema(closes, 10)
        ema_slow = calculate_ema(closes, 20)
        if ema_fast > ema_slow:
            return "BULLISH"
        if ema_fast < ema_slow:
            return "BEARISH"
        return "NEUTRAL"

    closes = [c["close"] for c in candles]
    ema_fast = calculate_ema(closes, 20)
    ema_slow = calculate_ema(closes, 50)
    if ema_fast > ema_slow:
        return "BULLISH"
    if ema_fast < ema_slow:
        return "BEARISH"
    return "NEUTRAL"


# ============================================
# ORDER BLOCK DETECTION
# ============================================
def detect_order_block(candles, bias):
    if len(candles) < 10:
        return None, None, False
    curr_price = candles[-1]["close"]
    if bias == "BULLISH":
        for i in range(len(candles)-3, max(len(candles)-20, 3), -1):
            c = candles[i]
            if c["close"] < c["open"]:
                next_closes = [candles[i+j]["close"] for j in range(1, 3) if i+j < len(candles)]
                if next_closes and max(next_closes) > c["high"]:
                    ob_high = c["high"]
                    ob_low  = c["low"]
                    price_in_ob = ob_low <= curr_price <= ob_high
                    return ob_high, ob_low, price_in_ob
    elif bias == "BEARISH":
        for i in range(len(candles)-3, max(len(candles)-20, 3), -1):
            c = candles[i]
            if c["close"] > c["open"]:
                next_closes = [candles[i+j]["close"] for j in range(1, 3) if i+j < len(candles)]
                if next_closes and min(next_closes) < c["low"]:
                    ob_high = c["high"]
                    ob_low  = c["low"]
                    price_in_ob = ob_low <= curr_price <= ob_high
                    return ob_high, ob_low, price_in_ob
    return None, None, False


# ============================================
# EQUAL HIGHS / EQUAL LOWS (LIQUIDITY ZONES)
# ============================================
def detect_liquidity_zones(candles, asset_cfg=None):
    if len(candles) < 10:
        return False, False, False, False
    eq_tol = (asset_cfg or {}).get("equal_level_tol", 0.30)
    recent      = candles[-30:]
    highs       = [c["high"] for c in recent[:-2]]
    lows        = [c["low"]  for c in recent[:-2]]
    last_high   = candles[-1]["high"]
    last_low    = candles[-1]["low"]

    equal_highs = False
    swept_high  = False
    for i in range(len(highs)):
        for j in range(i+1, len(highs)):
            if abs(highs[i] - highs[j]) <= eq_tol:
                equal_highs = True
                if last_high > max(highs[i], highs[j]):
                    swept_high = True

    equal_lows = False
    swept_low  = False
    for i in range(len(lows)):
        for j in range(i+1, len(lows)):
            if abs(lows[i] - lows[j]) <= eq_tol:
                equal_lows = True
                if last_low < min(lows[i], lows[j]):
                    swept_low = True

    return equal_highs, equal_lows, swept_high, swept_low


# ============================================
# FVG WITH SIZE FILTER
# ============================================
def detect_fvg(candles, asset_cfg=None):
    if len(candles) < 3:
        return None, 0
    min_fvg = (asset_cfg or {}).get("min_fvg", 1.20)
    for i in range(len(candles)-3, max(len(candles)-10, 0), -1):
        c1 = candles[i]
        c3 = candles[i+2]
        if c1["high"] < c3["low"]:
            gap_size = c3["low"] - c1["high"]
            if gap_size >= min_fvg:
                if candles[-1]["close"] > c1["high"]:
                    return "BULLISH_FVG", 8
        if c1["low"] > c3["high"]:
            gap_size = c1["low"] - c3["high"]
            if gap_size >= min_fvg:
                if candles[-1]["close"] < c1["low"]:
                    return "BEARISH_FVG", 8
    return None, 0


# ============================================
# LIQUIDITY GRAB
# ============================================
def detect_liquidity_grab(candles, asset_cfg=None):
    if len(candles) < 10:
        return None, 0
    recent       = candles[-10:]
    prev         = candles[-2]
    curr         = candles[-1]
    recent_highs = [c["high"] for c in recent[:-2]]
    recent_lows  = [c["low"]  for c in recent[:-2]]
    if not recent_highs or not recent_lows:
        return None, 0
    max_high = max(recent_highs)
    min_low  = min(recent_lows)
    wick_min = (asset_cfg or {}).get("wick_min", 1.0)
    grab, score = None, 0
    if prev["high"] > max_high:
        wick_size = prev["high"] - max(prev["open"], prev["close"])
        if wick_size >= wick_min and curr["close"] < curr["open"]:
            grab, score = "BEARISH_GRAB", 2
    if prev["low"] < min_low:
        wick_size = min(prev["open"], prev["close"]) - prev["low"]
        if wick_size >= wick_min and curr["close"] > curr["open"]:
            grab, score = "BULLISH_GRAB", 2
    return grab, score


# ============================================
# CANDLESTICK PATTERN (enhanced)
# ============================================
def check_candle_pattern(candles, asset_cfg=None):
    if len(candles) < 3:
        return None, 0
    c1 = candles[-3]
    c2 = candles[-2]
    c3 = candles[-1]

    if (c2["open"] < c2["close"] and c3["open"] > c3["close"] and
            c3["open"] >= c2["close"] and c3["close"] <= c2["open"]):
        body_size = abs(c3["open"] - c3["close"])
        min_disp = (asset_cfg or {}).get("min_displacement", 1.5)
        if body_size > min_disp:
            return "BEARISH_ENGULF", 3
        return "BEARISH_ENGULF", 2

    if (c2["open"] > c2["close"] and c3["open"] < c3["close"] and
            c3["open"] <= c2["close"] and c3["close"] >= c2["open"]):
        body_size = abs(c3["open"] - c3["close"])
        min_disp = (asset_cfg or {}).get("min_displacement", 1.5)
        if body_size > min_disp:
            return "BULLISH_ENGULF", 3
        return "BULLISH_ENGULF", 2

    if (c1["close"] > c1["open"] and
        abs(c2["close"] - c2["open"]) < abs(c1["close"] - c1["open"]) * 0.3 and
        c3["close"] < c3["open"] and c3["close"] < c1["open"]):
        return "EVENING_STAR", 3

    if (c1["close"] < c1["open"] and
        abs(c2["close"] - c2["open"]) < abs(c1["close"] - c1["open"]) * 0.3 and
        c3["close"] > c3["open"] and c3["close"] > c1["open"]):
        return "MORNING_STAR", 3

    if (c3["high"] - max(c3["open"], c3["close"]) >
            2 * abs(c3["open"] - c3["close"]) and
            abs(c3["open"] - c3["close"]) > 0):
        return "SHOOTING_STAR", 1

    if (min(c3["open"], c3["close"]) - c3["low"] >
            2 * abs(c3["open"] - c3["close"]) and
            abs(c3["open"] - c3["close"]) > 0):
        return "HAMMER", 1

    return None, 0


# ============================================
# RSI
# ============================================
def calculate_rsi(candles, period=14):
    if len(candles) < period + 1:
        return 50
    closes = [c["close"] for c in candles[-(period+1):]]
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i-1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_g = sum(gains) / period
    avg_l = sum(losses) / period
    if avg_l == 0:
        return 100
    return round(100 - (100 / (1 + avg_g / avg_l)), 2)


# ============================================
# RSI DIVERGENCE
# ============================================
def detect_rsi_divergence(candles, bias):
    if len(candles) < 30:
        return False
    rsi_series = []
    for k in range(len(candles) - 20, len(candles)):
        rsi_series.append((k, calculate_rsi(candles[:k+1])))
    lows  = find_swing_lows(candles[-20:], lookback=2)
    highs = find_swing_highs(candles[-20:], lookback=2)

    def rsi_at(local_idx):
        real_idx = len(candles) - 20 + local_idx
        for k, v in rsi_series:
            if k == real_idx:
                return v
        return 50

    if bias == "BULLISH" and len(lows) >= 2:
        (i1, p1), (i2, p2) = lows[-2], lows[-1]
        if p2 < p1 and rsi_at(i2) > rsi_at(i1):
            return True
    if bias == "BEARISH" and len(highs) >= 2:
        (i1, p1), (i2, p2) = highs[-2], highs[-1]
        if p2 > p1 and rsi_at(i2) < rsi_at(i1):
            return True
    return False


# ============================================
# MOMENTUM & DISPLACEMENT FILTER
# ============================================
def check_momentum(candles, bias):
    if len(candles) < 5:
        return False, 0
    score = 0
    last3 = candles[-3:]
    if bias == "BULLISH":
        consec = sum(1 for c in last3 if c["close"] > c["open"])
        if consec >= 3:
            score += 3
        elif consec >= 2:
            score += 1
    elif bias == "BEARISH":
        consec = sum(1 for c in last3 if c["close"] < c["open"])
        if consec >= 3:
            score += 3
        elif consec >= 2:
            score += 1
    c = candles[-1]
    body = abs(c["close"] - c["open"])
    upper_wick = c["high"] - max(c["open"], c["close"])
    lower_wick = min(c["open"], c["close"]) - c["low"]
    total_wick = upper_wick + lower_wick
    if body > 0 and total_wick > 0:
        ratio = body / total_wick
        if ratio > 2.0:
            score += 2
    return score > 0, score


# ============================================
# MACD
# ============================================
def calculate_macd(candles):
    if len(candles) < 35:
        return 0, 0, 0
    closes = [c["close"] for c in candles]
    ema12 = calculate_ema(closes, 12)
    ema26 = calculate_ema(closes, 26)
    macd_line = ema12 - ema26
    macd_series = []
    for i in range(26, len(closes)):
        e12 = calculate_ema(closes[:i+1], 12)
        e26 = calculate_ema(closes[:i+1], 26)
        macd_series.append(e12 - e26)
    signal_line = calculate_ema(macd_series, 9) if len(macd_series) >= 9 else macd_line
    histogram = macd_line - signal_line
    return round(macd_line, 6), round(signal_line, 6), round(histogram, 6)


# ============================================
# PUBLIC INTERFACE — consumed by the engine
# ============================================
def get_market_snapshot(pair="XAU/USD", timeframe="5m"):
    """
    Fetch a normalized market snapshot for the given pair.

    Returns a dict with:
        - candles_5m, candles_15m, candles_1h: raw OHLCV lists
        - current_price: float
        - session: active kill-zone / session info
        - news_blocked: (bool, str)
        - macro: macro trend analysis dict
        - support, resistance: from macro analyzer
        - asset_config: the ASSETS entry for this pair
    """
    asset_cfg = ASSETS.get(pair, ASSETS["XAU/USD"])

    candles_5m = get_candles(pair, "5m", "5d")
    time.sleep(2)
    candles_15m = get_candles(pair, "15m", "5d")
    time.sleep(2)
    candles_1h = get_candles(pair, "1h", "5d")
    time.sleep(2)

    current_price = None
    if candles_5m and len(candles_5m) > 0:
        current_price = candles_5m[-1]["close"]

    # Asian range
    if asset_cfg.get("use_asian_sweep", False) and candles_5m:
        update_asian_range(candles_5m)

    # Session / kill zone
    session = get_active_kill_zone()
    if session is None:
        session = {"name": "OFF_HOURS", "label": get_session_label(), "risk_mult": 0.5}

    # News
    is_blocked, news_title = macro_analyzer.check_news_block(pair)

    # Macro
    macro = macro_analyzer.analyze_macro_trend(pair)

    return {
        "pair": pair,
        "candles_5m": candles_5m,
        "candles_15m": candles_15m,
        "candles_1h": candles_1h,
        "current_price": current_price,
        "session": session,
        "news_blocked": is_blocked,
        "news_title": news_title,
        "macro": macro,
        "support": macro.get("support"),
        "resistance": macro.get("resistance"),
        "asset_config": asset_cfg,
    }


def get_historical(pair="XAU/USD", timeframe="1h", bars=300):
    """
    Return historical OHLCV from the DB cache.

    Returns list of dicts: [{"datetime": ..., "open": ..., "high": ..., "low": ..., "close": ..., "volume": ...}]
    """
    return db.get_historical_candles(pair, timeframe, limit=bars)
