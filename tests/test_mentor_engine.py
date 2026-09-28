"""
tests/test_mentor_engine.py — Basic tests for the refactored system.

Tests:
  1. Data layer returns valid data (or gracefully handles no data)
  2. Signal generation end-to-end from mock data
  3. Safety layer blocks banned phrases
  4. Missing stop-loss is rejected
  5. Kill switch falls back cleanly
"""

import os
import sys
import json
import unittest

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import signal_engine, mentor, safety, paper_trading, telegram_bot
import data_layer as dl


class TestDataLayer(unittest.TestCase):
    """Test that the data layer interface works."""

    def test_assets_registry_exists(self):
        """ASSETS config should be populated."""
        self.assertIn("XAU/USD", dl.ASSETS)
        self.assertEqual(dl.ASSETS["XAU/USD"]["type"], "commodity")
        self.assertTrue(dl.ASSETS["XAU/USD"]["enabled"])

    def test_get_historical_returns_list(self):
        """get_historical should return a list (even if empty)."""
        result = dl.get_historical("XAU/USD", "1h", 10)
        self.assertIsInstance(result, list)

    def test_ema_calculation(self):
        """EMA calculation should work on simple data."""
        values = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
        ema = dl.calculate_ema(values, 5)
        self.assertIsInstance(ema, float)
        self.assertGreater(ema, 0)

    def test_rsi_calculation(self):
        """RSI should return a value between 0 and 100."""
        candles = [{"close": 100 + i * 0.5, "high": 101 + i * 0.5,
                     "low": 99 + i * 0.5, "open": 100 + i * 0.5}
                    for i in range(20)]
        rsi = dl.calculate_rsi(candles)
        self.assertGreaterEqual(rsi, 0)
        self.assertLessEqual(rsi, 100)

    def test_atr_calculation(self):
        """ATR should return None for insufficient data or a positive float."""
        candles = [{"close": 100 + i, "high": 101 + i,
                     "low": 99 + i, "open": 100 + i}
                    for i in range(20)]
        atr = dl.calculate_atr(candles)
        self.assertIsNotNone(atr)
        self.assertGreater(atr, 0)

    def test_session_label(self):
        """Session label should return a non-empty string."""
        label = dl.get_session_label()
        self.assertIsInstance(label, str)
        self.assertGreater(len(label), 0)


class TestSignalEngine(unittest.TestCase):
    """Test signal generation from mock data."""

    def _make_candles(self, count, base_price=2650, trend="up"):
        """Generate mock candle data."""
        candles = []
        for i in range(count):
            if trend == "up":
                o = base_price + i * 0.5
                c = o + 1.0
                h = c + 0.3
                l = o - 0.2
            elif trend == "down":
                o = base_price - i * 0.5
                c = o - 1.0
                h = o + 0.2
                l = c - 0.3
            else:
                o = base_price + (i % 3 - 1) * 0.3
                c = o + 0.1
                h = max(o, c) + 0.2
                l = min(o, c) - 0.2
            candles.append({
                "time": f"2026-09-28 {10 + i // 12}:{(i % 12) * 5:02d}:00",
                "open": round(o, 2),
                "high": round(h, 2),
                "low": round(l, 2),
                "close": round(c, 2),
            })
        return candles

    def test_generate_signal_from_mock_data(self):
        """Signal engine should produce a signal or None from valid mock data."""
        snapshot = {
            "pair": "XAU/USD",
            "candles_5m": self._make_candles(100, trend="up"),
            "candles_15m": self._make_candles(60, trend="up"),
            "candles_1h": self._make_candles(50, trend="up"),
            "current_price": 2700.0,
            "session": {"name": "LONDON", "label": "London Kill Zone 🇬🇧", "risk_mult": 1.0, "is_silver_bullet": False},
            "news_blocked": False,
            "news_title": "",
            "macro": {"bias": "BULLISH", "prediction": "Trend is BULLISH"},
            "support": 2600.0,
            "resistance": 2750.0,
            "asset_config": dl.ASSETS["XAU/USD"],
        }

        signal = signal_engine.generate_mentor_signal(snapshot)
        # Signal can be None (no trade is valid) or a dict
        if signal is not None:
            self.assertIn("signal", signal)
            self.assertIn(signal["signal"], ["LONG", "SHORT"])
            self.assertIn("sl_price", signal)
            self.assertIn("tp_price", signal)
            self.assertIn("entry_price", signal)
            self.assertIn("confidence", signal)
            self.assertGreater(signal["confidence"], 0)
            self.assertGreater(signal["sl_distance"], 0)

    def test_no_trade_on_news_block(self):
        """Signal should be None when news is blocked."""
        snapshot = {
            "pair": "XAU/USD",
            "candles_5m": self._make_candles(100, trend="up"),
            "candles_15m": self._make_candles(60, trend="up"),
            "candles_1h": self._make_candles(50, trend="up"),
            "current_price": 2700.0,
            "session": {"name": "LONDON", "label": "London", "risk_mult": 1.0},
            "news_blocked": True,
            "news_title": "NFP",
            "macro": {"bias": "BULLISH"},
            "support": 2600.0,
            "resistance": 2750.0,
            "asset_config": dl.ASSETS["XAU/USD"],
        }

        signal = signal_engine.generate_mentor_signal(snapshot)
        self.assertIsNone(signal)

    def test_no_trade_on_missing_data(self):
        """Signal should be None when candle data is missing."""
        snapshot = {
            "pair": "XAU/USD",
            "candles_5m": None,
            "candles_15m": None,
            "candles_1h": None,
            "current_price": None,
            "session": None,
            "news_blocked": False,
            "macro": {},
            "asset_config": dl.ASSETS["XAU/USD"],
        }

        signal = signal_engine.generate_mentor_signal(snapshot)
        self.assertIsNone(signal)


