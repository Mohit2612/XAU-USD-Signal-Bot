"""
engine/telegram_bot.py — Telegram Bot with /ask command and mentor delivery

Handles:
  - Incoming commands via polling (/start, /ask, /status, /beginner, /language)
  - Signal delivery
  - Interactive /ask Q&A
"""

import os
import json
import time
import requests
import threading
from datetime import datetime
import pytz

import data_layer as dl

IST = pytz.timezone('Asia/Kolkata')

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# User preferences (persisted in memory, could be extended to file)
_user_prefs = {
    "language": "hinglish",  # "hinglish" or "english"
    "beginner_mode": True,
}


def get_language():
    return _user_prefs["language"]


def is_beginner_mode():
    return _user_prefs["beginner_mode"]


def send_message(text, chat_id=None):
    """Send a message to Telegram."""
    if not TELEGRAM_TOKEN:
        print("Telegram not configured; skipping send.")
        return
    target = chat_id or TELEGRAM_CHAT_ID
    if not target:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    # Telegram has a 4096 char limit per message
    if len(text) > 4000:
        # Split into parts
        parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for part in parts:
            payload = {"chat_id": target, "text": part, "parse_mode": "HTML"}
            try:
                r = requests.post(url, json=payload, timeout=10)
                print(f"Telegram: {r.status_code}")
            except Exception as e:
                print(f"Telegram error: {e}")
    else:
        payload = {"chat_id": target, "text": text, "parse_mode": "HTML"}
        try:
            r = requests.post(url, json=payload, timeout=10)
            print(f"Telegram: {r.status_code}")
        except Exception as e:
            print(f"Telegram error: {e}")


# ============================================
# /ask COMMAND — Interactive Q&A
# ============================================
ASK_RESPONSES = {
    "what is sl": (
        "🎓 <b>Stop Loss (SL)</b>\n\n"
        "SL ek price level hai jahan pe aapka trade automatically close ho jaata hai "
        "agar market aapke against jaaye.\n\n"
        "Ye aapka 'safety net' hai — ye ensure karta hai ki aap apne poore capital ko "
        "ek hi trade mein na kho do.\n\n"
        "🔑 Rule: SL HAMESHA lagao. Bina SL ke trade karna gambling hai, trading nahi."
    ),
    "what is tp": (
        "🎓 <b>Take Profit (TP)</b>\n\n"
        "TP woh price level hai jahan aap apna profit book karte ho.\n\n"
        "Jab price TP tak pahunchta hai, trade automatically close ho jaata hai "
        "aur profit lock ho jaata hai.\n\n"
        "🔑 Tip: TP ko Risk:Reward ratio ke hisaab se set karo (e.g., 1:2.5)."
    ),
    "what is rr": (
        "🎓 <b>Risk:Reward Ratio (R:R)</b>\n\n"
        "Ye batata hai ki har $1 risk ke against kitna potential profit hai.\n\n"
        "Example: 1:2.5 R:R = $1 risk ke liye $2.50 potential profit.\n\n"
        "🔑 Aim for minimum 1:2 R:R. Isse aap 40% win rate pe bhi profitable reh sakte ho."
    ),
    "what is fvg": (
        "🎓 <b>Fair Value Gap (FVG)</b>\n\n"
        "FVG ek 'gap' hai price mein jahan buying ya selling bahut fast hui thi.\n"
        "Ye imbalance hai — market often wapas aata hai is gap ko fill karne.\n\n"
        "Think of it as 'unfinished business' in the chart.\n\n"
        "🔑 FVGs best work karte hain jab trend ke direction mein use karein."
    ),
    "what is order block": (
        "🎓 <b>Order Block (OB)</b>\n\n"
        "Order Block woh zone hai jahan institutional traders ne bade orders place kiye.\n"
        "Ye ek 'zone of interest' hai jahan price react karne ki probability high hai.\n\n"
        "Bullish OB: Last bearish candle before a big move up.\n"
        "Bearish OB: Last bullish candle before a big move down.\n\n"
        "🔑 OBs are high-probability entry zones."
    ),
    "what is bos": (
        "🎓 <b>Break of Structure (BOS)</b>\n\n"
        "BOS tab hota hai jab price ek key swing high ya low ko break karta hai.\n\n"
        "Bullish BOS: Price breaks above a swing high → trend is up.\n"
        "Bearish BOS: Price breaks below a swing low → trend is down.\n\n"
        "🔑 BOS confirms the trend direction. Trade WITH the BOS, not against it."
    ),
    "what is choch": (
        "🎓 <b>Change of Character (CHoCH)</b>\n\n"
        "CHoCH ek early reversal signal hai.\n"
        "Ye BOS ka opposite hai — jab trend change hone lagta hai.\n\n"
        "Example: Market downtrend mein tha, suddenly price breaks above a swing high "
        "= CHoCH = possible reversal to uptrend.\n\n"
        "🔑 CHoCH is a STRONG signal but needs confirmation from other indicators."
    ),
    "what is kill zone": (
        "🎓 <b>Kill Zones</b>\n\n"
        "Kill Zones woh specific time windows hain jab market mein sabse zyada "
        "movement hoti hai.\n\n"
        "London: 12:30 PM - 3:30 PM IST\n"
        "New York: 6:30 PM - 9:30 PM IST\n"
        "Overlap: 6:30 PM - 8:00 PM IST (best!)\n\n"
        "🔑 Kill Zones mein trade karna = better fills, more movement, cleaner setups."
    ),
}


