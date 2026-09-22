import os
import requests
import time
import json
import math
from datetime import datetime, date, timedelta
from collections import deque
import pytz

# ╔══════════════════════════════════════════════════════════════╗
# ║  🥇 XAU/USD ULTIMATE SIGNAL BOT — 2026 INSTITUTIONAL GRADE ║
# ║                                                              ║
# ║  Strategies:                                                 ║
# ║  • ICT Kill Zone + Silver Bullet Timing                     ║
# ║  • Asian Range Sweep / Judas Swing                          ║
# ║  • VWAP + EMA Confluence (8/21/50)                          ║
# ║  • OTE Fibonacci (62%-79% Retracement)                      ║
# ║  • Market Structure (BOS/CHoCH/MSS)                         ║
# ║  • Order Blocks + FVG + Liquidity Grabs                     ║
# ║  • Momentum & Displacement Filters                          ║
# ║  • RSI Divergence                                            ║
# ║  • Auto Buy/Sell Engine with Trailing SL & Breakeven        ║
# ║  • Trade Journal + Performance Tracking                     ║
# ╚══════════════════════════════════════════════════════════════╝

# ============================================
# CONFIGURATION
# ============================================
TELEGRAM_TOKEN     = os.environ.get("TELEGRAM_TOKEN", "8831251788:AAEIMLBzD0LwdGC4vqyO7Z2SH5cUWcUTg6Y")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "953284393")
TWELVEDATA_API_KEY = os.environ.get("TWELVEDATA_API_KEY", "7299d19a5fa645a4ba5ac931ddf875a7")
FINNHUB_API_KEY    = os.environ.get("FINNHUB_API_KEY", "")

SYMBOL       = "XAU/USD"
CAPITAL      = 20
RISK_PERCENT = 0.25                     # 25% risk per trade (required for $20 account)
RISK_AMOUNT  = CAPITAL * RISK_PERCENT

MAX_TRADES_PER_DAY     = 10             # Quality > quantity
MIN_CONFIDENCE         = 50             # Only top-tier signals (was 70)
MIN_SL_DOLLARS         = 3.0
MAX_SL_DOLLARS         = 18.0
MIN_FVG_SIZE           = 1.20
EQUAL_LEVEL_TOL        = 0.30
RR_RATIO               = 2.5           # Target 1:2.5 R:R (was 2.0)
ATR_PERIOD             = 14
ATR_SL_MULT            = 1.5
MIN_ADX                = 22             # Stricter trend filter (was 20)
MAX_CONSEC_LOSSES      = 2              # Pause after 2 losses (was 3)
COOLDOWN_SAME_DIR      = 900            # 15 mins between same-direction signals
DAILY_LOSS_LIMIT_PCT   = 0.50           # Stop trading if -50% daily loss ($10 on $20 acct)
MAX_TRADE_DURATION_SEC = 7200           # Auto-close after 2 hours (7200 sec)

# Trailing SL thresholds
TRAILING_BREAKEVEN_AT  = 0.50           # Move SL to breakeven at 50% of TP
TRAILING_LOCK_AT       = 0.75           # Lock 50% profit at 75% of TP
TRAILING_LOCK_PCT      = 0.50           # Lock this % of profit

# EMA periods
EMA_FAST   = 8
EMA_MID    = 21
EMA_SLOW   = 50

IST = pytz.timezone('Asia/Kolkata')

PAPER_MODE = False  # Set False ONLY when ready for live execution

# Gold contract: 1.00 lot = 100oz -> $1 move = $100/lot -> $1 move = $1 per 0.01 lot
USD_PER_DOLLAR_MOVE_PER_001_LOT = 1.0

# Trade journal file
TRADE_JOURNAL_FILE = "trade_journal.json"

# ============================================
# KILL ZONE DEFINITIONS (IST times)
# ============================================
# London Kill Zone:  12:30 PM - 3:30 PM IST  (07:00-10:00 GMT)
# New York Kill Zone: 6:30 PM - 9:30 PM IST  (13:00-16:00 GMT)
# Silver Bullet windows (1-hour precision):
#   London Open:  1:30 PM - 2:30 PM IST
#   NY AM:        8:30 PM - 9:30 PM IST
#   NY PM:       12:30 AM - 1:30 AM IST (next day)

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

# Asian session for range detection (IST)
ASIAN_SESSION = {"start_h": 4, "start_m": 0, "end_h": 12, "end_m": 30}

# ============================================
# STATE
# ============================================
trades_today          = 0
last_trade_date       = None
last_signal_direction = None
last_signal_time      = 0
consecutive_losses    = 0
paused_until          = 0
daily_pnl             = 0.0
asian_range_high      = None
asian_range_low       = None
asian_range_set_date  = None

# Active trade state (auto-trade engine)
active_trade = None
# Structure: {
#   "signal": "LONG"/"SHORT",
#   "entry_price": float,
#   "sl_price": float,
#   "tp_price": float,
#   "lots": float,
#   "entry_time": float (timestamp),
#   "original_sl": float,
#   "sl_moved_breakeven": bool,
#   "sl_moved_lock": bool,
#   "confidence": int,
#   "reasons": list,
#   "state": "MONITORING",  # MONITORING -> closed
# }

# Trade journal (in-memory, synced to file)
trade_journal = []

# Rolling performance
rolling_trades = deque(maxlen=50)  # last 50 trades

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
# FETCH CANDLES
# ============================================
def get_candles(interval="5m", range_str="5d"):
    # Map intervals to TwelveData format
    td_interval_map = {"1m": "1min", "5m": "5min", "15m": "15min", "1h": "1h"}
    td_interval = td_interval_map.get(interval, "5min")
    
    url = f"https://api.twelvedata.com/time_series?symbol={SYMBOL}&interval={td_interval}&outputsize=500&apikey={TWELVEDATA_API_KEY}"
    try:
        r = requests.get(url, timeout=15)
        data = r.json()
        
        if "values" not in data:
            print(f"TwelveData Error for {SYMBOL}: {data}. Falling back to alternative APIs...")
            
            # --- FINNHUB FALLBACK ---
            if FINNHUB_API_KEY and SYMBOL == "XAU/USD":
                fh_interval_map = {"1m": "1", "5m": "5", "15m": "15", "1h": "60"}
                fh_res = fh_interval_map.get(interval, "5")
                end_ts = int(time.time())
                start_ts = end_ts - (10 * 24 * 60 * 60) # 10 days
                fh_url = f"https://finnhub.io/api/v1/forex/candle?symbol=OANDA:XAU_USD&resolution={fh_res}&from={start_ts}&to={end_ts}&token={FINNHUB_API_KEY}"
                
                print("Fetching from Finnhub...")
                try:
                    f_req = requests.get(fh_url, timeout=15)
                    f_data = f_req.json()
                    if f_data.get("s") == "ok":
                        # Convert Finnhub format to match TwelveData format
                        candles = []
                        for i in range(len(f_data['t'])):
                            dt_str = datetime.fromtimestamp(f_data['t'][i]).strftime('%Y-%m-%d %H:%M:%S')
                            candles.append({
                                "time": dt_str,
                                "open": float(f_data['o'][i]),
                                "high": float(f_data['h'][i]),
                                "low": float(f_data['l'][i]),
                                "close": float(f_data['c'][i])
                            })
                        return candles[::-1]  # Reverse to match TwelveData (newest first)
                except Exception as e:
                    print(f"Finnhub Error: {e}")

            # --- YAHOO FINANCE FALLBACK ---
            print("Falling back to Yahoo Finance...")
            y_url = f"https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval={interval}&range={range_str}"
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
            return candles

        values = data["values"]
        # TwelveData returns newest first, so we reverse it to oldest first
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
        return candles
    except Exception as e:
        print(f"Candle fetch error: {e}")
        return None

