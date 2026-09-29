"""
engine/mentor.py — Mentor Persona Explanation Layer

Generates educational, teaching-style explanations for every signal.

Features:
  - 6-part teaching structure (Setup → Why → Risk → Levels → Lesson → Disclosure)
  - 20-25 year veteran trader "mentor" voice
  - AI disclosure on every message
  - Hinglish/English support
  - Beginner Mode (extra simplification)
  - Loss coaching and daily mentor notes
  - Trade review summaries
"""

import random
from datetime import datetime
import pytz

IST = pytz.timezone('Asia/Kolkata')


# ============================================
# AI DISCLOSURE — Mandatory on EVERY message
# ============================================
AI_DISCLAIMER = (
    "\n\n⚠️ <i>AI-Generated Analysis — Not Financial Advice.\n"
    "This signal is produced by an AI system, not a human advisor.\n"
    "Always do your own research (DYOR). Past performance ≠ future results.\n"
    "Trading involves substantial risk of loss. Only risk what you can afford to lose.</i>"
)

AI_DISCLAIMER_HINDI = (
    "\n\n⚠️ <i>AI-Generated Analysis — Financial Advice Nahi Hai.\n"
    "Ye signal ek AI system ne generate kiya hai, koi human advisor nahi.\n"
    "Hamesha apna research karo (DYOR). Past performance ≠ future results.\n"
    "Trading mein loss ka substantial risk hota hai. Sirf utna risk karo jitna afford kar sako.</i>"
)


# ============================================
# MENTOR VOICE TEMPLATES
# ============================================
MENTOR_INTROS = [
    "Dekho beta, 20+ saal ka experience bol raha hai —",
    "Listen carefully, this is what decades of market experience tell me —",
    "Ek baat yaad rakhna — market kabhi easy nahi hota, but today I see —",
    "As a veteran trader, here's what the charts are telling us —",
    "Main tujhe wahi bataunga jo market mujhe dikha raha hai —",
]

MENTOR_LESSON_POOL = [
    "📚 <b>Today's Lesson:</b> Risk management is NOT optional — it's the foundation of every profitable career.",
    "📚 <b>Aaj Ki Seekh:</b> Stop-loss lagana weakness nahi hai — ye discipline hai jo winners ko losers se alag karta hai.",
    "📚 <b>Today's Lesson:</b> Never move your stop-loss further away. If the trade goes against you, it means your analysis was wrong — accept it.",
    "📚 <b>Aaj Ki Seekh:</b> Jab market confusing lage — DO NOTHING. Sideline rehna bhi ek position hai.",
    "📚 <b>Today's Lesson:</b> A 60% win rate with 1:2.5 RR will make you profitable. You don't need to win every trade.",
    "📚 <b>Aaj Ki Seekh:</b> Har trade ke pehle apne se pucho — 'Kya main ye trade bina FOMO ke le raha hoon?'",
    "📚 <b>Today's Lesson:</b> The market doesn't owe you anything. Protect your capital first, profits will follow.",
    "📚 <b>Aaj Ki Seekh:</b> Consecutive losses ke baad rest lo. Revenge trading sabse bada account killer hai.",
    "📚 <b>Aaj Ki Seekh (USD/INR):</b> USD/INR ek managed-float pair hai. RBI volatility ko smooth karne ke liye intervene karta hai, isliye breakouts jaldi fade ho sakte hain. SL discipline zaruri hai!",
    "📚 <b>Today's Lesson (USD/INR):</b> India imports ~85% of its crude oil. When Crude Oil prices rise, India's import bill increases, putting upward pressure on USD/INR.",
    "📚 <b>Aaj Ki Seekh (USD/INR):</b> DXY (US Dollar Index) aur FII flows USD/INR ke major drivers hain. FII equity selloff se USD/INR me buying pressure aata hai.",
    "📚 <b>Today's Lesson (EUR/INR):</b> EUR/INR is slightly less liquid than USD/INR on NSE. Always factor in wider spreads and use a buffer for stop-losses.",
    "📚 <b>Aaj Ki Seekh (EUR/INR):</b> ECB (European Central Bank) rate decisions aur EUR/USD trend EUR/INR ko directly impact karte hain.",
    "📚 <b>Today's Lesson (Spot vs Futures):</b> Levels are based on spot data feeds, while trading occurs on NSE futures. Futures may trade at a small premium/discount to spot — trade only via SEBI-registered brokers on NSE/BSE!",
]