class TestSafetyLayer(unittest.TestCase):
    """Test safety validation."""

    def test_banned_phrases_detected(self):
        """Banned phrases should be caught."""
        is_clean, violations = safety.check_banned_phrases(
            "This is a guaranteed profit signal!"
        )
        self.assertFalse(is_clean)
        self.assertIn("guaranteed profit", violations)

    def test_clean_text_passes(self):
        """Clean text should pass validation."""
        is_clean, violations = safety.check_banned_phrases(
            "This is a high-confidence signal based on multiple confluences."
        )
        self.assertTrue(is_clean)
        self.assertEqual(len(violations), 0)

    def test_missing_stoploss_rejected(self):
        """Signal without SL should be rejected."""
        signal = {
            "signal": "LONG",
            "entry_price": 2700,
            "sl_price": None,
            "sl_distance": None,
        }
        is_valid, error = safety.validate_signal_has_stoploss(signal)
        self.assertFalse(is_valid)
        self.assertIn("missing stop-loss", error.lower())

    def test_invalid_sl_direction_rejected(self):
        """LONG signal with SL above entry should be rejected."""
        signal = {
            "signal": "LONG",
            "entry_price": 2700,
            "sl_price": 2710,  # SL above entry for LONG = invalid
            "sl_distance": 10,
        }
        is_valid, error = safety.validate_signal_has_stoploss(signal)
        self.assertFalse(is_valid)

    def test_valid_signal_passes(self):
        """Valid signal should pass SL validation."""
        signal = {
            "signal": "LONG",
            "entry_price": 2700,
            "sl_price": 2690,
            "sl_distance": 10,
        }
        is_valid, error = safety.validate_signal_has_stoploss(signal)
        self.assertTrue(is_valid)

    def test_kill_switch_off_by_default(self):
        """Kill switch should be OFF by default."""
        # Save and restore env
        old = os.environ.get("KILL_SWITCH")
        if "KILL_SWITCH" in os.environ:
            del os.environ["KILL_SWITCH"]

        self.assertFalse(safety.is_kill_switch_active())

        if old is not None:
            os.environ["KILL_SWITCH"] = old

    def test_kill_switch_on(self):
        """Kill switch should activate when env var is set."""
        old = os.environ.get("KILL_SWITCH")
        os.environ["KILL_SWITCH"] = "1"

        self.assertTrue(safety.is_kill_switch_active())
        msg = safety.kill_switch_message()
        self.assertIn("Kill Switch", msg)

        if old is not None:
            os.environ["KILL_SWITCH"] = old
        else:
            del os.environ["KILL_SWITCH"]

    def test_no_signal_passes_validation(self):
        """None signal (no trade) should pass validation."""
        is_valid, error = safety.validate_signal_has_stoploss(None)
        self.assertTrue(is_valid)

    def test_full_pipeline_blocks_kill_switch(self):
        """Full pipeline should return kill switch message when active."""
        old = os.environ.get("KILL_SWITCH")
        os.environ["KILL_SWITCH"] = "1"

        msg, allowed, reason = safety.validate_and_sanitize(None, "test", "english")
        self.assertFalse(allowed)
        self.assertEqual(reason, "KILL_SWITCH")

        if old is not None:
            os.environ["KILL_SWITCH"] = old
        else:
            del os.environ["KILL_SWITCH"]


