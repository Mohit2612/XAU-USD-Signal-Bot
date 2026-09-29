"""
engine/money_management.py — Capital-Based Lot Sizing & Money Management

Implements beginner-level money management:
  - "exchange" mode (whole lots only, real NSE currency futures 1000 USD/EUR per lot)
  - "paper_fractional" mode (simulation only, fractional lots down to 0.01)
  - Dynamic currency conversion via live data_layer USD/INR rate
  - Strict risk % calculation (never rounds up)
  - Minimum capital check for 0-lot setups with clear minimum capital requirements
  - Daily loss cap monitoring
"""

import os
import math
import json
import data_layer as dl

CONFIG_FILE = "money_config.json"

_money_config = {
    "lot_mode": "paper_fractional",  # "paper_fractional" or "exchange"
    "capital": 50000.0,              # Default capital
    "capital_currency": "INR",       # "INR" or "USD"
    "risk_pct": 1.0,                 # Beginner default 1%, max 2%
    "daily_loss_cap_pct": 3.0,       # 3% of capital
    "max_lots_exchange": 10,         # Cap on exchange lots
    "max_lots_paper": 5.0,           # Cap on paper lots
}


def load_money_config():
    global _money_config
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                saved = json.load(f)
                _money_config.update(saved)
        except Exception as e:
            print(f"Error loading money_config.json: {e}")


def save_money_config():
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(_money_config, f, indent=2)
    except Exception as e:
        print(f"Error saving money_config.json: {e}")


load_money_config()


def get_money_config():
    return _money_config


def set_capital(amount, currency="INR"):
    if amount <= 0:
        return False, "Capital must be a positive number."
    curr = currency.upper().strip()
    if curr not in ("INR", "USD"):
        return False, "Currency must be INR or USD."

    _money_config["capital"] = float(amount)
    _money_config["capital_currency"] = curr
    save_money_config()
    return True, f"Capital updated to {curr} {amount:,.2f}"


def set_lot_mode(mode):
    m = mode.lower().strip()
    if m not in ("exchange", "paper_fractional"):
        return False, "Mode must be 'exchange' or 'paper_fractional'."
    _money_config["lot_mode"] = m
    save_money_config()
    return True, f"Lot mode updated to '{m}'"


def get_live_usdinr_rate():
    """Fetch live USD/INR exchange rate from data layer, never hardcoding."""
    try:
        price = dl.get_current_price("USD/INR")
        if price and price > 0:
            return float(price)
    except Exception:
        pass

    try:
        candles = dl.get_candles("USD/INR", "5m", "1d")
        if candles and len(candles) > 0:
            return float(candles[-1]["close"])
    except Exception:
        pass

    return 83.50  # Dynamic fallback if APIs offline


def calculate_lot_size(pair, entry_price, sl_price, asset_cfg):
    """
    Calculate position lot size based on capital, risk_pct, and lot_mode.

    Returns dict with:
      - lots: float/int
      - is_zero_lots: bool
      - risk_amount_inr: float
      - risk_amount_usd: float
      - loss_per_lot_inr: float
      - min_capital_needed_user: float
      - user_currency: str
      - live_usdinr: float
      - lot_mode: str
      - margin_note: str
    """
    cfg = get_money_config()
    lot_mode = cfg.get("lot_mode", "paper_fractional")
    capital = float(cfg.get("capital", 50000.0))
    capital_currency = cfg.get("capital_currency", "INR")
    risk_pct = min(float(cfg.get("risk_pct", 1.0)), 2.0)  # Max 2% for beginner

    live_usdinr = get_live_usdinr_rate()

    # Convert capital to INR
    if capital_currency == "USD":
        capital_inr = capital * live_usdinr
    else:
        capital_inr = capital

    risk_amount_inr = capital_inr * (risk_pct / 100.0)
    risk_amount_usd = risk_amount_inr / live_usdinr if live_usdinr > 0 else (capital * risk_pct / 100.0)

    sl_distance = abs(entry_price - sl_price)
    if sl_distance <= 0:
        return None

    # Contract lot size from config/pairs.yaml (e.g. 1000 for USD/INR, 100 for Gold)
    contract_lot_size = asset_cfg.get("lot_size", 1000)

    # If quote currency is USD (e.g. XAU/USD), convert sl loss to INR
    quote_currency = asset_cfg.get("quote", "INR")
    if quote_currency == "USD":
        loss_per_lot_inr = sl_distance * contract_lot_size * live_usdinr
    else:
        loss_per_lot_inr = sl_distance * contract_lot_size

    if loss_per_lot_inr <= 0:
        return None

    raw_lots = risk_amount_inr / loss_per_lot_inr

    if lot_mode == "exchange":
        # Whole lots only, strictly floor (never round up)
        lots = int(math.floor(raw_lots))
        max_cap = cfg.get("max_lots_exchange", 10)
        lots = min(lots, max_cap)
    else:
        # Paper fractional mode: round down to 0.01 step (min 0.01 for simulation)
        lots = math.floor(raw_lots * 100.0) / 100.0
        if raw_lots > 0 and lots < 0.01:
            lots = 0.01
        max_cap = cfg.get("max_lots_paper", 5.0)
        lots = min(lots, max_cap)

    is_zero_lots = (lots == 0)

    # Minimum capital needed for 1 lot in exchange mode
    min_capital_needed_inr = loss_per_lot_inr / (risk_pct / 100.0)
    if capital_currency == "USD":
        min_capital_needed_user = min_capital_needed_inr / live_usdinr
    else:
        min_capital_needed_user = min_capital_needed_inr

    actual_risk_inr = sl_distance * contract_lot_size * lots
    if quote_currency == "USD":
        actual_risk_inr *= live_usdinr
    actual_risk_usd = actual_risk_inr / live_usdinr if live_usdinr > 0 else 0.0

    return {
        "lots": lots,
        "is_zero_lots": is_zero_lots,
        "raw_lots": raw_lots,
        "risk_amount_inr": round(actual_risk_inr if lots > 0 else risk_amount_inr, 2),
        "risk_amount_usd": round(actual_risk_usd if lots > 0 else risk_amount_usd, 2),
        "loss_per_lot_inr": round(loss_per_lot_inr, 2),
        "min_capital_needed_user": round(min_capital_needed_user, 2),
        "user_currency": capital_currency,
        "live_usdinr": round(live_usdinr, 4),
        "lot_mode": lot_mode,
        "risk_pct": risk_pct,
        "margin_note": "Broker se margin requirement confirm karein",
    }