PAIR_LESSONS = {
    "USD/INR": [
        "📚 <b>Mentor Lesson (USD/INR):</b> USD/INR is a managed-float pair. RBI frequently smooths sharp moves, so breakouts can fade quickly. Maintain strict Stop Loss discipline!",
        "📚 <b>Mentor Lesson (USD/INR):</b> India imports ~85% of its crude oil. Spikes in crude oil increase India's import bill, adding upward pressure on USD/INR.",
        "📚 <b>Mentor Lesson (USD/INR):</b> Keep an eye on DXY (Dollar Index) and FII equity flows — FII selling in Indian equities typically drives USD/INR higher.",
    ],
    "EUR/INR": [
        "📚 <b>Mentor Lesson (EUR/INR):</b> EUR/INR is less liquid than USD/INR on NSE. Always account for wider spreads and use wider SL buffers.",
        "📚 <b>Mentor Lesson (EUR/INR):</b> ECB monetary policy decisions and Eurozone CPI heavily drive EUR/INR momentum alongside global EUR/USD trends.",
    ],
}


# ============================================
# 6-PART TEACHING STRUCTURE
# ============================================
def format_mentor_signal(signal, language="hinglish", beginner_mode=False):
    """
    Format a signal into the 6-part mentor teaching structure.
    """
    if signal is None or signal.get("signal") == "NO_TRADE":
        return _format_no_trade(language, signal)

    pair = signal.get("pair", "XAU/USD")
    direction = "🟢 LONG (BUY)" if signal["signal"] == "LONG" else "🔴 SHORT (SELL)"
    emoji = "📈" if signal["signal"] == "LONG" else "📉"

    intro = random.choice(MENTOR_INTROS)
    now_ist = datetime.now(IST).strftime('%d %b %Y %H:%M IST')

    import data_layer as dl
    asset_cfg = dl.ASSETS.get(pair, {})
    contract_info = asset_cfg.get("active_futures_contract", "Spot / Futures")
    disclaimer_note = asset_cfg.get("disclaimer", "")

    lot_mode = signal.get("lot_mode", "paper_fractional")
    risk_pct = signal.get("risk_pct", 1.0)
    risk_inr = signal.get("actual_risk_inr", 0.0)
    risk_usd = signal.get("actual_risk_usd", 0.0)
    lots_val = signal.get("lots", 0.01)

    if lot_mode == "exchange":
        lots_line = f"📦 <b>Lots:</b> {int(lots_val)} | <b>Risk:</b> ₹{risk_inr:,.2f} ({risk_pct}%)"
        mode_header = "🏛 <b>REAL EXCHANGE MODE (NSE)</b>\n"
    else:
        lots_line = f"📦 <b>Lots:</b> {lots_val:.2f} (paper) | <b>Risk:</b> ${risk_usd:,.2f} ({risk_pct}%)"
        mode_header = "🧪 <b>PAPER / SIMULATION</b>\n"

    # ─── PART 1: SETUP ───
    session_label = signal.get("session", {}).get("label", "Market Hours")
    macro_pred = signal.get("macro", {}).get("prediction", "N/A")

    setup = f"""{mode_header}🎯 <b>{pair} MENTOR SIGNAL</b> {emoji}
━━━━━━━━━━━━━━━━━━━━
💬 <i>{intro}</i>

📊 <b>Direction:</b> {direction}
📜 <b>Contract:</b> {contract_info}
🕐 <b>Session:</b> {session_label}
🔮 <b>Macro View:</b> {macro_pred}"""

    # ─── PART 2: WHY (Confluences) ───
    reasons_text = "\n".join([f"  {r}" for r in signal["reasons"]])

    why_section = f"""
━━━━━━━━━━━━━━━━━━━━
📋 <b>WHY THIS TRADE ({len(signal['reasons'])} confluences):</b>
{reasons_text}"""

    if beginner_mode:
        why_section += _beginner_explain(signal)

    # ─── PART 3: RISK ───
    prec = asset_cfg.get("price_decimals", 2)
    margin_note = signal.get("margin_note", "Broker se margin requirement confirm karein")

    risk_section = f"""
━━━━━━━━━━━━━━━━━━━━
💰 <b>Entry:</b> {signal['entry_price']:.{prec}f}
🛑 <b>Stop Loss:</b> {signal['sl_price']:.{prec}f} ({signal['sl_distance']:.{prec}f} away)
🎯 <b>Take Profit:</b> {signal['tp_price']:.{prec}f} ({signal['tp_distance']:.{prec}f} away)
{lots_line}
⚖️ <b>R:R:</b> 1:{signal['rr_ratio']}
📌 <i>{margin_note}</i>"""

    if disclaimer_note:
        risk_section += f"\n📌 <i>{disclaimer_note}</i>"

    # ─── PART 4: LEVELS ───
    levels = ""
    if signal.get("ema8"):
        levels += f"\n📉 <b>EMA:</b> 8={signal['ema8']:.2f} | 21={signal['ema21']:.2f} | 50={signal['ema50']:.2f}"
        if signal.get("ema_aligned"):
            levels += " ✅ ALIGNED"
    if signal.get("vwap"):
        levels += f"\n📊 <b>VWAP:</b> {signal['vwap']:.2f} ({signal['vwap_bias']})"
    if signal.get("supports"):
        s_levels = ", ".join([f"{s:.2f}" for s in signal["supports"][-3:]])
        levels += f"\n🟢 <b>Supports:</b> {s_levels}"
    if signal.get("resistances"):
        r_levels = ", ".join([f"{r:.2f}" for r in signal["resistances"][-3:]])
        levels += f"\n🔴 <b>Resistances:</b> {r_levels}"

    levels_section = f"""
━━━━━━━━━━━━━━━━━━━━
📊 <b>KEY LEVELS:</b>{levels}
📈 <b>1H:</b> {signal.get('trend_1h', 'N/A')} | <b>15M:</b> {signal.get('tf_bias', 'N/A')} {signal.get('bos_type', '') or ''}{' +CHoCH🔄' if signal.get('choch') else ''}
📶 <b>ADX:</b> {signal.get('adx', 0)} | <b>ATR:</b> {signal.get('atr', 0)} | <b>RSI:</b> {signal.get('rsi', 50)}"""

    # ─── PART 5: LESSON ───
    lesson = random.choice(MENTOR_LESSON_POOL)
    lesson_section = f"\n━━━━━━━━━━━━━━━━━━━━\n{lesson}"

    # ─── PART 6: DISCLOSURE ───
    disclaimer = AI_DISCLAIMER_HINDI if language == "hinglish" else AI_DISCLAIMER

    # ─── TIMESTAMP ───
    footer = f"\n━━━━━━━━━━━━━━━━━━━━\n🕐 {now_ist}"

    return setup + why_section + risk_section + levels_section + lesson_section + footer + disclaimer


