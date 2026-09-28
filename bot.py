"""
bot.py — Main entry point for the Mentor Persona Signal Bot.

Wires together:
  - data_layer: market data fetching (unchanged APIs)
  - engine/signal_engine: new multi-strategy confluence engine
  - engine/mentor: explanation layer (6-part teaching structure)
  - engine/safety: validation, banned phrases, kill switch, India Mode
  - engine/paper_trading: virtual money tracking
  - engine/telegram_bot: command handling & delivery
"""

import os
import sys
import time
import traceback
from datetime import datetime, date
import pytz

# Fix Windows console encoding for emojis
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

import data_layer as dl
from engine import signal_engine, mentor, safety, paper_trading, telegram_bot

IST = pytz.timezone('Asia/Kolkata')


def main():
    """Main bot loop."""
    # ── CONFIG CHECK ──
    if not dl.validate_config():
        return

    # ── LOAD STATE ──
    paper_trading.load_journal()

    # ── BUILD ENABLED ASSETS ──
    enabled_assets = [sym for sym, cfg in dl.ASSETS.items() if cfg.get("enabled", True)]

    print("🚀 Mentor Persona Signal Bot v4.0 Starting...")
    print(f"Enabled assets: {', '.join(enabled_assets)}")
    print(f"Language: {telegram_bot.get_language()}")
    print(f"Beginner Mode: {telegram_bot.is_beginner_mode()}")

    # ── START TELEGRAM POLLING ──
    telegram_bot.start_polling_thread()

    # ── SEND STARTUP MESSAGE ──
    lang = telegram_bot.get_language()
    assets_text = "\n".join([f"  • {dl.ASSETS[sym]['label']}" for sym in enabled_assets])
    startup_msg = (
        f"🚀 <b>MENTOR SIGNAL BOT v4.0 LIVE</b>\n\n"
        f"🧪 PAPER TRADING MODE\n\n"
        f"<b>📊 Active Assets:</b>\n{assets_text}\n\n"
        f"<b>🧠 Mentor Engine:</b>\n"
        f"  • Multi-Strategy Confluence\n"
        f"  • AI + 20yr Veteran Trader Voice\n"
        f"  • Mandatory SL on every signal\n"
        f"  • News/Macro filtering\n"
        f"  • Safety validation layer\n\n"
        f"<b>📱 Commands:</b>\n"
        f"  /ask [question] — Learn any concept\n"
        f"  /status — Current bot status\n"
        f"  /beginner — Toggle beginner mode\n"
        f"  /language — Switch Hinglish/English\n\n"
        f"💵 Starting Capital: $500\n"
    )
    # Safety check on startup message
    startup_msg, _, _ = safety.validate_and_sanitize(None, startup_msg, lang)
    telegram_bot.send_message(startup_msg)

    # ── SEND DAILY MENTOR NOTE ──
    daily_note = mentor.format_daily_mentor_note(lang)
    daily_note, _, _ = safety.validate_and_sanitize(None, daily_note, lang)
    telegram_bot.send_message(daily_note)

    last_mentor_note_date = date.today()

    # ── MAIN LOOP ──
    while True:
        try:
            now = datetime.now(IST)
            today = date.today()

            # ═══ DAILY RESET ═══
            is_new_day = paper_trading.check_daily_reset()
            if is_new_day:
                print(f"\n📅 New day: {today}")
                telegram_bot.send_message(
                    f"📅 <b>New Day: {today}</b>\n"
                    f"Signals remaining: {paper_trading.MAX_TRADES_PER_DAY}"
                )

                # Daily mentor note (once per day)
                if last_mentor_note_date != today:
                    lang = telegram_bot.get_language()
                    note = mentor.format_daily_mentor_note(lang)
                    note, _, _ = safety.validate_and_sanitize(None, note, lang)
                    telegram_bot.send_message(note)
                    last_mentor_note_date = today

            # ═══ KILL SWITCH CHECK ═══
            if safety.is_kill_switch_active():
                print("🔴 Kill switch active. Scanning only, no signals.")
                msg = safety.kill_switch_message()
                # Don't send every cycle, just once
                time.sleep(300)
                continue

            # ═══ MONITOR ACTIVE TRADES ═══
            pt_state = paper_trading.get_state()
            for symbol in list(pt_state["active_trades"].keys()):
                current_price = dl.get_current_price(symbol)
                if current_price:
                    result = paper_trading.monitor_trade(symbol, current_price)
                    if result:
                        # Trade closed — send notification
                        pnl = result.get("pnl", 0)
                        reason = result.get("reason", "UNKNOWN")
                        pnl_emoji = "💰" if pnl > 0 else "💸"
                        direction = "LONG (BUY)" if result["signal"] == "LONG" else "SHORT (SELL)"

                        close_msg = (
                            f"{'🎯✅' if reason == 'TP_HIT' else '🛑❌' if reason == 'SL_HIT' else '⏰'} "
                            f"<b>TRADE CLOSED — {reason}</b>\n\n"
                            f"📊 <b>{symbol} — {direction}</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n"
                            f"💰 Entry: {result['entry']}\n"
                            f"📍 Exit: {result['exit']}\n"
                            f"{pnl_emoji} <b>P&L: ${pnl:+.2f}</b>\n"
                            f"💵 Balance: ${paper_trading.get_virtual_balance():.2f}\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n"
                            f"⏱ Duration: {result.get('duration', 'N/A')}\n"
                        )

                        lang = telegram_bot.get_language()
                        close_msg, _, _ = safety.validate_and_sanitize(None, close_msg, lang)
                        telegram_bot.send_message(close_msg)

                        # Loss coaching
                        if pnl <= 0:
                            consec = pt_state["consecutive_losses"]
                            daily = pt_state["daily_pnl"]
                            coaching = mentor.format_loss_coaching(consec, daily, lang)
                            coaching, _, _ = safety.validate_and_sanitize(None, coaching, lang)
                            telegram_bot.send_message(coaching)

                        print(f"📊 {symbol} closed: {reason} | P&L: ${pnl:+.2f}")

            # ═══ SESSION INFO ═══
            session = dl.get_session_label()
            pt_state = paper_trading.get_state()
            print(f"\n[{now.strftime('%H:%M')}] {session} | "
                  f"Trades: {pt_state['trades_today']}/{paper_trading.MAX_TRADES_PER_DAY} | "
                  f"Active: {len(pt_state['active_trades'])} | "
                  f"P&L: ${pt_state['daily_pnl']:+.2f}")

            # ═══ SCAN ASSETS ═══
            for symbol in enabled_assets:
                asset_cfg = dl.ASSETS[symbol]
                asset_type = asset_cfg.get("type", "forex")

                # Skip forex/commodity on weekends
                if asset_type in ("forex", "commodity") and now.weekday() >= 5:
                    continue

                # Check if we can trade
                can, reason = paper_trading.can_trade(symbol)
                if not can:
                    continue

                print(f"\n--- Scanning {asset_cfg['label']} ({symbol}) ---")

                # ═══ GET MARKET SNAPSHOT ═══
                snapshot = dl.get_market_snapshot(symbol)

                if not snapshot.get("candles_5m") or not snapshot.get("candles_15m") or not snapshot.get("candles_1h"):
                    print(f"  Fetch failed for {symbol}. Skipping...")
                    continue

                # ═══ GENERATE SIGNAL ═══
                signal = signal_engine.generate_mentor_signal(snapshot)

                if signal:
                    # Check cooldown
                    if not paper_trading.check_cooldown(symbol, signal["signal"]):
                        print(f"  Same direction cooldown for {symbol} — skipping.")
                        continue

                    # ═══ SAFETY VALIDATION ═══
                    sl_valid, sl_error = safety.validate_signal_has_stoploss(signal)
                    if not sl_valid:
                        print(f"  ❌ {sl_error}")
                        continue

                    # ═══ FORMAT WITH MENTOR VOICE ═══
                    lang = telegram_bot.get_language()
                    beginner = telegram_bot.is_beginner_mode()
                    message = mentor.format_mentor_signal(signal, lang, beginner)

                    # ═══ FULL SAFETY PIPELINE ═══
                    final_msg, allowed, block_reason = safety.validate_and_sanitize(
                        signal, message, lang
                    )

                    if not allowed:
                        print(f"  🚫 Signal blocked: {block_reason}")
                        continue

                    # ═══ SEND SIGNAL ═══
                    telegram_bot.send_message(final_msg)

                    # ═══ OPEN PAPER TRADE ═══
                    paper_trading.open_trade(signal)

                    print(f"  ✅ Signal: {signal['signal']} @ {signal['entry_price']} | "
                          f"Conf: {signal['confidence']}% | Risk: ${signal['actual_risk']:.2f}")

                    if pt_state["trades_today"] >= paper_trading.MAX_TRADES_PER_DAY:
                        telegram_bot.send_message(
                            f"🔴 <b>Daily Limit Reached</b>\n"
                            f"{paper_trading.MAX_TRADES_PER_DAY} signals sent. Resuming tomorrow."
                        )
                        break
                else:
                    print(f"  No signal for {symbol}.")

                    # Occasionally send "no trade" message (not every cycle)
                    # Only in kill zones to avoid spam
                    if snapshot.get("session", {}).get("name") not in ("OFF_HOURS", None):
                        pass  # The engine already logs "no signal"

            # ═══ SAVE STATE ═══
            paper_trading.save_state_file()

            # ═══ END-OF-DAY SUMMARY ═══
            if now.hour == 22 and now.minute < 6:
                stats = paper_trading.get_daily_stats()
                if stats["total"] > 0:
                    lang = telegram_bot.get_language()
                    review = mentor.format_trade_review(stats, lang)
                    review, _, _ = safety.validate_and_sanitize(None, review, lang)
                    telegram_bot.send_message(review)

            # ═══ SLEEP ═══
            ts = time.time()
            sleep_time = (300 - (ts % 300)) + 3  # Align to 5-minute intervals
            print(f"\nSleeping {int(sleep_time)}s until next cycle...")
            time.sleep(sleep_time)

        except KeyboardInterrupt:
            # Graceful shutdown
            for symbol in list(paper_trading.get_state()["active_trades"].keys()):
                current_price = dl.get_current_price(symbol)
                if current_price:
                    paper_trading.close_trade(symbol, "BOT_SHUTDOWN", current_price)

            stats = paper_trading.get_daily_stats()
            lang = telegram_bot.get_language()
            review = mentor.format_trade_review(stats, lang)
            review, _, _ = safety.validate_and_sanitize(None, review, lang)
            telegram_bot.send_message(review)
            telegram_bot.send_message("🔴 <b>Bot stopped.</b>")
            break

        except Exception as e:
            print(f"Error: {e}")
            traceback.print_exc()
            time.sleep(120)


if __name__ == "__main__":
    main()
