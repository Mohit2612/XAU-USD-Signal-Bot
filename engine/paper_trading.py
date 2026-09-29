"""
engine/paper_trading.py — Paper Trading (Virtual Money) Engine

Tracks virtual trades, P&L, balance, and trade history without
touching any real broker API.

Features:
  - Virtual balance tracking
  - Trade open/close/monitor
  - Daily P&L and stats
  - Trade journal with persistence
  - Rolling performance tracking
"""

import os
import json
import time
from datetime import datetime, date
from collections import deque
import pytz

IST = pytz.timezone('Asia/Kolkata')

# ============================================
# PAPER TRADING STATE
# ============================================
INITIAL_CAPITAL = 500
TRADE_JOURNAL_FILE = "trade_journal.json"
MAX_TRADES_PER_DAY = 10
MAX_CONSEC_LOSSES = 3
COOLDOWN_SAME_DIR = 900  # 15 minutes

# In-memory state
_state = {
    "virtual_balance": INITIAL_CAPITAL,
    "trades_today": 0,
    "last_trade_date": None,
    "consecutive_losses": 0,
    "paused_until": 0,
    "daily_pnl": 0.0,
    "active_trades": {},  # {symbol: trade_dict}
    "last_signal_direction": {},  # {symbol: "LONG"/"SHORT"}
    "last_signal_time": {},  # {symbol: timestamp}
    "trade_journal": [],
    "rolling_trades": deque(maxlen=50),
}


def get_state():
    """Return the current paper trading state."""
    return _state


def get_virtual_balance():
    return _state["virtual_balance"]


# ============================================
# JOURNAL PERSISTENCE
# ============================================
def load_journal():
    """Load trade journal from disk."""
    try:
        if os.path.exists(TRADE_JOURNAL_FILE):
            with open(TRADE_JOURNAL_FILE, "r") as f:
                _state["trade_journal"] = json.load(f)
                print(f"📒 Loaded {len(_state['trade_journal'])} trades from journal.")
    except Exception as e:
        print(f"Journal load error: {e}")
        _state["trade_journal"] = []


def save_journal():
    """Save trade journal to disk."""
    try:
        with open(TRADE_JOURNAL_FILE, "w") as f:
            json.dump(_state["trade_journal"], f, indent=2)
    except Exception as e:
        print(f"Journal save error: {e}")


def save_state_file():
    """Save bot state for the web dashboard."""
    state_out = {
        "capital": INITIAL_CAPITAL,
        "virtual_balance": round(_state["virtual_balance"], 2),
        "daily_pnl": round(_state["daily_pnl"], 2),
        "trades_today": _state["trades_today"],
        "active_trades": _state["active_trades"],
        "consecutive_losses": _state["consecutive_losses"],
        "paused_until": _state["paused_until"],
        "last_signal_direction": _state["last_signal_direction"],
        "last_update": time.time(),
    }
    try:
        with open("state.json", "w") as f:
            json.dump(state_out, f, indent=2)
    except Exception:
        pass


# ============================================
# DAILY RESET
# ============================================
def check_daily_reset():
    """Reset daily counters if it's a new day."""
    today = date.today()
    if _state["last_trade_date"] != today:
        _state["trades_today"] = 0
        _state["daily_pnl"] = 0.0
        _state["last_trade_date"] = today
        return True
    return False


# ============================================
# TRADE MANAGEMENT
# ============================================
def can_trade(symbol):
    """Check if a new trade is allowed for this symbol."""
    if _state["trades_today"] >= MAX_TRADES_PER_DAY:
        return False, "Daily trade limit reached."

    if time.time() < _state["paused_until"]:
        return False, "Paused after consecutive losses or daily loss cap."

    if symbol in _state["active_trades"]:
        return False, f"Active trade already exists for {symbol}."

    # Daily loss cap check
    try:
        from engine import money_management as mm
        cfg = mm.get_money_config()
        cap = float(cfg.get("capital", 50000.0))
        cap_curr = cfg.get("capital_currency", "INR")
        loss_cap_pct = float(cfg.get("daily_loss_cap_pct", 3.0))

        live_usdinr = mm.get_live_usdinr_rate()
        loss_cap_usd = (cap * (loss_cap_pct / 100.0)) / live_usdinr if cap_curr == "INR" else cap * (loss_cap_pct / 100.0)

        if _state["daily_pnl"] <= -loss_cap_usd:
            return False, f"Daily loss cap ({loss_cap_pct}%) reached."
    except Exception as e:
        pass

    return True, ""


def check_cooldown(symbol, direction):
    """Check if same-direction cooldown is in effect."""
    # If no active trade exists, allow new signal after 60s buffer
    if symbol not in _state["active_trades"]:
        last_time = _state["last_signal_time"].get(symbol, 0)
        if (time.time() - last_time) < 60:
            return False
        return True

    last_dir = _state["last_signal_direction"].get(symbol)
    last_time = _state["last_signal_time"].get(symbol, 0)

    if last_dir == direction and (time.time() - last_time) < COOLDOWN_SAME_DIR:
        return False
    return True


def open_trade(signal):
    """Open a paper trade from a signal dict."""
    symbol = signal["pair"]
    entry_price = signal["entry_price"]

    trade = {
        "symbol": symbol,
        "signal": signal["signal"],
        "entry_price": entry_price,
        "sl_price": signal["sl_price"],
        "tp_price": signal["tp_price"],
        "original_sl": signal["sl_price"],
        "lots": signal["lots"],
        "entry_time": time.time(),
        "sl_moved_breakeven": False,
        "sl_moved_lock": False,
        "confidence": signal["confidence"],
        "reasons": signal["reasons"],
        "sl_distance": signal["sl_distance"],
        "tp_distance": signal["tp_distance"],
        "actual_risk": signal["actual_risk"],
        "state": "MONITORING",
    }

    _state["active_trades"][symbol] = trade
    _state["trades_today"] += 1
    _state["last_signal_direction"][symbol] = signal["signal"]
    _state["last_signal_time"][symbol] = time.time()

    return trade