def _format_no_trade(language="hinglish", signal=None):
    """When the engine says 'no trade' — that's valid and we explain why."""
    intro = random.choice(MENTOR_INTROS)
    now_ist = datetime.now(IST).strftime('%d %b %Y %H:%M IST')

    if signal and signal.get("reason_code") == "ZERO_LOTS":
        min_cap = signal.get("min_capital_needed", 0.0)
        sym = signal.get("currency_symbol", "₹")
        margin_note = signal.get("margin_note", "Broker se margin requirement confirm karein")
        risk_pct = signal.get("risk_pct", 1.0)

        if language == "hinglish":
            msg = f"""🔍 <b>MARKET SCAN COMPLETE — NO TRADE</b>

💬 <i>Capital kam hai is setup ke liye, skip kar rahe hain.</i>

🚫 <b>Sabak:</b> Risk management ke mutabiq exchange mode me 1 whole lot le lene ke liye aapka capital kam hai.
💰 <b>Minimum Capital Needed for 1 Lot:</b> {sym}{min_cap:,.2f} (at {risk_pct}% risk)
📌 <i>{margin_note}</i>

Patient raho. Capital protect karna pehli priority hai!

🕐 {now_ist}"""
        else:
            msg = f"""🔍 <b>MARKET SCAN COMPLETE — NO TRADE</b>

💬 <i>Capital is too low for this setup, skipping.</i>

🚫 <b>Lesson:</b> Your capital is insufficient to trade 1 whole lot safely in exchange mode.
💰 <b>Minimum Capital Required for 1 Lot:</b> {sym}{min_cap:,.2f} (at {risk_pct}% risk)
📌 <i>{margin_note}</i>

Be patient. Protecting your capital is priority #1!

🕐 {now_ist}"""
        return msg + (AI_DISCLAIMER_HINDI if language == "hinglish" else AI_DISCLAIMER)

    if language == "hinglish":
        msg = f"""🔍 <b>MARKET SCAN COMPLETE — NO TRADE</b>

💬 <i>{intro}</i>

🚫 <b>Aaj ka sabak:</b> Har candle pe trade lena zaruri nahi hai.
Jab confluence nahi milta, toh sideline rehna bhi ek strong move hai.

Patient raho. Quality signals ke liye wait karo.
Market hamesha rahega — tumhara capital protect karna pehli priority hai.

🕐 {now_ist}"""
    else:
        msg = f"""🔍 <b>MARKET SCAN COMPLETE — NO TRADE</b>

💬 <i>{intro}</i>

🚫 <b>Today's lesson:</b> You don't have to trade every candle.
When confluences aren't there, staying on the sideline IS a strong move.

Be patient. Wait for quality setups.
The market will always be here — protecting your capital is priority #1.

🕐 {now_ist}"""

    return msg + (AI_DISCLAIMER_HINDI if language == "hinglish" else AI_DISCLAIMER)


