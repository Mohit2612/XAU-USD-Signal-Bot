"""
engine/formatter.py — Telegram Signal Message Formatter & Validator

Formats and validates all outgoing Telegram alerts (Trade Signals, No-Trade,
Trade Closed, Discipline Notes) according to exact beginner-level templates.

Features:
  - 4 strict message templates with fixed field ordering
  - Strict field validation (SL direction, RR >= 1:2, banned words)
  - Capped message length (~700 chars max) with mentor line truncation
  - Deduplication within a time window
  - MENTOR_LINES=off support
  - Caching and sequential lesson curriculum rotation
"""

import os
import re
import time
from datetime import datetime
import pytz

import data_layer as dl
from engine import templates

IST = pytz.timezone('Asia/Kolkata')

# Deduplication cache: {(pair, direction, rounded_entry): timestamp}
_recent_signals = {}

# Lesson curriculum index tracker
_lesson_index = 0

BANNED_WORDS = [
    "guaranteed",
    "sure shot",
    "sureshot",
    "risk-free",
    "risk free",
    "100%",
    "double your money",
    "easy profit",
    "jackpot",
]


def check_banned_words(text):
    """Check text for banned words. Returns (is_clean, found_words)."""
    text_lower = text.lower()
    found = [w for w in BANNED_WORDS if w in text_lower]
    return len(found) == 0, found


def get_next_lesson(language="hinglish"):
    """Rotate sequentially through the lesson curriculum pool."""
    global _lesson_index
    pool = (
        templates.LESSON_CURRICULUM_HINGLISH
        if language == "hinglish"
        else templates.LESSON_CURRICULUM_ENGLISH
    )
    lesson = pool[_lesson_index % len(pool)]
    _lesson_index += 1
    return lesson


def is_duplicate_signal(pair, direction, entry_price, window_seconds=900):
    """Check if the same signal was recently sent within window_seconds."""
    now = time.time()
    key = (pair, direction, round(float(entry_price), 2))
    last_time = _recent_signals.get(key, 0)
    if (now - last_time) < window_seconds:
        return True
    return False


def register_signal(pair, direction, entry_price):
    """Register a sent signal in the deduplication cache."""
    key = (pair, direction, round(float(entry_price), 2))
    _recent_signals[key] = time.time()


def validate_signal_fields(signal):
    """
    Code-level validation of signal fields.

    Returns (is_valid, error_reason).
    """
    if not signal:
        return False, "Signal is None"

    if signal.get("signal") == "NO_TRADE":
        return False, "Signal is NO_TRADE"

    required = ["pair", "signal", "entry_price", "sl_price", "tp_price", "lots", "rr_ratio"]
    for field in required:
        if signal.get(field) is None:
            return False, f"Missing required field: {field}"

    pair = signal["pair"]
    direction = signal["signal"].upper()
    entry = float(signal["entry_price"])
    sl = float(signal["sl_price"])
    tp = float(signal["tp_price"])
    lots = float(signal["lots"])
    rr = float(signal.get("rr_ratio", 0))

    # Direction check
    if direction not in ("LONG", "BUY", "SHORT", "SELL"):
        return False, f"Invalid direction: {direction}"

    # SL side validation
    if direction in ("LONG", "BUY") and sl >= entry:
        return False, f"REJECTED: LONG SL ({sl}) must be below entry ({entry})"
    if direction in ("SHORT", "SELL") and sl <= entry:
        return False, f"REJECTED: SHORT SL ({sl}) must be above entry ({entry})"

    # RR validation: Must be >= 1:2 (2.0)
    if rr < 1.99:
        return False, f"REJECTED: RR ratio ({rr:.1f}) is less than 1:2"

    # Lots validation
    if lots <= 0:
        return False, "REJECTED: Lots is 0 (capital too small for setup)"

    # Pair enabled check
    asset_cfg = dl.ASSETS.get(pair, {})
    if not asset_cfg.get("enabled", True):
        return False, f"REJECTED: Pair {pair} is disabled"

    return True, ""


def truncate_line(text, max_chars=90):
    """Truncate a string to max_chars with ellipsis if needed."""
    if not text:
        return ""
    text = text.strip()
    if len(text) > max_chars:
        return text[: max_chars - 3] + "..."
    return text