def close_trade(symbol, reason, exit_price):
    """Close a paper trade and log it."""
    if symbol not in _state["active_trades"]:
        return None

    trade = _state["active_trades"][symbol]
    entry = trade["entry_price"]
    contract_size = 100  # Default for XAU/USD

    if trade["signal"] == "LONG":
        pnl = (exit_price - entry) * trade["lots"] * contract_size
    else:
        pnl = (entry - exit_price) * trade["lots"] * contract_size

    pnl = round(pnl, 2)
    _state["virtual_balance"] += pnl
    _state["daily_pnl"] += pnl

    duration = time.time() - trade["entry_time"]
    duration_str = f"{int(duration // 60)}m {int(duration % 60)}s"

    # Update consecutive losses
    if pnl <= 0:
        _state["consecutive_losses"] += 1
        if _state["consecutive_losses"] >= MAX_CONSEC_LOSSES:
            _state["paused_until"] = time.time() + 3600  # 1 hour pause
    else:
        _state["consecutive_losses"] = 0

    now_ist = datetime.now(IST).strftime('%d %b %Y %H:%M IST')

    record = {
        "date": date.today().isoformat(),
        "time": now_ist,
        "symbol": symbol,
        "signal": trade["signal"],
        "entry": entry,
        "exit": exit_price,
        "sl": trade["original_sl"],
        "tp": trade["tp_price"],
        "lots": trade["lots"],
        "pnl": pnl,
        "reason": reason,
        "confidence": trade["confidence"],
        "duration": duration_str,
    }

    _state["trade_journal"].append(record)
    _state["rolling_trades"].append(record)
    save_journal()

    del _state["active_trades"][symbol]
    return record


def monitor_trade(symbol, current_price):
    """
    Monitor an active paper trade. Returns close record or None.
    """
    if symbol not in _state["active_trades"]:
        return None

    trade = _state["active_trades"][symbol]
    signal = trade["signal"]
    sl = trade["sl_price"]
    tp = trade["tp_price"]

    # Check TP hit
    if signal == "LONG" and current_price >= tp:
        return close_trade(symbol, "TP_HIT", current_price)
    elif signal == "SHORT" and current_price <= tp:
        return close_trade(symbol, "TP_HIT", current_price)

    # Check SL hit
    if signal == "LONG" and current_price <= sl:
        return close_trade(symbol, "SL_HIT", current_price)
    elif signal == "SHORT" and current_price >= sl:
        return close_trade(symbol, "SL_HIT", current_price)

    # Check time expiry (2 hours)
    elapsed = time.time() - trade["entry_time"]
    if elapsed >= 7200:
        return close_trade(symbol, "TIME_EXIT", current_price)

    # Trailing SL logic
    entry = trade["entry_price"]
    tp_dist = trade["tp_distance"]

    if signal == "LONG":
        progress = (current_price - entry) / tp_dist if tp_dist > 0 else 0
    else:
        progress = (entry - current_price) / tp_dist if tp_dist > 0 else 0

    # Move to breakeven at 50%
    if not trade["sl_moved_breakeven"] and progress >= 0.50:
        if signal == "LONG":
            new_sl = entry + 0.50
            if new_sl > trade["sl_price"]:
                trade["sl_price"] = new_sl
                trade["sl_moved_breakeven"] = True
        else:
            new_sl = entry - 0.50
            if new_sl < trade["sl_price"]:
                trade["sl_price"] = new_sl
                trade["sl_moved_breakeven"] = True

    # Lock profit at 75%
    if not trade["sl_moved_lock"] and progress >= 0.75:
        lock_dist = tp_dist * 0.50
        if signal == "LONG":
            new_sl = entry + lock_dist
            if new_sl > trade["sl_price"]:
                trade["sl_price"] = new_sl
                trade["sl_moved_lock"] = True
        else:
            new_sl = entry - lock_dist
            if new_sl < trade["sl_price"]:
                trade["sl_price"] = new_sl
                trade["sl_moved_lock"] = True

    return None


# ============================================
# STATS
# ============================================
def get_daily_stats():
    """Get today's trading stats."""
    today_str = date.today().isoformat()
    today_trades = [t for t in _state["trade_journal"] if t.get("date") == today_str]
    wins = sum(1 for t in today_trades if t.get("pnl", 0) > 0)
    losses = sum(1 for t in today_trades if t.get("pnl", 0) <= 0)
    total_pnl = sum(t.get("pnl", 0) for t in today_trades)
    return {
        "total": len(today_trades),
        "wins": wins,
        "losses": losses,
        "pnl": round(total_pnl, 2),
        "win_rate": round(wins / len(today_trades) * 100, 1) if today_trades else 0,
    }


def get_rolling_stats():
    """Get rolling performance stats."""
    if not _state["rolling_trades"]:
        return None
    wins = sum(1 for t in _state["rolling_trades"] if t.get("pnl", 0) > 0)
    total = len(_state["rolling_trades"])
    total_pnl = sum(t.get("pnl", 0) for t in _state["rolling_trades"])
    return {
        "total": total,
        "wins": wins,
        "losses": total - wins,
        "pnl": round(total_pnl, 2),
        "win_rate": round(wins / total * 100, 1) if total else 0,
    }