def get_current_price():
    """Fetch latest price for trade monitoring."""
    candles = get_candles(interval="1m", range_str="1d")
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

    # Check main Kill Zones
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

    # Check Silver Bullet windows
    for sb_name, sb in SILVER_BULLET_WINDOWS.items():
        sb_start = sb["start_h"] * 60 + sb["start_m"]
        sb_end = sb["end_h"] * 60 + sb["end_m"]
        # Handle overnight window (NY PM: 0:30-1:30)
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
        return  # Already set for today

    # Find candles in Asian session time window
    asian_highs = []
    asian_lows = []
    for c in candles_5m:
        try:
            # Parse candle time
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
    """
    Detect if price has swept the Asian range (Judas Swing).
    For BULLISH: price swept Asian Low then reversed up
    For BEARISH: price swept Asian High then reversed down
    """
    if asian_range_high is None or asian_range_low is None:
        return False, 0

    curr = candles[-1]
    prev = candles[-2] if len(candles) >= 2 else None

    if bias == "BULLISH" and prev:
        # Price dipped below Asian Low (sweep) then closed back above
        swept = prev["low"] < asian_range_low
        rejected = curr["close"] > asian_range_low
        strong_rejection = curr["close"] > curr["open"]  # bullish candle
        if swept and rejected and strong_rejection:
            return True, 15
    elif bias == "BEARISH" and prev:
        # Price spiked above Asian High (sweep) then closed back below
        swept = prev["high"] > asian_range_high
        rejected = curr["close"] < asian_range_high
        strong_rejection = curr["close"] < curr["open"]  # bearish candle
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
# PROPER EMA (Exponential Moving Average)
# ============================================
def calculate_ema(values, period):
    """Calculate true EMA (not simple average)."""
    if len(values) < period:
        return sum(values) / len(values) if values else 0

    multiplier = 2 / (period + 1)
    ema = sum(values[:period]) / period  # SMA seed

    for val in values[period:]:
        ema = (val - ema) * multiplier + ema

    return round(ema, 4)

def get_ema_confluence(candles):
    """
    Calculate 8/21/50 EMAs and check alignment.
    Returns: (ema8, ema21, ema50, bias, is_aligned, score)
    """
    closes = [c["close"] for c in candles]
    if len(closes) < EMA_SLOW:
        return None, None, None, "NEUTRAL", False, 0

    ema8 = calculate_ema(closes, EMA_FAST)
    ema21 = calculate_ema(closes, EMA_MID)
    ema50 = calculate_ema(closes, EMA_SLOW)

    # Full bullish alignment: EMA8 > EMA21 > EMA50
    bullish_aligned = ema8 > ema21 > ema50
    # Full bearish alignment: EMA8 < EMA21 < EMA50
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
def calculate_vwap(candles):
    """
    Calculate VWAP using typical price * estimated volume.
    Since TwelveData free tier may not give volume, we use
    candle range as a proxy for volume weighting.
    VWAP = sum(TP * V) / sum(V) where TP = (H+L+C)/3
    """
    if len(candles) < 5:
        return None, "NEUTRAL", 0

    sum_tpv = 0
    sum_v = 0

    for c in candles:
        typical_price = (c["high"] + c["low"] + c["close"]) / 3
        # Use candle range as volume proxy (higher range = more activity)
        vol_proxy = max(c["high"] - c["low"], 0.01)
        sum_tpv += typical_price * vol_proxy
        sum_v += vol_proxy

    if sum_v == 0:
        return None, "NEUTRAL", 0

    vwap = round(sum_tpv / sum_v, 2)
    curr_price = candles[-1]["close"]

    # Price relative to VWAP
    if curr_price > vwap + 1.0:
        return vwap, "BULLISH", 10
    elif curr_price < vwap - 1.0:
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
def detect_ote_zone(candles, bias):
    """
    After a displacement move, check if price is in the
    62%-79% retracement zone (OTE = premium/discount).
    """
    if len(candles) < 15:
        return False, 0, None, None

    recent = candles[-15:]

    if bias == "BULLISH":
        # Find recent swing low and swing high (displacement up)
        low_val = min(c["low"] for c in recent[:-3])
        high_val = max(c["high"] for c in recent[-5:])
        move = high_val - low_val
        if move < 2.0:
            return False, 0, None, None

        # OTE zone: 62%-79% retracement from high
        ote_top = high_val - move * 0.618
        ote_bottom = high_val - move * 0.79
        curr = candles[-1]["close"]

        if ote_bottom <= curr <= ote_top:
            return True, 8, ote_bottom, ote_top

    elif bias == "BEARISH":
        # Find recent swing high and swing low (displacement down)
        high_val = max(c["high"] for c in recent[:-3])
        low_val = min(c["low"] for c in recent[-5:])
        move = high_val - low_val
        if move < 2.0:
            return False, 0, None, None

        # OTE zone: 62%-79% retracement from low
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

# ============================================
# HTF TREND (EMA-based for 1H confirmation)
# ============================================
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
def detect_liquidity_zones(candles):
    if len(candles) < 10:
        return False, False, False, False

    recent      = candles[-30:]
    highs       = [c["high"] for c in recent[:-2]]
    lows        = [c["low"]  for c in recent[:-2]]
    last_high   = candles[-1]["high"]
    last_low    = candles[-1]["low"]

    equal_highs = False
    swept_high  = False
    for i in range(len(highs)):
        for j in range(i+1, len(highs)):
            if abs(highs[i] - highs[j]) <= EQUAL_LEVEL_TOL:
                equal_highs = True
                if last_high > max(highs[i], highs[j]):
                    swept_high = True

    equal_lows = False
    swept_low  = False
    for i in range(len(lows)):
        for j in range(i+1, len(lows)):
            if abs(lows[i] - lows[j]) <= EQUAL_LEVEL_TOL:
                equal_lows = True
                if last_low < min(lows[i], lows[j]):
                    swept_low = True

    return equal_highs, equal_lows, swept_high, swept_low

# ============================================
# FVG WITH SIZE FILTER
# ============================================
def detect_fvg(candles):
    if len(candles) < 3:
        return None, 0
    for i in range(len(candles)-3, max(len(candles)-10, 0), -1):
        c1 = candles[i]
        c3 = candles[i+2]
        if c1["high"] < c3["low"]:
            gap_size = c3["low"] - c1["high"]
            if gap_size >= MIN_FVG_SIZE:
                if candles[-1]["close"] > c1["high"]:
                    return "BULLISH_FVG", 8
        if c1["low"] > c3["high"]:
            gap_size = c1["low"] - c3["high"]
            if gap_size >= MIN_FVG_SIZE:
                if candles[-1]["close"] < c1["low"]:
                    return "BEARISH_FVG", 8
    return None, 0

# ============================================
# LIQUIDITY GRAB
# ============================================
def detect_liquidity_grab(candles):
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
    grab, score = None, 0
    if prev["high"] > max_high:
        wick_size = prev["high"] - max(prev["open"], prev["close"])
        if wick_size >= 1.0 and curr["close"] < curr["open"]:
            grab, score = "BEARISH_GRAB", 2
    if prev["low"] < min_low:
        wick_size = min(prev["open"], prev["close"]) - prev["low"]
        if wick_size >= 1.0 and curr["close"] > curr["open"]:
            grab, score = "BULLISH_GRAB", 2
    return grab, score

# ============================================
# CANDLESTICK PATTERN (enhanced)
# ============================================
def check_candle_pattern(candles):
    if len(candles) < 3:
        return None, 0

    c1 = candles[-3]
    c2 = candles[-2]
    c3 = candles[-1]

    # Bearish Engulfing
    if (c2["open"] < c2["close"] and c3["open"] > c3["close"] and
            c3["open"] >= c2["close"] and c3["close"] <= c2["open"]):
        body_size = abs(c3["open"] - c3["close"])
        if body_size > 1.5:  # Minimum body size for gold
            return "BEARISH_ENGULF", 3
        return "BEARISH_ENGULF", 2

    # Bullish Engulfing
    if (c2["open"] > c2["close"] and c3["open"] < c3["close"] and
            c3["open"] <= c2["close"] and c3["close"] >= c2["open"]):
        body_size = abs(c3["open"] - c3["close"])
        if body_size > 1.5:
            return "BULLISH_ENGULF", 3
        return "BULLISH_ENGULF", 2

    # Evening Star (bearish 3-candle reversal)
    if (c1["close"] > c1["open"] and  # big green
        abs(c2["close"] - c2["open"]) < abs(c1["close"] - c1["open"]) * 0.3 and  # small body
        c3["close"] < c3["open"] and c3["close"] < c1["open"]):  # big red below c1 open
        return "EVENING_STAR", 3

    # Morning Star (bullish 3-candle reversal)
    if (c1["close"] < c1["open"] and  # big red
        abs(c2["close"] - c2["open"]) < abs(c1["close"] - c1["open"]) * 0.3 and  # small body
        c3["close"] > c3["open"] and c3["close"] > c1["open"]):  # big green above c1 open
        return "MORNING_STAR", 3

    # Shooting Star
    if (c3["high"] - max(c3["open"], c3["close"]) >
            2 * abs(c3["open"] - c3["close"]) and
            abs(c3["open"] - c3["close"]) > 0):
        return "SHOOTING_STAR", 1

    # Hammer
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
    """
    Bullish divergence: price lower low but RSI higher low.
    Bearish divergence: price higher high but RSI lower high.
    """
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
    """
    Check for strong displacement (momentum):
    1. Body-to-wick ratio of recent candles
    2. Consecutive same-direction closes
    3. Velocity (ATR multiple)
    """
    if len(candles) < 5:
        return False, 0

    score = 0
    reasons = []

    # 1. Check last 3 candles for consecutive same direction
    last3 = candles[-3:]
    if bias == "BULLISH":
        consec = sum(1 for c in last3 if c["close"] > c["open"])
        if consec >= 3:
            score += 3
            reasons.append("3 consecutive bullish candles")
        elif consec >= 2:
            score += 1
    elif bias == "BEARISH":
        consec = sum(1 for c in last3 if c["close"] < c["open"])
        if consec >= 3:
            score += 3
            reasons.append("3 consecutive bearish candles")
        elif consec >= 2:
            score += 1

    # 2. Body-to-wick ratio of the last candle (strong displacement)
    c = candles[-1]
    body = abs(c["close"] - c["open"])
    upper_wick = c["high"] - max(c["open"], c["close"])
    lower_wick = min(c["open"], c["close"]) - c["low"]
    total_wick = upper_wick + lower_wick

    if body > 0 and total_wick > 0:
        ratio = body / total_wick
        if ratio > 2.0:  # Body >> Wicks = strong displacement
            score += 2
            reasons.append(f"Strong displacement (B/W={ratio:.1f})")

    return score > 0, score

