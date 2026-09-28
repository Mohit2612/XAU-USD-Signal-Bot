"""
engine/safety.py — Safety Validation Layer

Every outgoing message passes through this layer before delivery.

Features:
  - Banned phrase detection
  - Auto-disclaimer injection
  - Missing stop-loss rejection
  - Kill switch (fallback mode)
  - India Mode (SEBI/RBI/FEMA compliance messaging)
  - Logging of all signals
"""

import os
import json
import time
from datetime import datetime
import pytz

IST = pytz.timezone('Asia/Kolkata')

# ============================================
# KILL SWITCH
# ============================================
# Set KILL_SWITCH=1 in env to disable all signal generation.
# The bot will still scan the market but won't send any trade signals.

def is_kill_switch_active():
    """Check if kill switch is engaged."""
    return os.environ.get("KILL_SWITCH", "0") == "1"


def kill_switch_message():
    """Fallback message when kill switch is active."""
    return (
        "🔴 <b>SYSTEM PAUSED — Kill Switch Active</b>\n\n"
        "Signal generation has been temporarily disabled by the administrator.\n"
        "Market scanning continues in the background.\n\n"
        "⚠️ <i>This is a safety measure. Do not trade based on stale signals.</i>"
    )


# ============================================
# BANNED PHRASES
# ============================================
BANNED_PHRASES = [
    # Guaranteed profit claims
    "guaranteed profit",
    "guaranteed return",
    "100% sure",
    "100% guaranteed",
    "can't lose",
    "cannot lose",
    "risk free",
    "risk-free",
    "no risk",
    "zero risk",
    "sure shot",
    "sureshot",
    "guaranteed winner",
    "never lose",

    # Unlicensed advice claims
    "financial advisor",
    "investment advisor",
    "certified advisor",
    "licensed advisor",
    "sebi registered",
    "sebi certified",

    # Offshore broker promotion
    "open account with",
    "sign up with broker",
    "use my referral",
    "use this broker",
    "deposit with",

    # Pump/manipulation language
    "pump",
    "to the moon",
    "going to 10x",
    "free money",
    "easy money",
    "insider tip",
    "insider info",
]


def check_banned_phrases(text):
    """
    Scan text for banned phrases.
    Returns (is_clean, list_of_violations).
    """
    text_lower = text.lower()
    violations = []
    for phrase in BANNED_PHRASES:
        if phrase in text_lower:
            violations.append(phrase)
    return len(violations) == 0, violations


# ============================================
# STOP-LOSS VALIDATION
# ============================================
def validate_signal_has_stoploss(signal):
    """
    MANDATORY: Every signal must have a valid stop-loss.
    Returns (is_valid, error_message).
    """
    if signal is None:
        return True, ""  # No signal = no trade = valid

    sl_price = signal.get("sl_price")
    sl_distance = signal.get("sl_distance")

    if sl_price is None or sl_distance is None:
        return False, "REJECTED: Signal missing stop-loss price."

    if sl_distance <= 0:
        return False, "REJECTED: Stop-loss distance is zero or negative."

    entry = signal.get("entry_price", 0)
    if signal.get("signal") == "LONG" and sl_price >= entry:
        return False, "REJECTED: LONG signal SL is above entry price."
    if signal.get("signal") == "SHORT" and sl_price <= entry:
        return False, "REJECTED: SHORT signal SL is below entry price."

    return True, ""


# ============================================
# INDIA MODE — SEBI/RBI/FEMA COMPLIANCE
# ============================================
INDIA_MODE = os.environ.get("INDIA_MODE", "1") == "1"  # On by default

INDIA_DISCLAIMER = (
    "\n\n🇮🇳 <b>IMPORTANT FOR INDIAN USERS:</b>\n"
    "• Forex trading by Indian residents is restricted under FEMA.\n"
    "• Only INR-based pairs on recognized exchanges (NSE/BSE) are legally permitted.\n"
    "• This bot is for EDUCATIONAL PURPOSES ONLY.\n"
    "• We do NOT recommend any offshore broker.\n"
    "• Consult a SEBI-registered advisor before investing.\n"
    "• RBI guidelines prohibit leveraged forex trading on unauthorized platforms."
)