def handle_ask_command(question):
    """
    Handle /ask <question> command.
    Returns an educational response.
    """
    q = question.strip().lower()

    # Direct match
    for key, response in ASK_RESPONSES.items():
        if key in q:
            return response

    # Fuzzy match attempts
    keywords = {
        "stop loss": "what is sl",
        "stoploss": "what is sl",
        "take profit": "what is tp",
        "risk reward": "what is rr",
        "fair value": "what is fvg",
        "gap": "what is fvg",
        "order block": "what is order block",
        "ob": "what is order block",
        "break of structure": "what is bos",
        "change of character": "what is choch",
        "reversal": "what is choch",
        "kill zone": "what is kill zone",
        "session": "what is kill zone",
    }

    for kw, key in keywords.items():
        if kw in q:
            return ASK_RESPONSES.get(key, "")

    # Default response
    return (
        "🤔 <b>Accha sawaal hai!</b>\n\n"
        "Abhi mere paas is specific topic ka detailed answer nahi hai, "
        "but main constantly seekh raha hoon.\n\n"
        "Try karo ye commands:\n"
        "• /ask what is SL\n"
        "• /ask what is TP\n"
        "• /ask what is RR\n"
        "• /ask what is FVG\n"
        "• /ask what is order block\n"
        "• /ask what is BOS\n"
        "• /ask what is CHoCH\n"
        "• /ask what is kill zone\n"
    )


# ============================================
# COMMAND HANDLER
# ============================================
def handle_command(command, args=""):
    """Process a Telegram command and return a response."""
    cmd = command.lower().strip()

    if cmd == "/start":
        return (
            "🎯 <b>Welcome to Mentor Signal Bot!</b>\n\n"
            "Main tumhara trading mentor hoon — 20+ saal ka experience, "
            "AI ki power ke saath.\n\n"
            "<b>Commands:</b>\n"
            "• /ask [question] — Koi bhi trading concept pucho\n"
            "• /status — Current bot status\n"
            "• /beginner — Toggle Beginner Mode\n"
            "• /language — Switch Hindi/English\n\n"
            "Signals automatically aayenge jab market mein quality setup milega.\n\n"
            "⚠️ <i>AI-generated analysis. Not financial advice.</i>"
        )

    elif cmd == "/status":
        from engine import paper_trading as pt
        stats = pt.get_daily_stats()
        balance = pt.get_virtual_balance()
        active = pt.get_state()["active_trades"]

        return (
            f"📊 <b>Bot Status</b>\n\n"
            f"💵 Balance: ${balance:.2f}\n"
            f"📈 Today: {stats['total']} trades | "
            f"W: {stats['wins']} L: {stats['losses']}\n"
            f"💰 Daily P&L: ${stats['pnl']:+.2f}\n"
            f"📊 Win Rate: {stats['win_rate']:.1f}%\n"
            f"🔄 Active Trades: {len(active)}\n"
            f"🎓 Beginner Mode: {'ON ✅' if is_beginner_mode() else 'OFF'}\n"
            f"🌐 Language: {get_language().title()}"
        )

    elif cmd == "/beginner":
        _user_prefs["beginner_mode"] = not _user_prefs["beginner_mode"]
        status = "ON ✅" if _user_prefs["beginner_mode"] else "OFF"
        return f"🎓 <b>Beginner Mode:</b> {status}\n\nBeginner mode adds extra explanations for every trading concept in signals."

    elif cmd == "/language":
        if _user_prefs["language"] == "hinglish":
            _user_prefs["language"] = "english"
        else:
            _user_prefs["language"] = "hinglish"
        return f"🌐 <b>Language switched to:</b> {_user_prefs['language'].title()}"

    elif cmd == "/ask":
        if args:
            return handle_ask_command(args)
        return "Usage: /ask [question]\nExample: /ask what is SL"

    return None


# ============================================
# POLLING (runs in background thread)
# ============================================
_last_update_id = 0


def poll_updates():
    """Poll Telegram for incoming messages/commands."""
    global _last_update_id

    if not TELEGRAM_TOKEN:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params = {"offset": _last_update_id + 1, "timeout": 5}

    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()

        if not data.get("ok"):
            return

        for update in data.get("result", []):
            _last_update_id = update["update_id"]

            msg = update.get("message", {})
            text = msg.get("text", "")
            chat_id = msg.get("chat", {}).get("id")

            if not text or not chat_id:
                continue

            # Parse command
            if text.startswith("/"):
                parts = text.split(maxsplit=1)
                cmd = parts[0]
                args = parts[1] if len(parts) > 1 else ""

                response = handle_command(cmd, args)
                if response:
                    send_message(response, chat_id=str(chat_id))

    except Exception as e:
        print(f"Telegram poll error: {e}")


def start_polling_thread():
    """Start a background thread that polls Telegram for commands."""
    def _poll_loop():
        while True:
            try:
                poll_updates()
            except Exception as e:
                print(f"Poll loop error: {e}")
            time.sleep(3)

    t = threading.Thread(target=_poll_loop, daemon=True)
    t.start()
    print("📱 Telegram polling thread started.")