def _beginner_explain(signal):
    """Extra beginner-friendly explanation of what each confluence means."""
    explanations = []

    if signal.get("bos_type") == "BOS":
        explanations.append(
            "\n  💡 <i>BOS = Break of Structure — price broke a key level, confirming the trend direction.</i>"
        )
    if signal.get("choch"):
        explanations.append(
            "\n  💡 <i>CHoCH = Change of Character — the trend just reversed! This is a strong early signal.</i>"
        )
    if signal.get("in_order_block"):
        explanations.append(
            "\n  💡 <i>Order Block = A zone where big institutions placed orders before. Price often reacts here.</i>"
        )
    if signal.get("fvg") and signal["fvg"] != "None":
        explanations.append(
            "\n  💡 <i>FVG = Fair Value Gap — an imbalance in price that the market often fills. Think of it as 'unfinished business'.</i>"
        )
    if signal.get("ema_aligned"):
        explanations.append(
            "\n  💡 <i>EMA Aligned = The 8, 21 and 50 EMAs are stacked in order — a textbook trending market.</i>"
        )

    if explanations:
        return "\n\n🎓 <b>BEGINNER NOTES:</b>" + "".join(explanations)
    return ""


# ============================================
# LOSS COACHING
# ============================================
def format_loss_coaching(consecutive_losses, daily_pnl, language="hinglish"):
    """Generate coaching message after losses."""
    if language == "hinglish":
        if consecutive_losses >= 3:
            msg = f"""🛑 <b>MENTOR SAYS: RUK JAO!</b>

Beta, {consecutive_losses} consecutive losses ho chuke hain.
Daily P&L: ${daily_pnl:+.2f}

❌ Aur trade MAT karo aaj.
✅ Break lo. Walk karo. Screen se door jao.
✅ Kal naye dimag se aana.

Ye weakness nahi hai — ye DISCIPLINE hai.
Best traders jaante hain kab rukna hai."""
        else:
            msg = f"""⚠️ <b>MENTOR NOTE: Loss Hua — Koi Baat Nahi</b>

Loss trading ka hissa hai.
Daily P&L: ${daily_pnl:+.2f}

✅ SL hit hua matlab system kaam kar raha hai.
✅ Apna risk management follow karte raho.
❌ Revenge trading se DOOR raho."""
    else:
        if consecutive_losses >= 3:
            msg = f"""🛑 <b>MENTOR SAYS: STOP TRADING!</b>

You've had {consecutive_losses} consecutive losses.
Daily P&L: ${daily_pnl:+.2f}

❌ Do NOT take any more trades today.
✅ Take a break. Walk. Step away from the screen.
✅ Come back tomorrow with a fresh mind.

This isn't weakness — this is DISCIPLINE.
The best traders know when to stop."""
        else:
            msg = f"""⚠️ <b>MENTOR NOTE: Loss is Part of Trading</b>

Losses are a natural part of trading.
Daily P&L: ${daily_pnl:+.2f}

✅ SL hit means your system is working.
✅ Keep following your risk management.
❌ Stay AWAY from revenge trading."""

    return msg + (AI_DISCLAIMER_HINDI if language == "hinglish" else AI_DISCLAIMER)


