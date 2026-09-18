<div align="center">

# 🥇 XAU/USD (Gold) Ultimate Signal Bot v2.0

[![Python](https://img.shields.io/badge/Python-3.9+-blue?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Telegram API](https://img.shields.io/badge/Telegram-API-0088CC?style=for-the-badge&logo=telegram&logoColor=white)](https://core.telegram.org/bots)
[![TwelveData](https://img.shields.io/badge/TwelveData-Market_Data-FF4B4B?style=for-the-badge)](https://twelvedata.com/)
[![Railway](https://img.shields.io/badge/Railway-Deploy-0B0D0E?style=for-the-badge&logo=railway&logoColor=white)](https://railway.app/)

*An institutional-grade algorithmic trading bot engineered specifically for Gold (XAU/USD). Combines 2026's most powerful ICT & SMC strategies with automated trade execution, trailing stop-loss, and breakeven management — delivering high-probability setups directly to Telegram.*

</div>

---

## 📑 Table of Contents
- [About the Project](#-about-the-project)
- [Algorithmic Strategy Stack](#-algorithmic-strategy-stack)
- [Key Features](#-key-features)
- [Auto-Trade Engine](#-auto-trade-engine)
- [Requirements & Setup](#-requirements--setup)
- [Environment Variables](#-environment-variables)
- [Deployment (Railway/Heroku)](#-deployment)
- [Disclaimer](#-disclaimer)

---

## 🧠 About the Project

This bot monitors the **XAU/USD (Gold)** forex market autonomously 24/5. It implements the **2026 institutional trading framework** combining ICT (Inner Circle Trader) methodology with Smart Money Concepts (SMC). 

The bot uses a multi-timeframe approach:
- **1-Hour** candles for macro trend bias
- **15-Minute** candles for market structure (BOS/CHoCH)
- **5-Minute** candles for precision entries

It **only trades during Kill Zones** (London & New York sessions) where institutional volume is highest, dramatically reducing false signals and increasing win rate.

---

## ⚙️ Algorithmic Strategy Stack

### 🔥 2026 Strategy Confluence (10 Layers)

| # | Strategy | Points | Description |
|---|---------|--------|-------------|
| 1 | **Kill Zone + Silver Bullet Timing** | 15 | Only trades during London/NY Kill Zones + ICT Silver Bullet windows |
| 2 | **1H + 15M Trend Alignment** | 20 | Multi-timeframe structural agreement (BOS/CHoCH) |
| 3 | **Asian Range Sweep (Judas Swing)** | 15 | Detects Asian session high/low sweeps — the #1 institutional setup |
| 4 | **Order Block Entry** | 12 | Price must be inside institutional order block |
| 5 | **VWAP Alignment** | 10 | Volume-Weighted Average Price confirms fair value direction |
| 6 | **EMA Confluence (8/21/50)** | 8 | Full exponential moving average alignment |
| 7 | **Fair Value Gap (FVG)** | 8 | Institutional imbalance zones |
| 8 | **OTE Fibonacci (62-79%)** | 8 | ICT Optimal Trade Entry zone |
| 9 | **Candle Patterns** | 6 | Engulfing, Morning/Evening Star, Hammer/Shooting Star |
| 10 | **RSI Divergence + Momentum** | 10+ | Momentum confirmation + divergence detection |

**Minimum score of 85/115 required** — only the highest-quality setups pass.

---

## ✨ Key Features

### Signal Quality
- **85+ Confidence Threshold** — extremely strict filtering (only top-tier signals)
- **10-Layer Confluence Scoring** — 10 independent strategies must align
- **Kill Zone Only** — trades only during London/NY institutional hours
- **Asian Range Sweep Detection** — catches the famous "Judas Swing" setup
- **Entry Candle Confirmation** — waits for candle to close in signal direction

### Risk Management
- **1% Risk Per Trade** — ultra-conservative position sizing
- **Dynamic Lot Sizing** — automatically calculated based on SL distance
- **Daily Loss Limit (-3%)** — auto-pause if daily losses exceed limit
- **Consecutive Loss Circuit Breaker** — pauses after 2 consecutive losses
- **Win Rate Auto-Pause** — stops trading if win rate drops below 50%
- **Max 2 Trades/Day** — quality over quantity

### Auto-Trade Engine 🤖
- **Automatic Entry** — executes trade when all conditions align
- **Trailing Stop Loss** — moves SL to breakeven at 50% of TP
- **Profit Lock** — locks 50% profit at 75% of TP
- **Time-Based Exit** — auto-closes trades after 2 hours
- **Reverse Signal Exit** — closes trade if opposite signal appears
- **Graceful Shutdown** — closes active trade on bot shutdown

### Trade Journal & Reporting
- **Full Trade Logging** — every trade recorded with entry, exit, P&L, reasons
- **Daily Summary Report** — Telegram notification with day's results
- **Rolling Performance** — tracks last 50 trades for win rate monitoring
- **Persistent Journal** — saved to JSON file, survives restarts

---

## 🤖 Auto-Trade Engine

The bot runs a complete **trade state machine**:

```
IDLE → SIGNAL (85+) → ENTRY CONFIRMED → AUTO-EXECUTE →
  → MONITORING →
    → SL to Breakeven (at 50% TP) →
    → Profit Lock (at 75% TP) →
    → TP HIT ✅ / SL HIT ❌ / TIME EXIT ⏰ / REVERSE EXIT 🔄
```

### Trailing SL Logic
1. **Entry** → SL placed below Order Block or ATR-based
2. **50% of TP reached** → SL moved to breakeven (entry + $0.50)
3. **75% of TP reached** → SL moved to lock 50% of profit
4. **TP hit** → Trade closed with full profit

---

## 🛠️ Requirements & Setup

### Prerequisites
- Python 3.9+
- A Telegram Bot Token (from [@BotFather](https://t.me/botfather))
- A TwelveData API Key (for real-time XAU/USD data)

### Local Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/YourUsername/XAU-USD-Signal-Bot.git
   cd XAU-USD-Signal-Bot
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure the script:**
   Inside `bot.py`, locate the Configuration block and update your risk settings:
   ```python
   CAPITAL = 200               # Your exact real balance
   RISK_PERCENT = 0.01         # 1% risk per trade (ultra-safe)
   MAX_TRADES_PER_DAY = 2      # Quality over quantity
   MIN_CONFIDENCE = 85         # Strict 85%+ confluence required
   RR_RATIO = 2.5              # Target 1:2.5 Risk:Reward
   PAPER_MODE = True           # Set False ONLY when ready for live execution
   ```

4. **Run the bot:**
   ```bash
   python bot.py
   ```

---

## 🔑 Environment Variables

To keep your credentials secure, do **not** hardcode them. Export these environment variables locally or input them into your hosting provider's dashboard:

| Variable | Description |
|---|---|
| `TELEGRAM_TOKEN` | The HTTP API token from BotFather. |
| `TELEGRAM_CHAT_ID` | Your personal ID or Channel ID where signals will be sent. |
| `TWELVEDATA_API_KEY` | Free API key from TwelveData to pull candlestick data. |

---

## 🚀 Deployment

The project is fully pre-configured for seamless cloud deployment to ensure 24/5 uptime.

### Railway.app (Recommended)
This repository includes a `railway.json` and `Procfile`. 
1. Link your GitHub repository to a new Railway project.
2. Add your Environment Variables in the Railway Dashboard.
3. The bot will deploy and run automatically.

---

## ⚠️ Disclaimer

**Educational Purposes Only.** Trading Gold (XAU/USD) involves significant risk of loss and is not suitable for all investors. The algorithms provided in this repository do not constitute financial advice. Always use `PAPER_MODE` before engaging in live markets. Past performance does not guarantee future results.

---
<div align="center">
  <i>May your Stop Losses be tight and your Take Profits be hit. ⚔️</i>
</div>