INDIA_DISCLAIMER_HINDI = (
    "\n\n🇮🇳 <b>INDIAN USERS KE LIYE ZAROORI:</b>\n"
    "• Indian residents ke liye forex trading FEMA ke under restricted hai.\n"
    "• Sirf INR-based pairs jo recognized exchanges (NSE/BSE) pe hain — legally allowed hain.\n"
    "• Ye bot EDUCATIONAL PURPOSE ke liye hai.\n"
    "• Hum koi offshore broker RECOMMEND NAHI karte.\n"
    "• Invest karne se pehle SEBI-registered advisor se consult karo.\n"
    "• RBI guidelines ke according unauthorized platforms pe leveraged forex trading prohibited hai."
)


def apply_india_mode(message, language="hinglish"):
    """Append India-specific regulatory disclaimers if India Mode is on."""
    if not INDIA_MODE:
        return message
    disclaimer = INDIA_DISCLAIMER_HINDI if language == "hinglish" else INDIA_DISCLAIMER
    return message + disclaimer


# ============================================
# SIGNAL LOGGING
# ============================================
SIGNAL_LOG_FILE = "signal_log.json"


def log_signal(signal, message, was_blocked=False, block_reason=""):
    """Log every signal attempt for audit trail."""
    entry = {
        "timestamp": datetime.now(IST).isoformat(),
        "pair": signal.get("pair", "N/A") if signal else "N/A",
        "direction": signal.get("signal", "NONE") if signal else "NO_TRADE",
        "confidence": signal.get("confidence", 0) if signal else 0,
        "entry_price": signal.get("entry_price", 0) if signal else 0,
        "sl_price": signal.get("sl_price", 0) if signal else 0,
        "tp_price": signal.get("tp_price", 0) if signal else 0,
        "was_blocked": was_blocked,
        "block_reason": block_reason,
        "message_length": len(message),
    }

    try:
        log = []
        if os.path.exists(SIGNAL_LOG_FILE):
            with open(SIGNAL_LOG_FILE, "r") as f:
                log = json.load(f)
        log.append(entry)
        # Keep last 500 entries
        log = log[-500:]
        with open(SIGNAL_LOG_FILE, "w") as f:
            json.dump(log, f, indent=2)
    except Exception as e:
        print(f"Signal log error: {e}")


# ============================================
# FULL VALIDATION PIPELINE
# ============================================
def validate_and_sanitize(signal, message, language="hinglish"):
    """
    Run the full safety pipeline on a signal + message.

    Returns (final_message, is_allowed, block_reason).
    """
    # 1. Kill switch check
    if is_kill_switch_active():
        msg = kill_switch_message()
        log_signal(signal, msg, was_blocked=True, block_reason="KILL_SWITCH")
        return msg, False, "KILL_SWITCH"

    # 2. Stop-loss validation
    sl_valid, sl_error = validate_signal_has_stoploss(signal)
    if not sl_valid:
        log_signal(signal, sl_error, was_blocked=True, block_reason=sl_error)
        return None, False, sl_error

    # 3. Banned phrase check
    is_clean, violations = check_banned_phrases(message)
    if not is_clean:
        reason = f"BANNED_PHRASES: {', '.join(violations)}"
        log_signal(signal, message, was_blocked=True, block_reason=reason)
        # Strip the banned phrases and add a warning
        cleaned = message
        for v in violations:
            cleaned = cleaned.replace(v, "[REDACTED]")
        cleaned += "\n\n⚠️ <i>Some content was filtered by the safety system.</i>"
        message = cleaned

    # 4. India Mode
    message = apply_india_mode(message, language)

    # 5. Log the signal
    log_signal(signal, message)

    return message, True, ""