def format_trade_signal_message(signal, language="hinglish", level_label="Beginner"):
    """
    Format a Trade Signal into the exact 12-line beginner template.

    Returns (formatted_text, is_valid, error_reason).
    """
    valid, err = validate_signal_fields(signal)
    if not valid:
        return None, False, err

    pair = signal["pair"]
    direction_raw = signal["signal"].upper()
    dir_str = "BUY 🟢" if direction_raw in ("LONG", "BUY") else "SELL 🔴"

    entry = float(signal["entry_price"])
    sl = float(signal["sl_price"])
    tp = float(signal["tp_price"])

    asset_cfg = dl.ASSETS.get(pair, {})
    prec = asset_cfg.get("price_decimals", 2)
    instrument_type = asset_cfg.get("instrument_type", "spot")

    spot_note = " (spot)" if instrument_type == "futures" else ""

    entry_fmt = f"{entry:.{prec}f}{spot_note}"
    sl_fmt = f"{sl:.{prec}f}"
    tp_fmt = f"{tp:.{prec}f}"

    lots_val = signal.get("lots", 1)
    lots_str = f"{int(lots_val)}" if isinstance(lots_val, int) or (isinstance(lots_val, float) and lots_val.is_integer()) else f"{lots_val:.2f}"

    rr_val = float(signal.get("rr_ratio", 2.0))
    rr_str = f"1:{rr_val:.1f}"

    risk_pct = float(signal.get("risk_pct", 1.0))

    # Deduplication check
    if is_duplicate_signal(pair, direction_raw, entry):
        return None, False, "DEDUPLICATED: Identical signal recently sent"

    # MENTOR_LINES=off default (clean trade fields only: Pair, Direction, Entry, SL, Target, Lots, RR, Risk)
    mentor_lines_env = os.environ.get("MENTOR_LINES", "off").lower()
    if mentor_lines_env == "off":
        msg = templates.TRADE_SIGNAL_SHORT_TEMPLATE.format(
            pair=pair,
            direction_emoji=dir_str,
            entry=entry_fmt,
            stop_loss=sl_fmt,
            target=tp_fmt,
            lots=lots_str,
            level_label=level_label,
            rr_str=rr_str,
            risk_pct=risk_pct,
        )
        register_signal(pair, direction_raw, entry)
        return msg, True, ""

    # Generate Mentor lines
    reasons = signal.get("reasons", ["Confluence setup"])
    why_raw = f"{pair} {level_label} setup - " + (reasons[0] if reasons else "Pattern Confluence")
    caution_raw = "SL order zaroori hai. Risk management maintain rakho."
    lesson_raw = get_next_lesson(language)

    why = truncate_line(why_raw, 90)
    caution = truncate_line(caution_raw, 90)
    lesson = truncate_line(lesson_raw, 90)

    template = (
        templates.TRADE_SIGNAL_TEMPLATE_HINGLISH
        if language == "hinglish"
        else templates.TRADE_SIGNAL_TEMPLATE_ENGLISH
    )

    msg = template.format(
        pair=pair,
        direction_emoji=dir_str,
        entry=entry_fmt,
        stop_loss=sl_fmt,
        target=tp_fmt,
        lots=lots_str,
        level_label=level_label,
        rr_str=rr_str,
        risk_pct=risk_pct,
        why=why,
        caution=caution,
        lesson=lesson,
    )

    # Banned words validation
    clean, banned_found = check_banned_words(msg)
    if not clean:
        return None, False, f"REJECTED: Contains banned words: {', '.join(banned_found)}"

    # Max length check (~700 chars)
    if len(msg) > 700:
        # Truncate mentor lines further if overflowing
        why = truncate_line(why_raw, 50)
        caution = truncate_line(caution_raw, 50)
        lesson = truncate_line(lesson_raw, 50)
        msg = template.format(
            pair=pair,
            direction_emoji=dir_str,
            entry=entry_fmt,
            stop_loss=sl_fmt,
            target=tp_fmt,
            lots=lots_str,
            level_label=level_label,
            rr_str=rr_str,
            risk_pct=risk_pct,
            why=why,
            caution=caution,
            lesson=lesson,
        )

    register_signal(pair, direction_raw, entry)
    return msg, True, ""


def format_no_trade_message(reason_short, language="hinglish"):
    """Format a No-Trade notification."""
    lesson = get_next_lesson(language)
    template = (
        templates.NO_TRADE_TEMPLATE_HINGLISH
        if language == "hinglish"
        else templates.NO_TRADE_TEMPLATE_ENGLISH
    )
    reason_clean = truncate_line(reason_short, 80)
    return template.format(reason_short=reason_clean, lesson=lesson)


def format_trade_closed_message(pair, outcome_status, pnl, language="hinglish"):
    """Format a Trade Closed notification."""
    lesson = get_next_lesson(language)
    template = (
        templates.TRADE_CLOSED_TEMPLATE_HINGLISH
        if language == "hinglish"
        else templates.TRADE_CLOSED_TEMPLATE_ENGLISH
    )
    pnl_str = f"${pnl:+.2f}" if isinstance(pnl, (int, float)) else str(pnl)
    return template.format(
        pair=pair,
        outcome_status=outcome_status,
        pnl_str=pnl_str,
        lesson=lesson,
    )


def format_discipline_note_message(consecutive_losses, language="hinglish"):
    """Format a Daily Loss Lock / Discipline Note notification."""
    template = (
        templates.DISCIPLINE_NOTE_TEMPLATE_HINGLISH
        if language == "hinglish"
        else templates.DISCIPLINE_NOTE_TEMPLATE_ENGLISH
    )
    return template.format(consecutive_losses=consecutive_losses)