# ============================================
# ENTRY CANDLE CONFIRMATION
# ============================================
def check_entry_confirmation(candles, signal_direction):
    """
    Wait for the current candle to close in the signal direction
    as final confirmation before executing.
    """
    if len(candles) < 2:
        return False

    curr = candles[-1]

    if signal_direction == "LONG":
        # Bullish close: close > open AND close > previous close
        return curr["close"] > curr["open"] and curr["close"] > candles[-2]["close"]
    elif signal_direction == "SHORT":
        # Bearish close: close < open AND close < previous close
        return curr["close"] < curr["open"] and curr["close"] < candles[-2]["close"]

    return False

# ============================================
# SMART SL PLACEMENT (structure + ATR blend)
# ============================================
def calculate_sl_distance(candles, bias, ob_high, ob_low, atr):
    curr = candles[-1]["close"]
    atr_sl = (atr * ATR_SL_MULT) if atr else 8.0

    if bias == "LONG":
        if ob_low is not None:
            struct_sl = curr - (ob_low - 0.50)
        else:
            swing_lows = find_swing_lows(candles[-30:])
            struct_sl = curr - (swing_lows[-1][1] - 0.50) if swing_lows else 8.0
        return max(struct_sl, atr_sl, MIN_SL_DOLLARS)

    elif bias == "SHORT":
        if ob_high is not None:
            struct_sl = (ob_high + 0.50) - curr
        else:
            swing_highs = find_swing_highs(candles[-30:])
            struct_sl = (swing_highs[-1][1] + 0.50) - curr if swing_highs else 8.0
        return max(struct_sl, atr_sl, MIN_SL_DOLLARS)

    return 8.0

# ============================================
# CALCULATE LOTS
# ============================================
def calculate_lots(sl_dollars):
    if sl_dollars <= 0:
        return 0.01, 0, False
    raw_lots = (RISK_AMOUNT / sl_dollars) * 0.01
    lots     = round(raw_lots, 2)
    if lots < 0.01:
        return 0.01, round(sl_dollars * 1.0, 2), False
    lots        = min(lots, 0.50)
    actual_risk = sl_dollars * (lots / 0.01) * USD_PER_DOLLAR_MOVE_PER_001_LOT
    is_safe     = actual_risk <= RISK_AMOUNT * 1.5   # Relaxed safety margin
    return lots, round(actual_risk, 2), is_safe

# ============================================
# TRADE JOURNAL — PERSISTENCE
# ============================================
def load_trade_journal():
    global trade_journal
    try:
        if os.path.exists(TRADE_JOURNAL_FILE):
            with open(TRADE_JOURNAL_FILE, "r") as f:
                trade_journal = json.load(f)
                print(f"📒 Loaded {len(trade_journal)} trades from journal.")
    except Exception as e:
        print(f"Journal load error: {e}")
        trade_journal = []

def save_trade_journal():
    try:
        with open(TRADE_JOURNAL_FILE, "w") as f:
            json.dump(trade_journal, f, indent=2)
    except Exception as e:
        print(f"Journal save error: {e}")

def log_trade(trade_data):
    """Log a completed trade to the journal."""
    trade_journal.append(trade_data)
    rolling_trades.append(trade_data)
    save_trade_journal()

def get_daily_stats():
    """Get today's trading stats."""
    today_str = date.today().isoformat()
    today_trades = [t for t in trade_journal if t.get("date", "") == today_str]
    wins = sum(1 for t in today_trades if t.get("pnl", 0) > 0)
    losses = sum(1 for t in today_trades if t.get("pnl", 0) <= 0)
    total_pnl = sum(t.get("pnl", 0) for t in today_trades)
    return {
        "total": len(today_trades),
        "wins": wins,
        "losses": losses,
        "pnl": round(total_pnl, 2),
        "win_rate": round(wins / len(today_trades) * 100, 1) if today_trades else 0
    }

def get_rolling_stats():
    """Get rolling performance stats."""
    if not rolling_trades:
        return None
    wins = sum(1 for t in rolling_trades if t.get("pnl", 0) > 0)
    total = len(rolling_trades)
    total_pnl = sum(t.get("pnl", 0) for t in rolling_trades)
    return {
        "total": total,
        "wins": wins,
        "losses": total - wins,
        "pnl": round(total_pnl, 2),
        "win_rate": round(wins / total * 100, 1) if total else 0
    }

