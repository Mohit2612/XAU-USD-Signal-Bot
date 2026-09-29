"""
engine/templates.py — Telegram Message Templates & Lesson Curriculum

Houses all message templates (Trade Signal, No-Trade, Trade Closed, Discipline Note)
and lesson curriculum pools.
"""

TRADE_SIGNAL_TEMPLATE_HINGLISH = (
    "📊 {pair} | {direction_emoji}\n"
    "Entry: {entry}\n"
    "Stop Loss: {stop_loss}\n"
    "Target: {target}\n"
    "Lots: {lots} ({level_label}) | RR {rr_str} | Risk {risk_pct}%\n"
    "\n"
    "🎓 Mentor:\n"
    "Kyun: {why}\n"
    "Dhyan: {caution}\n"
    "Sabak: {lesson}\n"
    "\n"
    "⚠️ Educational only, not advice. SEBI-registered broker se hi trade karein."
)

TRADE_SIGNAL_TEMPLATE_ENGLISH = (
    "📊 {pair} | {direction_emoji}\n"
    "Entry: {entry}\n"
    "Stop Loss: {stop_loss}\n"
    "Target: {target}\n"
    "Lots: {lots} ({level_label}) | RR {rr_str} | Risk {risk_pct}%\n"
    "\n"
    "🎓 Mentor:\n"
    "Why: {why}\n"
    "Caution: {caution}\n"
    "Lesson: {lesson}\n"
    "\n"
    "⚠️ Educational only, not advice. Trade only via SEBI-registered brokers."
)

TRADE_SIGNAL_SHORT_TEMPLATE = (
    "📊 {pair} | {direction_emoji}\n"
    "Entry: {entry}\n"
    "Stop Loss: {stop_loss}\n"
    "Target: {target}\n"
    "Lots: {lots} ({level_label}) | RR {rr_str} | Risk {risk_pct}%\n"
    "\n"
    "⚠️ Educational only, not advice. SEBI-registered broker se hi trade karein."
)

NO_TRADE_TEMPLATE_HINGLISH = (
    "🎓 Mentor: {reason_short}. Wait karna bhi ek trade hai.\n"
    "Sabak: {lesson}\n"
    "\n"
    "⚠️ Educational only, not advice."
)

NO_TRADE_TEMPLATE_ENGLISH = (
    "🎓 Mentor: {reason_short}. Waiting is also a valid trade.\n"
    "Lesson: {lesson}\n"
    "\n"
    "⚠️ Educational only, not advice."
)

TRADE_CLOSED_TEMPLATE_HINGLISH = (
    "📊 {pair} closed: {outcome_status}\n"
    "Result: {pnl_str} (paper)\n"
    "Sabak: {lesson}\n"
    "\n"
    "⚠️ Educational only, not advice."
)

TRADE_CLOSED_TEMPLATE_ENGLISH = (
    "📊 {pair} closed: {outcome_status}\n"
    "Result: {pnl_str} (paper)\n"
    "Lesson: {lesson}\n"
    "\n"
    "⚠️ Educational only, not advice."
)

DISCIPLINE_NOTE_TEMPLATE_HINGLISH = (
    "🎓 Mentor: {consecutive_losses} losses ho gaye. Aaj aur signals band.\n"
    "Journal dekho, kal fresh start karo.\n"
    "\n"
    "⚠️ Educational only, not advice."
)

DISCIPLINE_NOTE_TEMPLATE_ENGLISH = (
    "🎓 Mentor: {consecutive_losses} losses hit. Signal generation locked for today.\n"
    "Review your journal and start fresh tomorrow.\n"
    "\n"
    "⚠️ Educational only, not advice."
)

LESSON_CURRICULUM_HINGLISH = [
    "Stop-loss lagana weakness nahi, discipline hai.",
    "FOMO me entry lene se humesha capital loss hota hai.",
    "Risk management bina strategy zero hoti hai.",
    "NSE currency futures me leverage ko respect karo.",
    "RBI intervention zone me breakouts fast fade ho sakte hain.",
    "Crude oil moves directly affect USD/INR volatility.",
    "Win rate se zyaada R:R ratio matter karta hai.",
    "Revenge trading se door rahna hi trader ki jeet hai.",
]

LESSON_CURRICULUM_ENGLISH = [
    "Placing a Stop Loss is discipline, not weakness.",
    "Entering due to FOMO always destroys capital.",
    "Strategy without risk management equals zero.",
    "Always respect leverage in currency derivatives.",
    "RBI interventions cause fast breakouts to fade.",
    "Crude oil price spikes directly impact USD/INR.",
    "Risk:Reward ratio matters more than win rate.",
    "Avoiding revenge trading is the mark of a pro.",
]