# ============================================
# DAILY MENTOR NOTE
# ============================================
def format_daily_mentor_note(language="hinglish"):
    """Generate a motivational/educational daily note."""
    notes_hinglish = [
        "🌅 <b>Good Morning, Trader!</b>\n\nAaj ka mantra: 'Plan the trade, trade the plan.'\n\nMarket mein entry se pehle — SL, TP, aur risk sab decide kar lo.\nFOMO se door raho. Quality signals ka wait karo.\n\nAaj ka din profitable ho ya na ho — disciplined zaroor rehna. 💪",
        "🌅 <b>Subah Ka Mentor Note</b>\n\nYaad rakhna: Trading marathon hai, sprint nahi.\n\n1 din mein ameer hone ki koshish mat karo.\nConsistency > Big Wins.\n\nApna capital protect karo, profits khud aayenge. 🎯",
        "🌅 <b>Aaj Ka Game Plan</b>\n\nKill Zones mein trade karo (London/NY).\nMinimum 3 confluences ke bina entry mat lo.\nSL hamesha lagao — no exceptions.\n\nBest trader woh nahi jo sabse zyada trade kare,\nbest trader woh hai jo sabse zyada disciplined ho. 🏆",
    ]

    notes_english = [
        "🌅 <b>Good Morning, Trader!</b>\n\nToday's mantra: 'Plan the trade, trade the plan.'\n\nBefore entering the market — decide your SL, TP, and risk.\nStay away from FOMO. Wait for quality signals.\n\nWhether today is profitable or not — stay disciplined. 💪",
        "🌅 <b>Morning Mentor Note</b>\n\nRemember: Trading is a marathon, not a sprint.\n\nDon't try to get rich in one day.\nConsistency > Big Wins.\n\nProtect your capital, profits will follow. 🎯",
        "🌅 <b>Today's Game Plan</b>\n\nTrade during Kill Zones (London/NY).\nDon't enter without minimum 3 confluences.\nAlways place SL — no exceptions.\n\nThe best trader isn't the one who trades the most,\nit's the one who is the most disciplined. 🏆",
    ]

    pool = notes_hinglish if language == "hinglish" else notes_english
    note = random.choice(pool)
    return note + (AI_DISCLAIMER_HINDI if language == "hinglish" else AI_DISCLAIMER)


# ============================================
# TRADE REVIEW
# ============================================
def format_trade_review(stats, language="hinglish"):
    """Format end-of-day trade review."""
    now_ist = datetime.now(IST).strftime('%d %b %Y')
    pnl_emoji = "💰" if stats.get("pnl", 0) >= 0 else "💸"

    msg = f"""📊 <b>DAILY TRADE REVIEW — {now_ist}</b>
━━━━━━━━━━━━━━━━━━━━

📈 <b>Today's Results:</b>
  Total Trades: {stats.get('total', 0)}
  ✅ Wins: {stats.get('wins', 0)}
  ❌ Losses: {stats.get('losses', 0)}
  📊 Win Rate: {stats.get('win_rate', 0):.1f}%
  {pnl_emoji} P&L: ${stats.get('pnl', 0):+.2f}
━━━━━━━━━━━━━━━━━━━━"""

    if language == "hinglish":
        if stats.get("win_rate", 0) >= 60:
            msg += "\n\n💬 <i>Accha kaam! But overconfident mat ho. Kal phir se zero se shuru.</i>"
        elif stats.get("total", 0) == 0:
            msg += "\n\n💬 <i>Aaj koi trade nahi hua. Koi baat nahi — no trade is better than a bad trade.</i>"
        else:
            msg += "\n\n💬 <i>Kuch trades nahi chale — ye normal hai. Review karo, seekho, aur aage badho.</i>"
    else:
        if stats.get("win_rate", 0) >= 60:
            msg += "\n\n💬 <i>Good work! But don't get overconfident. Tomorrow we start from zero again.</i>"
        elif stats.get("total", 0) == 0:
            msg += "\n\n💬 <i>No trades today. That's okay — no trade is better than a bad trade.</i>"
        else:
            msg += "\n\n💬 <i>Some trades didn't work — that's normal. Review, learn, and move forward.</i>"

    return msg + (AI_DISCLAIMER_HINDI if language == "hinglish" else AI_DISCLAIMER)