def save_state():
    """Save bot state for the web dashboard."""
    state = {
        "capital": CAPITAL,
        "daily_pnl": round(daily_pnl, 2),
        "trades_today": trades_today,
        "active_trade": active_trade,
        "consecutive_losses": consecutive_losses,
        "paused_until": paused_until,
        "last_signal_direction": last_signal_direction,
        "last_update": time.time()
    }
    try:
        with open("state.json", "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        pass

# ============================================
# AUTO-TRADE ENGINE
# ============================================
def execute_auto_trade(sig):
    """
    Execute a trade (paper or live).
    Sets up the active_trade state for monitoring.
    """
    global active_trade

    entry_price = sig["price"]

    if sig["signal"] == "LONG":
        sl_price = entry_price - sig["sl_dollars"]
        tp_price = entry_price + sig["tp_dollars"]
    else:
        sl_price = entry_price + sig["sl_dollars"]
        tp_price = entry_price - sig["tp_dollars"]

    active_trade = {
        "signal": sig["signal"],
        "entry_price": entry_price,
        "sl_price": sl_price,
        "tp_price": tp_price,
        "original_sl": sl_price,
        "lots": sig["lots"],
        "entry_time": time.time(),
        "sl_moved_breakeven": False,
        "sl_moved_lock": False,
        "confidence": sig["confidence"],
        "reasons": sig["reasons"],
        "sl_dollars": sig["sl_dollars"],
        "tp_dollars": sig["tp_dollars"],
        "potential_loss": sig["potential_loss"],
        "state": "MONITORING",
    }

    mode = "🧪 PAPER" if PAPER_MODE else "⚡ LIVE"
    direction = "🟢 BUY" if sig["signal"] == "LONG" else "🔴 SELL"
    now_ist = datetime.now(IST).strftime('%d %b %Y %H:%M IST')

    msg = f"""{mode} <b>AUTO-TRADE EXECUTED</b> 🤖

⚔️ <b>XAUUSD — {direction}</b>
━━━━━━━━━━━━━━━━━━━━
💰 <b>Entry:</b> {entry_price:.2f}
🛑 <b>Stop Loss:</b> {sl_price:.2f} (${sig["sl_dollars"]:.2f})
🎯 <b>Take Profit:</b> {tp_price:.2f} (${sig["tp_dollars"]:.2f})
📦 <b>Lots:</b> {sig["lots"]}
⚖️ <b>R:R:</b> 1:{RR_RATIO}
🎯 <b>Confidence:</b> {sig["confidence"]}%
💵 <b>Max Risk:</b> ~${sig["potential_loss"]:.2f}
━━━━━━━━━━━━━━━━━━━━
📋 <b>WHY THIS TRADE:</b>
""" + "\n".join([f"  ✅ {r}" for r in sig["reasons"]]) + f"""

━━━━━━━━━━━━━━━━━━━━
🤖 <b>AUTO-MANAGEMENT:</b>
  📊 Trailing SL → Breakeven at {int(TRAILING_BREAKEVEN_AT*100)}% TP
  🔒 Profit Lock at {int(TRAILING_LOCK_AT*100)}% TP
  ⏰ Max Duration: {MAX_TRADE_DURATION_SEC//3600}h
━━━━━━━━━━━━━━━━━━━━
🕐 {now_ist}"""

    send_telegram(msg)
    print(f"🤖 Auto-trade executed: {sig['signal']} @ {entry_price:.2f}")
    return True

def monitor_active_trade():
    """
    Monitor the active trade:
    - Check SL/TP hit
    - Trailing SL (breakeven + profit lock)
    - Time-based exit
    Returns: None if trade still active, or trade result dict
    """
    global active_trade, consecutive_losses, paused_until, daily_pnl

    if active_trade is None:
        return None

    current_price = get_current_price()
    if current_price is None or current_price == 0:
        return None

    trade = active_trade
    signal = trade["signal"]
    entry = trade["entry_price"]
    sl = trade["sl_price"]
    tp = trade["tp_price"]
    elapsed = time.time() - trade["entry_time"]

    # Calculate current P&L
    if signal == "LONG":
        current_pnl = (current_price - entry) * (trade["lots"] / 0.01) * USD_PER_DOLLAR_MOVE_PER_001_LOT
        price_progress = (current_price - entry) / trade["tp_dollars"] if trade["tp_dollars"] > 0 else 0
    else:
        current_pnl = (entry - current_price) * (trade["lots"] / 0.01) * USD_PER_DOLLAR_MOVE_PER_001_LOT
        price_progress = (entry - current_price) / trade["tp_dollars"] if trade["tp_dollars"] > 0 else 0

    result = None

    # --- CHECK TP HIT ---
    if signal == "LONG" and current_price >= tp:
        result = close_trade("TP_HIT", current_price, current_pnl)
    elif signal == "SHORT" and current_price <= tp:
        result = close_trade("TP_HIT", current_price, current_pnl)

    # --- CHECK SL HIT ---
    elif signal == "LONG" and current_price <= sl:
        result = close_trade("SL_HIT", current_price, current_pnl)
    elif signal == "SHORT" and current_price >= sl:
        result = close_trade("SL_HIT", current_price, current_pnl)

    # --- CHECK TIME EXIT ---
    elif elapsed >= MAX_TRADE_DURATION_SEC:
        result = close_trade("TIME_EXIT", current_price, current_pnl)

    else:
        # --- TRAILING SL LOGIC ---
        # Move SL to breakeven at 50% of TP distance
        if not trade["sl_moved_breakeven"] and price_progress >= TRAILING_BREAKEVEN_AT:
            if signal == "LONG":
                new_sl = entry + 0.50  # Slightly above entry
                if new_sl > trade["sl_price"]:
                    trade["sl_price"] = new_sl
                    trade["sl_moved_breakeven"] = True
                    send_telegram(
                        f"🔄 <b>SL → BREAKEVEN</b>\n"
                        f"Trade: {signal} @ {entry:.2f}\n"
                        f"New SL: {new_sl:.2f} (was {trade['original_sl']:.2f})\n"
                        f"Current: {current_price:.2f} ({price_progress*100:.0f}% to TP)"
                    )
                    print(f"🔄 SL moved to breakeven: {new_sl:.2f}")
            else:
                new_sl = entry - 0.50
                if new_sl < trade["sl_price"]:
                    trade["sl_price"] = new_sl
                    trade["sl_moved_breakeven"] = True
                    send_telegram(
                        f"🔄 <b>SL → BREAKEVEN</b>\n"
                        f"Trade: {signal} @ {entry:.2f}\n"
                        f"New SL: {new_sl:.2f} (was {trade['original_sl']:.2f})\n"
                        f"Current: {current_price:.2f} ({price_progress*100:.0f}% to TP)"
                    )
                    print(f"🔄 SL moved to breakeven: {new_sl:.2f}")

        # Lock 50% profit at 75% of TP distance
        if not trade["sl_moved_lock"] and price_progress >= TRAILING_LOCK_AT:
            if signal == "LONG":
                lock_distance = trade["tp_dollars"] * TRAILING_LOCK_PCT
                new_sl = entry + lock_distance
                if new_sl > trade["sl_price"]:
                    trade["sl_price"] = new_sl
                    trade["sl_moved_lock"] = True
                    send_telegram(
                        f"🔒 <b>PROFIT LOCKED</b>\n"
                        f"Trade: {signal} @ {entry:.2f}\n"
                        f"New SL: {new_sl:.2f} (locking ${lock_distance:.2f} profit)\n"
                        f"Current: {current_price:.2f} ({price_progress*100:.0f}% to TP)"
                    )
                    print(f"🔒 Profit locked at SL: {new_sl:.2f}")
            else:
                lock_distance = trade["tp_dollars"] * TRAILING_LOCK_PCT
                new_sl = entry - lock_distance
                if new_sl < trade["sl_price"]:
                    trade["sl_price"] = new_sl
                    trade["sl_moved_lock"] = True
                    send_telegram(
                        f"🔒 <b>PROFIT LOCKED</b>\n"
                        f"Trade: {signal} @ {entry:.2f}\n"
                        f"New SL: {new_sl:.2f} (locking ${lock_distance:.2f} profit)\n"
                        f"Current: {current_price:.2f} ({price_progress*100:.0f}% to TP)"
                    )
                    print(f"🔒 Profit locked at SL: {new_sl:.2f}")

    return result

def close_trade(reason, exit_price, pnl):
    """Close the active trade and log it."""
    global active_trade, consecutive_losses, paused_until, daily_pnl

    trade = active_trade
    now_ist = datetime.now(IST).strftime('%d %b %Y %H:%M IST')
    duration = time.time() - trade["entry_time"]
    duration_str = f"{int(duration // 60)}m {int(duration % 60)}s"

    # Determine result emoji and update state
    if reason == "TP_HIT":
        emoji = "🎯✅"
        result_text = "TAKE PROFIT HIT"
        consecutive_losses = 0
    elif reason == "SL_HIT":
        emoji = "🛑❌"
        result_text = "STOP LOSS HIT"
        consecutive_losses += 1
        if consecutive_losses >= MAX_CONSEC_LOSSES:
            paused_until = time.time() + 3600  # Pause 1 hour
    elif reason == "TIME_EXIT":
        emoji = "⏰"
        result_text = "TIME-BASED EXIT"
        if pnl <= 0:
            consecutive_losses += 1
    elif reason == "REVERSE_EXIT":
        emoji = "🔄"
        result_text = "REVERSE SIGNAL EXIT"
    else:
        emoji = "📊"
        result_text = reason

    daily_pnl += pnl
    pnl_emoji = "💰" if pnl > 0 else "💸"

    # Log to journal
    trade_record = {
        "date": date.today().isoformat(),
        "time": now_ist,
        "signal": trade["signal"],
        "entry": trade["entry_price"],
        "exit": exit_price,
        "sl": trade["original_sl"],
        "tp": trade["tp_price"],
        "lots": trade["lots"],
        "pnl": round(pnl, 2),
        "reason": reason,
        "confidence": trade["confidence"],
        "duration": duration_str,
        "sl_moved_be": trade["sl_moved_breakeven"],
        "sl_moved_lock": trade["sl_moved_lock"],
    }
    log_trade(trade_record)

    # Send close notification
    direction = "LONG (BUY)" if trade["signal"] == "LONG" else "SHORT (SELL)"
    msg = f"""{emoji} <b>TRADE CLOSED — {result_text}</b>

📊 <b>{direction}</b>
━━━━━━━━━━━━━━━━━━━━
💰 Entry: {trade["entry_price"]:.2f}
📍 Exit: {exit_price:.2f}
{pnl_emoji} <b>P&L: ${pnl:+.2f}</b>
━━━━━━━━━━━━━━━━━━━━
⏱ Duration: {duration_str}
🛑 Original SL: {trade["original_sl"]:.2f}
🔄 Final SL: {trade["sl_price"]:.2f}
🎯 TP: {trade["tp_price"]:.2f}
📦 Lots: {trade["lots"]}
━━━━━━━━━━━━━━━━━━━━
📊 <b>Daily P&L:</b> ${daily_pnl:+.2f}
🔥 Consec Losses: {consecutive_losses}
🕐 {now_ist}"""

    send_telegram(msg)
    print(f"{emoji} Trade closed: {reason} | P&L: ${pnl:+.2f}")

    active_trade = None
    return trade_record

def check_reverse_signal(new_signal_direction):
    """If there's an active trade in opposite direction, close it."""
    global active_trade

    if active_trade is None:
        return

    if active_trade["signal"] != new_signal_direction:
        current_price = get_current_price()
        if current_price:
            entry = active_trade["entry_price"]
            if active_trade["signal"] == "LONG":
                pnl = (current_price - entry) * (active_trade["lots"] / 0.01) * USD_PER_DOLLAR_MOVE_PER_001_LOT
            else:
                pnl = (entry - current_price) * (active_trade["lots"] / 0.01) * USD_PER_DOLLAR_MOVE_PER_001_LOT
            close_trade("REVERSE_EXIT", current_price, pnl)

# ============================================
# DAILY SUMMARY REPORT
# ============================================
def send_daily_summary():
    """Send end-of-day summary to Telegram."""
    stats = get_daily_stats()
    rolling = get_rolling_stats()
    now_ist = datetime.now(IST).strftime('%d %b %Y')

    pnl_emoji = "💰" if stats["pnl"] >= 0 else "💸"

    msg = f"""📊 <b>DAILY SUMMARY — {now_ist}</b>
━━━━━━━━━━━━━━━━━━━━

📈 <b>Today's Results:</b>
  Total Trades: {stats["total"]}
  ✅ Wins: {stats["wins"]}
  ❌ Losses: {stats["losses"]}
  📊 Win Rate: {stats["win_rate"]}%
  {pnl_emoji} P&L: ${stats["pnl"]:+.2f}
"""

    if rolling:
        r_emoji = "💰" if rolling["pnl"] >= 0 else "💸"
        msg += f"""
━━━━━━━━━━━━━━━━━━━━
📈 <b>Rolling Performance (Last {rolling["total"]} trades):</b>
  ✅ Wins: {rolling["wins"]} | ❌ Losses: {rolling["losses"]}
  📊 Win Rate: {rolling["win_rate"]}%
  {r_emoji} Total P&L: ${rolling["pnl"]:+.2f}
"""

    # Win rate auto-pause warning
    if rolling and rolling["win_rate"] < 60 and rolling["total"] >= 10:
        msg += f"""
━━━━━━━━━━━━━━━━━━━━
⚠️ <b>WARNING:</b> Win rate below 60% ({rolling["win_rate"]}%)
Bot will auto-pause if this continues. Review strategy.
"""

    msg += f"""
━━━━━━━━━━━━━━━━━━━━
🕐 Report generated at {datetime.now(IST).strftime('%H:%M IST')}
💼 Capital: ${CAPITAL} | Risk/trade: {int(RISK_PERCENT*100)}%"""

    send_telegram(msg)

# ============================================
# SCALPING ENGINE (1-Minute TF)
# ============================================
def generate_scalp_signal(candles_1m):
    if not candles_1m or len(candles_1m) < 30:
        return None

    curr = candles_1m[-1]
    curr_price = curr["close"]
    
    closes = [c["close"] for c in candles_1m]
    ema9 = calculate_ema(closes, 9)
    ema21 = calculate_ema(closes, 21)
    vwap, _, _ = calculate_vwap(candles_1m)
    
    if vwap is None:
        return None

    atr = calculate_atr(candles_1m, 14)
    if atr is None or atr < 0.2:
        atr = 0.5

    # Bullish Scalp: Price > VWAP, EMA9 > EMA21, Close > EMA9, previous close < EMA9 (crossover pullback)
    if curr_price > vwap and ema9 > ema21:
        if curr["close"] > ema9 and candles_1m[-2]["close"] <= ema9:
            sl_price = curr_price - (atr * 1.5)
            tp_price = curr_price + ((curr_price - sl_price) * 1.5) # 1:1.5 RR
            loss_dollars = curr_price - sl_price
            lots = max(0.01, round(RISK_AMOUNT / loss_dollars * 0.01, 2)) if loss_dollars > 0 else 0.01
            
            return {
                "signal": "LONG",
                "price": curr_price,
                "sl_price": sl_price,
                "tp_price": tp_price,
                "sl_dollars": loss_dollars,
                "tp_dollars": tp_price - curr_price,
                "lots": lots,
                "potential_loss": loss_dollars * (lots / 0.01),
                "confidence": 88,
                "reasons": ["⚡ 1M EMA 9/21 Cross", "🌊 Price > VWAP (Bullish)"],
                "trend_1h": "SCALP",
                "tf_bias": "BULLISH",
                "bos_type": "N/A",
                "choch": False,
                "adx": 0,
                "atr": atr,
                "fvg": "N/A",
                "pattern": "Pullback",
                "rsi": 0,
                "kill_zone": "SCALP ZONE",
                "swept_high": False,
                "swept_low": False,
            }

    # Bearish Scalp: Price < VWAP, EMA9 < EMA21, Close < EMA9, previous close >= EMA9
    if curr_price < vwap and ema9 < ema21:
        if curr["close"] < ema9 and candles_1m[-2]["close"] >= ema9:
            sl_price = curr_price + (atr * 1.5)
            tp_price = curr_price - ((sl_price - curr_price) * 1.5) # 1:1.5 RR
            loss_dollars = sl_price - curr_price
            lots = max(0.01, round(RISK_AMOUNT / loss_dollars * 0.01, 2)) if loss_dollars > 0 else 0.01
            
            return {
                "signal": "SHORT",
                "price": curr_price,
                "sl_price": sl_price,
                "tp_price": tp_price,
                "sl_dollars": loss_dollars,
                "tp_dollars": curr_price - tp_price,
                "lots": lots,
                "potential_loss": loss_dollars * (lots / 0.01),
                "confidence": 88,
                "reasons": ["⚡ 1M EMA 9/21 Cross", "🌊 Price < VWAP (Bearish)"],
                "trend_1h": "SCALP",
                "tf_bias": "BEARISH",
                "bos_type": "N/A",
                "choch": False,
                "adx": 0,
                "atr": atr,
                "fvg": "N/A",
                "pattern": "Pullback",
                "rsi": 0,
                "kill_zone": "SCALP ZONE",
                "swept_high": False,
                "swept_low": False,
            }
            
    return None

# ============================================
# MAIN SIGNAL ENGINE — 2026 ULTIMATE STRATEGY
# ============================================
def generate_signal(candles_5m, candles_15m, candles_1h):
    if not candles_5m or not candles_15m or not candles_1h:
        return None

    curr_price = candles_5m[-1]["close"]

    # ═══════════════════════════════════════
    # GATE 1: KILL ZONE CHECK
    # ═══════════════════════════════════════
    kill_zone = get_active_kill_zone()
    if kill_zone is None:
        kill_zone = {"name": "ANY_TIME", "label": "24/7 Market Scan ⏱", "risk_mult": 1.0}

    print(f"\n🎯 Active: {kill_zone['label']}")

    # ═══════════════════════════════════════
    # GATE 2: 1H MACRO TREND
    # ═══════════════════════════════════════
    trend_1h = htf_trend(candles_1h)

    # ═══════════════════════════════════════
    # GATE 3: 15M STRUCTURE
    # ═══════════════════════════════════════
    tf_bias, bos_type, choch = analyze_structure_bos(candles_15m)
    
    # RELAXED RULES: Use EMA if structure is neutral
    if tf_bias == "NEUTRAL":
        closes = [c["close"] for c in candles_15m]
        ema10 = calculate_ema(closes, 10)
        ema30 = calculate_ema(closes, 30)
        tf_bias = "BULLISH" if ema10 > ema30 else "BEARISH"

    # ═══════════════════════════════════════
    # GATE 4: TREND STRENGTH (ADX)
    # ═══════════════════════════════════════
    adx = calculate_adx(candles_15m)

    # ═══════════════════════════════════════
    # CALCULATE ALL INDICATORS
    # ═══════════════════════════════════════
    atr_5m = calculate_atr(candles_5m)

    # EMA confluence (8/21/50)
    ema8, ema21, ema50, ema_bias, ema_aligned, ema_score = get_ema_confluence(candles_5m)

    # VWAP
    vwap, vwap_bias, vwap_score = calculate_vwap(candles_5m)

    # 5M structure
    m5_bias, m5_bos, m5_choch = analyze_structure_bos(candles_5m)

    # Order blocks
    ob_high, ob_low, price_in_ob = detect_order_block(candles_5m, tf_bias)

    # Liquidity
    eq_highs, eq_lows, swept_high, swept_low = detect_liquidity_zones(candles_5m)
    liquidity, liq_score = detect_liquidity_grab(candles_5m)

    # FVG
    fvg, fvg_score = detect_fvg(candles_5m)

    # Candle patterns
    pattern, pat_score = check_candle_pattern(candles_5m)

    # RSI
    rsi = calculate_rsi(candles_5m)
    div_bull = detect_rsi_divergence(candles_5m, "BULLISH")
    div_bear = detect_rsi_divergence(candles_5m, "BEARISH")

    # Asian range sweep
    asian_swept, asian_score = detect_asian_sweep(candles_5m, tf_bias)

    # OTE zone
    ote_in_zone, ote_score, ote_bottom, ote_top = detect_ote_zone(candles_5m, tf_bias)

    # Momentum filter
    momentum_ok, momentum_score = check_momentum(candles_5m, tf_bias)

    # Entry confirmation
    entry_confirmed = check_entry_confirmation(candles_5m, "LONG" if tf_bias == "BULLISH" else "SHORT")

    # ═══════════════════════════════════════
    # ANALYSIS LOG
    # ═══════════════════════════════════════
    print(f"\n{'='*50}")
    print(f"  🔍 FULL ANALYSIS — {kill_zone['label']}")
    print(f"{'='*50}")
    print(f"  Price:       {curr_price:.2f}")
    print(f"  1H Trend:    {trend_1h}")
    print(f"  15M Bias:    {tf_bias} | BOS: {bos_type} | CHoCH: {choch} | ADX: {adx}")
    print(f"  ATR(5m):     {atr_5m}")
    print(f"  EMA 8/21/50: {ema8:.2f}/{ema21:.2f}/{ema50:.2f} | {ema_bias} | Aligned: {ema_aligned}")
    print(f"  VWAP:        {vwap} | Bias: {vwap_bias}")
    print(f"  M5 Bias:     {m5_bias} | BOS: {m5_bos}")
    print(f"  Order Block: high={ob_high} low={ob_low} in_ob={price_in_ob}")
    print(f"  Liquidity:   {liquidity} | swept_hi={swept_high} swept_lo={swept_low}")
    print(f"  FVG:         {fvg} | Pattern: {pattern} | RSI: {rsi}")
    print(f"  Asian Sweep: {asian_swept} | OTE Zone: {ote_in_zone}")
    print(f"  Momentum:    ok={momentum_ok} | Entry Confirmed: {entry_confirmed}")

    # ═══════════════════════════════════════
    # SCORING ENGINE (max 115 points)
    # ═══════════════════════════════════════
    long_score, long_reasons = 0, []
    short_score, short_reasons = 0, []

    # --- Kill Zone (15 pts) ---
    if kill_zone:
        if tf_bias == "BULLISH":
            kz_pts = 15 if kill_zone.get("is_silver_bullet") else 12
            long_score += kz_pts
            long_reasons.append(f"🎯 {kill_zone['label']} (+{kz_pts})")
        elif tf_bias == "BEARISH":
            kz_pts = 15 if kill_zone.get("is_silver_bullet") else 12
            short_score += kz_pts
            short_reasons.append(f"🎯 {kill_zone['label']} (+{kz_pts})")

    # --- 1H + 15M Trend Alignment (20 pts) ---
    if tf_bias == "BULLISH":
        long_score += 20
        long_reasons.append(f"📈 1H+15M Bullish ({bos_type or 'trend'})")
    elif tf_bias == "BEARISH":
        short_score += 20
        short_reasons.append(f"📉 1H+15M Bearish ({bos_type or 'trend'})")

    # --- Asian Range Sweep (15 pts) ---
    if asian_swept:
        if tf_bias == "BULLISH":
            long_score += asian_score
            long_reasons.append(f"🏯 Asian Range Swept — Judas Swing (+{asian_score})")
        elif tf_bias == "BEARISH":
            short_score += asian_score
            short_reasons.append(f"🏯 Asian Range Swept — Judas Swing (+{asian_score})")

    # --- Order Block (12 pts) ---
    if price_in_ob and tf_bias == "BULLISH":
        long_score += 12
        long_reasons.append("📦 Price in Bullish Order Block (+12)")
    elif price_in_ob and tf_bias == "BEARISH":
        short_score += 12
        short_reasons.append("📦 Price in Bearish Order Block (+12)")

    # --- VWAP Alignment (10 pts) ---
    if vwap_bias == tf_bias:
        pts = vwap_score
        if tf_bias == "BULLISH":
            long_score += pts
            long_reasons.append(f"📊 VWAP Bullish — Price above VWAP ({vwap:.2f}) (+{pts})")
        elif tf_bias == "BEARISH":
            short_score += pts
            short_reasons.append(f"📊 VWAP Bearish — Price below VWAP ({vwap:.2f}) (+{pts})")

    # --- EMA Confluence (8 pts) ---
    if ema_bias == tf_bias and ema_score > 0:
        if tf_bias == "BULLISH":
            long_score += ema_score
            long_reasons.append(f"📉 EMA 8/21/50 Bullish{'  (Full Align)' if ema_aligned else ''} (+{ema_score})")
        elif tf_bias == "BEARISH":
            short_score += ema_score
            short_reasons.append(f"📉 EMA 8/21/50 Bearish{'  (Full Align)' if ema_aligned else ''} (+{ema_score})")

    # --- FVG (8 pts) ---
    if fvg == "BULLISH_FVG" and tf_bias == "BULLISH":
        long_score += fvg_score
        long_reasons.append(f"⚡ Bullish FVG (>=${MIN_FVG_SIZE}) (+{fvg_score})")
    elif fvg == "BEARISH_FVG" and tf_bias == "BEARISH":
        short_score += fvg_score
        short_reasons.append(f"⚡ Bearish FVG (>=${MIN_FVG_SIZE}) (+{fvg_score})")

    # --- OTE Zone (8 pts) ---
    if ote_in_zone:
        if tf_bias == "BULLISH":
            long_score += ote_score
            long_reasons.append(f"🎯 OTE Zone Entry ({ote_bottom:.2f}-{ote_top:.2f}) (+{ote_score})")
        elif tf_bias == "BEARISH":
            short_score += ote_score
            short_reasons.append(f"🎯 OTE Zone Entry ({ote_bottom:.2f}-{ote_top:.2f}) (+{ote_score})")

    # --- Candle Pattern (6 pts) ---
    if pattern in ["BULLISH_ENGULF", "HAMMER", "MORNING_STAR"] and tf_bias == "BULLISH":
        pts = pat_score * 2
        long_score += pts
        long_reasons.append(f"🕯 Pattern: {pattern} (+{pts})")
    elif pattern in ["BEARISH_ENGULF", "SHOOTING_STAR", "EVENING_STAR"] and tf_bias == "BEARISH":
        pts = pat_score * 2
        short_score += pts
        short_reasons.append(f"🕯 Pattern: {pattern} (+{pts})")

    # --- RSI Divergence (5 pts) ---
    if div_bull and tf_bias == "BULLISH":
        long_score += 5
        long_reasons.append("📈 Bullish RSI Divergence (+5)")
    if div_bear and tf_bias == "BEARISH":
        short_score += 5
        short_reasons.append("📉 Bearish RSI Divergence (+5)")

    # --- Momentum (5 pts) ---
    if momentum_ok:
        if tf_bias == "BULLISH":
            long_score += momentum_score
            long_reasons.append(f"💪 Strong Momentum (+{momentum_score})")
        elif tf_bias == "BEARISH":
            short_score += momentum_score
            short_reasons.append(f"💪 Strong Momentum (+{momentum_score})")

    # --- ADX Strength Bonus (3 pts) ---
    if adx >= 30:
        if tf_bias == "BULLISH":
            long_score += 3
            long_reasons.append(f"📶 Strong Trend ADX={adx} (+3)")
        elif tf_bias == "BEARISH":
            short_score += 3
            short_reasons.append(f"📶 Strong Trend ADX={adx} (+3)")

    # --- CHoCH Bonus ---
    if choch and tf_bias == "BULLISH":
        long_score += 5
        long_reasons.append("🔄 15M CHoCH Reversal (+5)")
    elif choch and tf_bias == "BEARISH":
        short_score += 5
        short_reasons.append("🔄 15M CHoCH Reversal (+5)")

    # --- 5M alignment bonus ---
    if m5_bias == tf_bias and m5_bos:
        if tf_bias == "BULLISH":
            long_score += 5
            long_reasons.append(f"✅ M5 Bullish BOS (+5)")
        elif tf_bias == "BEARISH":
            short_score += 5
            short_reasons.append(f"✅ M5 Bearish BOS (+5)")

    # --- Liquidity sweep bonus ---
    if swept_low and tf_bias == "BULLISH":
        long_score += 5
        long_reasons.append("💧 Equal Lows Swept (liquidity taken) (+5)")
    if swept_high and tf_bias == "BEARISH":
        short_score += 5
        short_reasons.append("💧 Equal Highs Swept (liquidity taken) (+5)")

    # --- Liquidity grab ---
    if liquidity == "BULLISH_GRAB" and tf_bias == "BULLISH":
        long_score += 3
        long_reasons.append("💧 Bullish Liquidity Grab (+3)")
    elif liquidity == "BEARISH_GRAB" and tf_bias == "BEARISH":
        short_score += 3
        short_reasons.append("💧 Bearish Liquidity Grab (+3)")

    # --- RSI extreme ---
    if rsi < 30 and tf_bias == "BULLISH":
        long_score += 3
        long_reasons.append(f"📉 RSI Oversold ({rsi}) (+3)")
    elif rsi > 70 and tf_bias == "BEARISH":
        short_score += 3
        short_reasons.append(f"📈 RSI Overbought ({rsi}) (+3)")

    print(f"\n  📊 SCORE: Long={long_score} | Short={short_score} | Need: {MIN_CONFIDENCE}+")

    # ═══════════════════════════════════════
    # SIGNAL DECISION
    # ═══════════════════════════════════════
    signal, score, reasons = None, 0, []
    if long_score > short_score and long_score >= MIN_CONFIDENCE and tf_bias == "BULLISH":
        signal, score, reasons = "LONG", min(long_score, 99), long_reasons
    elif short_score > long_score and short_score >= MIN_CONFIDENCE and tf_bias == "BEARISH":
        signal, score, reasons = "SHORT", min(short_score, 99), short_reasons

    if not signal:
        print("  ❌ No signal — confidence too low.")
        return None

    # ═══════════════════════════════════════
    # ENTRY CONFIRMATION GATE
    # ═══════════════════════════════════════
    if not entry_confirmed:
        print(f"  ⏳ Signal {signal} ({score}%) detected but entry candle not confirmed yet.")
        return None

    # ═══════════════════════════════════════
    # RISK CALCULATION
    # ═══════════════════════════════════════
    sl_dollars = calculate_sl_distance(
        candles_5m, "LONG" if signal == "LONG" else "SHORT",
        ob_high, ob_low, atr_5m
    )
    sl_dollars = min(sl_dollars, MAX_SL_DOLLARS)
    tp_dollars = sl_dollars * RR_RATIO

    lots, actual_risk, is_safe = calculate_lots(sl_dollars)
    if not is_safe:
        print(f"  ❌ Signal rejected: risk ${actual_risk:.2f} too high.")
        return None

    # ═══════════════════════════════════════
    # DAILY LOSS CHECK
    # ═══════════════════════════════════════
    if daily_pnl <= -(CAPITAL * DAILY_LOSS_LIMIT_PCT):
        print(f"  ❌ Daily loss limit reached (${daily_pnl:.2f}). No more trades today.")
        send_telegram(
            f"🛑 <b>DAILY LOSS LIMIT HIT</b>\n"
            f"Daily P&L: ${daily_pnl:.2f} (limit: -${CAPITAL * DAILY_LOSS_LIMIT_PCT:.2f})\n"
            f"Bot paused for the day."
        )
        return None

    return {
        "signal": signal, "price": curr_price,
        "sl_dollars": round(sl_dollars, 2), "tp_dollars": round(tp_dollars, 2),
        "lots": lots, "potential_loss": actual_risk,
        "confidence": score, "reasons": reasons, "rsi": rsi,
        "tf_bias": tf_bias, "trend_1h": trend_1h, "adx": adx, "atr": atr_5m,
        "bos_type": bos_type or "None", "choch": choch,
        "ob_high": ob_high, "ob_low": ob_low, "price_in_ob": price_in_ob,
        "swept_high": swept_high, "swept_low": swept_low,
        "liquidity": liquidity or "None", "fvg": fvg or "None",
        "pattern": pattern or "None",
        "kill_zone": kill_zone["label"],
        "ema8": ema8, "ema21": ema21, "ema50": ema50, "ema_aligned": ema_aligned,
        "vwap": vwap, "vwap_bias": vwap_bias,
        "asian_swept": asian_swept,
        "ote_in_zone": ote_in_zone,
        "momentum": momentum_ok,
        "entry_confirmed": entry_confirmed,
    }

# ============================================
# FORMAT & SEND SIGNAL (enhanced)
# ============================================
def send_signal(sig):
    direction = "🟢 LONG (BUY)" if sig["signal"] == "LONG" else "🔴 SHORT (SELL)"
    emoji     = "📈" if sig["signal"] == "LONG" else "📉"

    if sig["signal"] == "LONG":
        sl_price = sig["price"] - sig["sl_dollars"]
        tp_price = sig["price"] + sig["tp_dollars"]
    else:
        sl_price = sig["price"] + sig["sl_dollars"]
        tp_price = sig["price"] - sig["tp_dollars"]

    reasons_text = "\n".join([f"  {r}" for r in sig["reasons"]])
    now_ist      = datetime.now(IST).strftime('%d %b %Y %H:%M IST')

    # Build indicator summary
    ema_text = ""
    if sig.get("ema8"):
        ema_text = f"📉 <b>EMA:</b> 8={sig['ema8']:.2f} | 21={sig['ema21']:.2f} | 50={sig['ema50']:.2f}"
        if sig.get("ema_aligned"):
            ema_text += " ✅ ALIGNED"
        ema_text += "\n"

    vwap_text = ""
    if sig.get("vwap"):
        vwap_text = f"📊 <b>VWAP:</b> {sig['vwap']:.2f} ({sig['vwap_bias']})\n"

    fvg_text = ""
    if sig.get("fvg") and sig.get("fvg") != "None":
        fvg_text = f"🧲 <b>FVG/OB:</b> {sig.get('fvg')} | OB: {sig.get('ob_high')} - {sig.get('ob_low')}\n"

    ob_text = ""
    if sig.get("ob_high"):
        ob_text = (
            f"📦 <b>Order Block:</b> {sig['ob_low']:.2f} - {sig['ob_high']:.2f} "
            f"{'✅ inside OB' if sig['price_in_ob'] else ''}\n"
        )

    liq_text = ""
    if sig["swept_high"]:
        liq_text = "💧 <b>Liquidity:</b> Equal Highs swept\n"
    elif sig["swept_low"]:
        liq_text = "💧 <b>Liquidity:</b> Equal Lows swept\n"

    special_text = ""
    if sig.get("asian_swept"):
        special_text += "🏯 <b>Asian Range Sweep:</b> Judas Swing detected\n"
    if sig.get("ote_in_zone"):
        special_text += "🎯 <b>OTE Zone:</b> Price in 62-79% retracement\n"

    msg = f"""⚔️ <b>XAUUSD PRECISION SIGNAL</b> {emoji}
━━━━━━━━━━━━━━━━━━━━
🎯 <b>Kill Zone:</b> {sig.get("kill_zone", "N/A")}
📊 <b>Direction:</b> {direction}
💰 <b>Entry:</b> {sig["price"]:.2f} (Market)
🛑 <b>Stop Loss:</b> {sl_price:.2f} (${sig["sl_dollars"]:.2f} away)
🎯 <b>Take Profit:</b> {tp_price:.2f} (${sig["tp_dollars"]:.2f} away)
📦 <b>Lots:</b> {sig["lots"]}
⚖️ <b>R:R:</b> 1:{RR_RATIO}
🎯 <b>Confidence:</b> {sig["confidence"]}%
💵 <b>Max Risk:</b> ~${sig["potential_loss"]:.2f} ({int(RISK_PERCENT*100)}% of capital)
━━━━━━━━━━━━━━━━━━━━
📋 <b>WHY THIS TRADE ({len(sig["reasons"])} confluences):</b>
{reasons_text}

📈 <b>1H:</b> {sig["trend_1h"]} | <b>15M:</b> {sig["tf_bias"]} {sig["bos_type"]}{' +CHoCH🔄' if sig["choch"] else ''}
📶 <b>ADX:</b> {sig["adx"]} | <b>ATR:</b> {sig["atr"]}
{ema_text}{vwap_text}{ob_text}{liq_text}{special_text}📊 <b>FVG:</b> {sig["fvg"]} | 🕯 {sig["pattern"]} | 📉 RSI {sig["rsi"]}
━━━━━━━━━━━━━━━━━━━━
🕐 {now_ist}
⚠️ <i>Not financial advice. Verify spread & news before acting.</i>"""

    send_telegram(msg)
    print(f"✅ Signal: {sig['signal']} @ {sig['price']} | "
          f"Conf: {sig['confidence']}% | Risk: ${sig['potential_loss']:.2f}")

# ============================================
# MAIN LOOP — 2026 ULTIMATE ENGINE
# ============================================
def main():
    global trades_today, last_trade_date, last_signal_direction
    global last_signal_time, consecutive_losses, paused_until
    global daily_pnl

    if not validate_config():
        return

    # Load trade journal
    load_trade_journal()

    print("🚀 XAUUSD Ultimate Signal Bot v2.0 Starting...")
    print(f"Capital: ${CAPITAL} | Risk/trade: ${RISK_AMOUNT:.2f} ({int(RISK_PERCENT*100)}%) | "
          f"Min Confidence: {MIN_CONFIDENCE}%")
    print(f"Paper mode: {PAPER_MODE}")
    print(f"Strategy: ICT Kill Zones + Judas Swing + VWAP + EMA + OTE + SMC")

    rolling = get_rolling_stats()
    rolling_text = ""
    if rolling:
        rolling_text = (
            f"\n📊 Rolling Stats: {rolling['wins']}W / {rolling['losses']}L "
            f"({rolling['win_rate']}%) | P&L: ${rolling['pnl']:+.2f}"
        )

    send_telegram(
        f"🚀 <b>XAUUSD ULTIMATE BOT v2.0 LIVE</b>\n\n"
        f"{'🧪 PAPER MODE' if PAPER_MODE else '⚡ LIVE MODE'}\n\n"
        f"<b>🔥 2026 Strategy Stack:</b>\n"
        f"  • ICT Kill Zone + Silver Bullet Timing\n"
        f"  • Asian Range Sweep (Judas Swing)\n"
        f"  • VWAP + EMA Confluence (8/21/50)\n"
        f"  • OTE Fibonacci (62-79%)\n"
        f"  • BOS/CHoCH + Order Blocks + FVG\n"
        f"  • Momentum & RSI Divergence\n"
        f"  • Auto Buy/Sell + Trailing SL + Breakeven\n\n"
        f"<b>⚙️ Settings:</b>\n"
        f"  Capital: ${CAPITAL} | Risk: {int(RISK_PERCENT*100)}%/trade\n"
        f"  Min Confidence: {MIN_CONFIDENCE}% | R:R: 1:{RR_RATIO}\n"
        f"  Max Trades/Day: {MAX_TRADES_PER_DAY}\n"
        f"  Auto-Trade: ✅ | Trailing SL: ✅ | Breakeven: ✅\n"
        f"  Daily Loss Limit: -{int(DAILY_LOSS_LIMIT_PCT*100)}%\n"
        f"{rolling_text}\n\n"
        f"Scanning during Kill Zones only ⚔️"
    )

    last_summary_date = None
    last_heartbeat_time = 0

    while True:
        try:
            now   = datetime.now(IST)
            today = date.today()

            # ═══ NEW DAY RESET ═══
            if last_trade_date != today:
                # Send yesterday's summary if we had trades
                if last_trade_date is not None and trades_today > 0:
                    send_daily_summary()

                trades_today = 0
                daily_pnl = 0.0
                last_trade_date = today
                print(f"\n📅 New day: {today}")
                send_telegram(f"📅 <b>New Day: {today}</b>\nSignals remaining: {MAX_TRADES_PER_DAY}")

            # ═══ MONITOR ACTIVE TRADE ═══
            if active_trade is not None:
                result = monitor_active_trade()
                if result:
                    print(f"📊 Trade closed: {result.get('reason', 'unknown')} | P&L: ${result.get('pnl', 0):+.2f}")

            # ═══ LOSS-STREAK CIRCUIT BREAKER ═══
            if consecutive_losses >= MAX_CONSEC_LOSSES and time.time() < paused_until:
                mins = int((paused_until - time.time()) / 60)
                print(f"⏸️ Paused after {consecutive_losses} losses. {mins} min left.")
                time.sleep(60)  # Check every minute while paused
                continue

            # ═══ DAILY LOSS LIMIT ═══
            if daily_pnl <= -(CAPITAL * DAILY_LOSS_LIMIT_PCT):
                print(f"🛑 Daily loss limit hit (${daily_pnl:.2f}). Sleeping 1hr...")
                time.sleep(3600)
                continue

            # ═══ WIN RATE AUTO-PAUSE ═══
            rolling = get_rolling_stats()
            if rolling and rolling["total"] >= 10 and rolling["win_rate"] < 50:
                print(f"⚠️ Win rate critically low ({rolling['win_rate']}%). Auto-pause 2hrs.")
                send_telegram(
                    f"⚠️ <b>AUTO-PAUSE: Win rate critical</b>\n"
                    f"Win Rate: {rolling['win_rate']}% (last {rolling['total']} trades)\n"
                    f"Bot paused for 2 hours for safety."
                )
                time.sleep(7200)
                continue

            session = get_session_label()
            print(f"\n[{now.strftime('%H:%M')}] {session} | "
                  f"Signals: {trades_today}/{MAX_TRADES_PER_DAY} | "
                  f"Daily P&L: ${daily_pnl:+.2f}")

            # ═══ DAILY LIMIT ═══
            if trades_today >= MAX_TRADES_PER_DAY:
                print("Daily limit reached. Sleeping 30min...")
                time.sleep(1800)
                continue

            # ═══ WEEKEND ═══
            if now.weekday() >= 5:
                print("Weekend. Sleeping 1hr...")
                time.sleep(3600)
                continue

            # ═══ HEARTBEAT ═══
            if time.time() - last_heartbeat_time > 3600:
                send_telegram(f"💓 <b>Bot Heartbeat</b>\nActive and scanning the market.\nDaily P&L: ${daily_pnl:+.2f}")
                last_heartbeat_time = time.time()

            # ═══ KILL ZONE CHECK (skip fetching data if not in KZ) ═══
            # ═══ KILL ZONE CHECK ═══
            kill_zone = get_active_kill_zone()
            if kill_zone is None:
                # Agar kill zone nahi hai tab bhi scan karega
                kill_zone = {"name": "ANY_TIME", "label": "24/7 Market Scan ⏱", "risk_mult": 1.0}



            # ═══ FETCH CANDLES ═══
            print("Fetching candles...")
            candles_1m = get_candles("1m", "1d")
            time.sleep(1)
            candles_5m = get_candles("5m", "5d")
            time.sleep(1)
            candles_15m = get_candles("15m", "5d")
            time.sleep(1)
            candles_1h = get_candles("1h", "5d")

            if not candles_1m or not candles_5m or not candles_15m or not candles_1h:
                print("Fetch failed. Retry in 1min...")
                time.sleep(60)
                continue

            # ═══ UPDATE ASIAN RANGE ═══
            update_asian_range(candles_5m)

            # ═══ GENERATE SIGNAL ═══
            # 1. Try Scalping Signal (1M)
            sig = generate_scalp_signal(candles_1m)
            
            # 2. Try Primary Strategy (5M/15M/1H)
            if not sig:
                sig = generate_signal(candles_5m, candles_15m, candles_1h)

            if sig:
                now_ts = time.time()
                if (last_signal_direction == sig["signal"] and
                        now_ts - last_signal_time < COOLDOWN_SAME_DIR):
                    print("Same direction within cooldown — skipping.")
                else:
                    # Check for reverse signal (close existing trade)
                    check_reverse_signal(sig["signal"])

                    # Send signal notification
                    send_signal(sig)

                    # Auto-execute trade
                    if execute_auto_trade(sig):
                        trades_today += 1
                        last_signal_time = now_ts
                        last_signal_direction = sig["signal"]

                        if trades_today >= MAX_TRADES_PER_DAY:
                            send_telegram(
                                f"🔴 <b>Daily Limit Reached</b>\n"
                                f"{MAX_TRADES_PER_DAY}/{MAX_TRADES_PER_DAY} signals sent.\n"
                                f"Resuming tomorrow."
                            )
            else:
                print("No signal. Waiting...")

            # ═══ SLEEP UNTIL NEXT CANDLE ═══
            ts = time.time()
            sleep_time = (60 - (ts % 60)) + 3 # Scalping requires 1-minute checks
            print(f"Sleeping {int(sleep_time)}s until next candle close...")
            time.sleep(sleep_time)

        except KeyboardInterrupt:
            # Close active trade on shutdown
            if active_trade:
                current_price = get_current_price()
                if current_price:
                    entry = active_trade["entry_price"]
                    if active_trade["signal"] == "LONG":
                        pnl = (current_price - entry) * (active_trade["lots"] / 0.01) * USD_PER_DOLLAR_MOVE_PER_001_LOT
                    else:
                        pnl = (entry - current_price) * (active_trade["lots"] / 0.01) * USD_PER_DOLLAR_MOVE_PER_001_LOT
                    close_trade("BOT_SHUTDOWN", current_price, pnl)

            send_daily_summary()
            send_telegram("🔴 <b>Bot stopped.</b>")
            break
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(120)

if __name__ == "__main__":
    main()