class TestMentorFormatting(unittest.TestCase):
    """Test mentor explanation layer."""

    def test_no_trade_message(self):
        """No-trade message should contain key elements."""
        msg = mentor.format_mentor_signal(None, "hinglish")
        self.assertIn("NO TRADE", msg)
        self.assertIn("AI-Generated", msg)

    def test_signal_message_has_6_parts(self):
        """Signal message should contain all 6 parts."""
        signal = {
            "pair": "XAU/USD",
            "signal": "LONG",
            "confidence": 75,
            "reasons": ["📈 Test reason 1", "📊 Test reason 2"],
            "entry_price": 2700.00,
            "sl_price": 2690.00,
            "tp_price": 2725.00,
            "sl_distance": 10.00,
            "tp_distance": 25.00,
            "lots": 0.05,
            "actual_risk": 5.00,
            "rr_ratio": 2.5,
            "trend_1h": "BULLISH",
            "tf_bias": "BULLISH",
            "bos_type": "BOS",
            "choch": False,
            "adx": 28,
            "atr": 3.5,
            "rsi": 55,
            "ema8": 2698,
            "ema21": 2695,
            "ema50": 2690,
            "ema_aligned": True,
            "vwap": 2697,
            "vwap_bias": "BULLISH",
            "fvg": "None",
            "pattern": "None",
            "supports": [2680, 2670],
            "resistances": [2720, 2740],
            "session": {"label": "London Kill Zone 🇬🇧"},
            "macro": {"prediction": "Trend is BULLISH"},
        }

        msg = mentor.format_mentor_signal(signal, "hinglish", beginner_mode=True)

        # Part 1: Setup
        self.assertIn("MENTOR SIGNAL", msg)
        # Part 2: Why
        self.assertIn("WHY THIS TRADE", msg)
        # Part 3: Risk
        self.assertIn("Entry:", msg)
        self.assertIn("Stop Loss:", msg)
        self.assertIn("Take Profit:", msg)
        # Part 4: Levels
        self.assertIn("KEY LEVELS", msg)
        # Part 5: Lesson (may say "Seekh" in Hinglish or "Lesson" in English)
        self.assertTrue("Lesson" in msg or "Seekh" in msg)
        # Part 6: Disclosure
        self.assertIn("AI-Generated", msg)

    def test_loss_coaching_message(self):
        """Loss coaching should generate appropriate message."""
        msg = mentor.format_loss_coaching(3, -15.0, "hinglish")
        self.assertIn("RUK JAO", msg)

    def test_daily_note(self):
        """Daily mentor note should generate non-empty message."""
        msg = mentor.format_daily_mentor_note("english")
        self.assertGreater(len(msg), 50)
        self.assertIn("AI-Generated", msg)


class TestPaperTrading(unittest.TestCase):
    """Test paper trading engine."""

    def test_initial_balance(self):
        """Initial balance should be $500."""
        self.assertEqual(paper_trading.INITIAL_CAPITAL, 500)

    def test_daily_stats_empty(self):
        """Daily stats should work even with no trades."""
        stats = paper_trading.get_daily_stats()
        self.assertIn("total", stats)
        self.assertIn("pnl", stats)


class TestTelegramBot(unittest.TestCase):
    """Test Telegram command handling."""

    def test_start_command(self):
        """/start should return welcome message."""
        response = telegram_bot.handle_command("/start")
        self.assertIn("Welcome", response)

    def test_ask_command(self):
        """/ask should return educational response."""
        response = telegram_bot.handle_command("/ask", "what is SL")
        self.assertIn("Stop Loss", response)

    def test_ask_unknown(self):
        """/ask with unknown question should return help."""
        response = telegram_bot.handle_command("/ask", "what is xyz123")
        self.assertIn("Try karo", response)

    def test_beginner_toggle(self):
        """/beginner should toggle beginner mode."""
        before = telegram_bot.is_beginner_mode()
        telegram_bot.handle_command("/beginner")
        after = telegram_bot.is_beginner_mode()
        self.assertNotEqual(before, after)
        # Reset
        telegram_bot.handle_command("/beginner")

    def test_language_toggle(self):
        """/language should switch language."""
        before = telegram_bot.get_language()
        telegram_bot.handle_command("/language")
        after = telegram_bot.get_language()
        self.assertNotEqual(before, after)
        # Reset
        telegram_bot.handle_command("/language")


if __name__ == "__main__":
    unittest.main(verbosity=2)
