"""
engine/signal_engine.py — Mentor Persona Signal Engine

Multi-strategy confluence engine that consumes data exclusively through
data_layer.get_market_snapshot() and data_layer.get_historical().

Key principles:
  - Support/resistance from historical data (never invented)
  - Multiple strategies must CONFIRM each other
  - News/macro factor affects conviction
  - Risk-reward calculation with mandatory stop-loss
  - "No trade" is always a valid output
"""

import data_layer as dl


# ============================================
# STRATEGY: Support / Resistance from History
# ============================================
def _find_sr_levels(candles, lookback=100):
    """Find support and resistance levels using swing points."""
    if not candles or len(candles) < 20:
        return [], []

    subset = candles[-lookback:] if len(candles) >= lookback else candles
    swing_highs = dl.find_swing_highs(subset, lookback=3)
    swing_lows = dl.find_swing_lows(subset, lookback=3)

    resistance_levels = [price for _, price in swing_highs[-5:]]  # last 5 swing highs
    support_levels = [price for _, price in swing_lows[-5:]]  # last 5 swing lows

    return support_levels, resistance_levels


# ============================================
# STRATEGY: Multi-Timeframe Trend Alignment
# ============================================
def _check_trend_alignment(snapshot):
    """Check if 1H and 15M trends agree."""
    candles_15m = snapshot.get("candles_15m")
    candles_1h = snapshot.get("candles_1h")

    if not candles_15m or not candles_1h:
        return "NEUTRAL", {}

    trend_1h = dl.htf_trend(candles_1h)
    tf_bias, bos_type, choch = dl.analyze_structure_bos(candles_15m)

    # Fallback to EMA if structure is neutral
    if tf_bias == "NEUTRAL" and candles_15m:
        closes = [c["close"] for c in candles_15m]
        ema10 = dl.calculate_ema(closes, 10)
        ema30 = dl.calculate_ema(closes, 30)
        tf_bias = "BULLISH" if ema10 > ema30 else "BEARISH"

    aligned = (tf_bias == trend_1h)

    return tf_bias, {
        "trend_1h": trend_1h,
        "tf_bias": tf_bias,
        "bos_type": bos_type,
        "choch": choch,
        "aligned": aligned,
    }


# ============================================
# STRATEGY: ICT Confluence (OB + FVG + Liq)
# ============================================
def _check_ict_confluence(candles_5m, bias, asset_cfg):
    """Check ICT concepts: order blocks, FVGs, liquidity."""
    results = {}

    ob_high, ob_low, in_ob = dl.detect_order_block(candles_5m, bias)
    results["ob_high"] = ob_high
    results["ob_low"] = ob_low
    results["in_order_block"] = in_ob

    fvg, fvg_score = dl.detect_fvg(candles_5m, asset_cfg)
    results["fvg"] = fvg
    results["fvg_score"] = fvg_score

    eq_hi, eq_lo, swept_hi, swept_lo = dl.detect_liquidity_zones(candles_5m, asset_cfg)
    results["swept_high"] = swept_hi
    results["swept_low"] = swept_lo

    grab, grab_score = dl.detect_liquidity_grab(candles_5m, asset_cfg)
    results["liquidity_grab"] = grab
    results["grab_score"] = grab_score

    return results


# ============================================
# STRATEGY: Indicator Confluence (EMA, VWAP, RSI, MACD)
# ============================================
def _check_indicator_confluence(candles_5m, bias, asset_cfg):
    """Check technical indicator alignment."""
    results = {}

    ema8, ema21, ema50, ema_bias, ema_aligned, ema_score = dl.get_ema_confluence(candles_5m)
    results["ema8"] = ema8
    results["ema21"] = ema21
    results["ema50"] = ema50
    results["ema_bias"] = ema_bias
    results["ema_aligned"] = ema_aligned
    results["ema_score"] = ema_score

    vwap, vwap_bias, vwap_score = dl.calculate_vwap(candles_5m, asset_cfg)
    results["vwap"] = vwap
    results["vwap_bias"] = vwap_bias
    results["vwap_score"] = vwap_score

    rsi = dl.calculate_rsi(candles_5m)
    results["rsi"] = rsi

    macd_line, macd_signal, macd_hist = dl.calculate_macd(candles_5m)
    results["macd_bullish"] = macd_line > macd_signal and macd_hist > 0
    results["macd_bearish"] = macd_line < macd_signal and macd_hist < 0

    adx = dl.calculate_adx(candles_5m)
    results["adx"] = adx

    atr = dl.calculate_atr(candles_5m)
    results["atr"] = atr

    return results


# ============================================
# STRATEGY: Pattern & Momentum
# ============================================
def _check_patterns(candles_5m, bias, asset_cfg):
    """Check candle patterns and momentum."""
    results = {}

    pattern, pat_score = dl.check_candle_pattern(candles_5m, asset_cfg)
    results["pattern"] = pattern
    results["pattern_score"] = pat_score

    momentum_ok, momentum_score = dl.check_momentum(candles_5m, bias)
    results["momentum_ok"] = momentum_ok
    results["momentum_score"] = momentum_score

    div_bull = dl.detect_rsi_divergence(candles_5m, "BULLISH")
    div_bear = dl.detect_rsi_divergence(candles_5m, "BEARISH")
    results["div_bull"] = div_bull
    results["div_bear"] = div_bear

    ote_in, ote_score, ote_bot, ote_top = dl.detect_ote_zone(candles_5m, bias, asset_cfg)
    results["ote_in_zone"] = ote_in
    results["ote_score"] = ote_score
    results["ote_bottom"] = ote_bot
    results["ote_top"] = ote_top

    # Asian sweep
    use_asian = (asset_cfg or {}).get("use_asian_sweep", False)
    if use_asian:
        asian_swept, asian_score = dl.detect_asian_sweep(candles_5m, bias)
    else:
        asian_swept, asian_score = False, 0
    results["asian_swept"] = asian_swept
    results["asian_score"] = asian_score

    return results


# ============================================
# RISK-REWARD CALCULATION
# ============================================
def _calculate_risk_reward(candles_5m, signal_dir, ict, indicators, asset_cfg):
    """
    Calculate SL, TP, lot size and validate risk.

    Stop-loss is ALWAYS mandatory — if we can't compute a valid SL,
    we reject the trade.
    """
    if not candles_5m:
        return None

    curr_price = candles_5m[-1]["close"]
    atr = indicators.get("atr")
    ob_high = ict.get("ob_high")
    ob_low = ict.get("ob_low")

    min_sl = (asset_cfg or {}).get("min_sl", 3.0)
    max_sl = (asset_cfg or {}).get("max_sl", 18.0)
    rr_ratio = (asset_cfg or {}).get("rr_ratio", 2.5)
    atr_sl_mult = 1.5

    atr_sl = (atr * atr_sl_mult) if atr else (min_sl * 2.5)

    if signal_dir == "LONG":
        if ob_low is not None:
            pip_v = (asset_cfg or {}).get("pip_value", 1.0)
            struct_sl = curr_price - (ob_low - 0.50 * pip_v)
        else:
            swing_lows = dl.find_swing_lows(candles_5m[-30:])
            if swing_lows:
                pip_v = (asset_cfg or {}).get("pip_value", 1.0)
                struct_sl = curr_price - (swing_lows[-1][1] - 0.50 * pip_v)
            else:
                struct_sl = min_sl * 2.5
        sl_distance = max(struct_sl, atr_sl, min_sl)
    elif signal_dir == "SHORT":
        if ob_high is not None:
            pip_v = (asset_cfg or {}).get("pip_value", 1.0)
            struct_sl = (ob_high + 0.50 * pip_v) - curr_price
        else:
            swing_highs = dl.find_swing_highs(candles_5m[-30:])
            if swing_highs:
                pip_v = (asset_cfg or {}).get("pip_value", 1.0)
                struct_sl = (swing_highs[-1][1] + 0.50 * pip_v) - curr_price
            else:
                struct_sl = min_sl * 2.5
        sl_distance = max(struct_sl, atr_sl, min_sl)
    else:
        return None

    sl_distance = min(sl_distance, max_sl)
    tp_distance = sl_distance * rr_ratio

    # MANDATORY: SL must be valid
    if sl_distance <= 0:
        return None

    # Calculate lots (paper trading — $500 capital, 5% risk)
    capital = 500
    risk_pct = 0.05
    risk_amount = capital * risk_pct
    contract_size = (asset_cfg or {}).get("contract_size", 100)

    raw_lots = risk_amount / (sl_distance * contract_size) if (sl_distance * contract_size) > 0 else 0.01
    lots = round(raw_lots, 2)
    lots = max(0.01, min(lots, 0.50))

    actual_risk = sl_distance * lots * contract_size

    if signal_dir == "LONG":
        sl_price = curr_price - sl_distance
        tp_price = curr_price + tp_distance
    else:
        sl_price = curr_price + sl_distance
        tp_price = curr_price - tp_distance

    return {
        "entry_price": curr_price,
        "sl_price": round(sl_price, 2),
        "tp_price": round(tp_price, 2),
        "sl_distance": round(sl_distance, 2),
        "tp_distance": round(tp_distance, 2),
        "lots": lots,
        "actual_risk": round(actual_risk, 2),
        "rr_ratio": rr_ratio,
    }


# ============================================
# SCORING ENGINE — Multi-Confirmation
# ============================================
def _score_signal(bias, trend_info, ict, indicators, patterns, session, asset_cfg):
    """
    Score a potential signal based on multiple confirming strategies.
    Returns (score, reasons) tuple.
    """
    score = 0
    reasons = []

    # --- Session / Kill Zone (up to 15 pts) ---
    if session and session.get("name") != "OFF_HOURS":
        kz_pts = 15 if session.get("is_silver_bullet") else 12
        score += kz_pts
        reasons.append(f"🎯 {session['label']} (+{kz_pts})")

    # --- HTF + 15M Trend Alignment (20 pts) ---
    if trend_info.get("aligned"):
        score += 20
        bos = trend_info.get("bos_type") or "trend"
        reasons.append(f"📈 1H+15M {bias} ({bos}) (+20)")
    elif trend_info.get("tf_bias") == bias:
        score += 10
        reasons.append(f"📊 15M {bias} (HTF not aligned) (+10)")

    # --- Order Block (12 pts) ---
    if ict.get("in_order_block"):
        score += 12
        reasons.append(f"📦 Price in {bias} Order Block (+12)")

    # --- VWAP (10 pts) ---
    if indicators.get("vwap_bias") == bias:
        pts = indicators.get("vwap_score", 5)
        score += pts
        vwap_val = indicators.get("vwap", 0)
        reasons.append(f"📊 VWAP {bias} ({vwap_val:.2f}) (+{pts})")

    # --- EMA Confluence (8 pts) ---
    if indicators.get("ema_bias") == bias and indicators.get("ema_score", 0) > 0:
        pts = indicators["ema_score"]
        aligned_text = " (Full Align)" if indicators.get("ema_aligned") else ""
        score += pts
        reasons.append(f"📉 EMA 8/21/50 {bias}{aligned_text} (+{pts})")

    # --- FVG (8 pts) ---
    fvg = ict.get("fvg")
    expected_fvg = "BULLISH_FVG" if bias == "BULLISH" else "BEARISH_FVG"
    if fvg == expected_fvg:
        pts = ict.get("fvg_score", 8)
        score += pts
        reasons.append(f"⚡ {fvg} (+{pts})")

    # --- OTE Zone (8 pts) ---
    if patterns.get("ote_in_zone"):
        pts = patterns.get("ote_score", 8)
        score += pts
        reasons.append(f"🎯 OTE Zone Entry (+{pts})")

    # --- Candle Pattern (6 pts) ---
    pat = patterns.get("pattern")
    bullish_pats = ["BULLISH_ENGULF", "HAMMER", "MORNING_STAR"]
    bearish_pats = ["BEARISH_ENGULF", "SHOOTING_STAR", "EVENING_STAR"]
    if (bias == "BULLISH" and pat in bullish_pats) or (bias == "BEARISH" and pat in bearish_pats):
        pts = patterns.get("pattern_score", 2) * 2
        score += pts
        reasons.append(f"🕯 Pattern: {pat} (+{pts})")

    # --- RSI Divergence (5 pts) ---
    if bias == "BULLISH" and patterns.get("div_bull"):
        score += 5
        reasons.append("📈 Bullish RSI Divergence (+5)")
    elif bias == "BEARISH" and patterns.get("div_bear"):
        score += 5
        reasons.append("📉 Bearish RSI Divergence (+5)")

    # --- Momentum (5 pts) ---
    if patterns.get("momentum_ok"):
        pts = patterns.get("momentum_score", 2)
        score += pts
        reasons.append(f"💪 Strong Momentum (+{pts})")

    # --- ADX Bonus (3 pts) ---
    adx = indicators.get("adx", 0)
    if adx >= 30:
        score += 3
        reasons.append(f"📶 Strong Trend ADX={adx} (+3)")

    # --- CHoCH Bonus (5 pts) ---
    if trend_info.get("choch"):
        score += 5
        reasons.append("🔄 15M CHoCH Reversal (+5)")

    # --- Asian Sweep Bonus (15 pts) ---
    if patterns.get("asian_swept"):
        pts = patterns.get("asian_score", 15)
        score += pts
        reasons.append(f"🏯 Asian Range Swept — Judas Swing (+{pts})")

    # --- Liquidity sweep (5 pts) ---
    if bias == "BULLISH" and ict.get("swept_low"):
        score += 5
        reasons.append("💧 Equal Lows Swept (+5)")
    elif bias == "BEARISH" and ict.get("swept_high"):
        score += 5
        reasons.append("💧 Equal Highs Swept (+5)")

    # --- Liquidity Grab (3 pts) ---
    grab = ict.get("liquidity_grab")
    if (bias == "BULLISH" and grab == "BULLISH_GRAB") or (bias == "BEARISH" and grab == "BEARISH_GRAB"):
        score += 3
        reasons.append(f"💧 {grab} (+3)")

    # --- RSI Extreme (3 pts) ---
    rsi = indicators.get("rsi", 50)
    if bias == "BULLISH" and rsi < 30:
        score += 3
        reasons.append(f"📉 RSI Oversold ({rsi}) (+3)")
    elif bias == "BEARISH" and rsi > 70:
        score += 3
        reasons.append(f"📈 RSI Overbought ({rsi}) (+3)")

    return score, reasons


# ============================================
# MAIN SIGNAL GENERATION
# ============================================
MIN_CONFIDENCE = 50  # Minimum score to trigger a signal

def generate_mentor_signal(snapshot):
    """
    Generate a trading signal from a market snapshot.

    Returns a signal dict or None ("no trade" is a valid output).

    The signal is built ONLY from live data in the snapshot.
    Never invents prices or levels.
    """
    candles_5m = snapshot.get("candles_5m")
    candles_15m = snapshot.get("candles_15m")
    candles_1h = snapshot.get("candles_1h")
    asset_cfg = snapshot.get("asset_config", {})
    session = snapshot.get("session")
    pair = snapshot.get("pair", "XAU/USD")

    if not candles_5m or not candles_15m or not candles_1h:
        return None

    # --- NEWS GATE ---
    if snapshot.get("news_blocked"):
        print(f"🚫 Trade blocked: {snapshot.get('news_title', 'High-impact news')}")
        return None

    # --- TREND ALIGNMENT ---
    bias, trend_info = _check_trend_alignment(snapshot)
    if bias == "NEUTRAL":
        print("  ❌ No clear trend direction. No trade.")
        return None

    # --- ICT CONFLUENCE ---
    ict = _check_ict_confluence(candles_5m, bias, asset_cfg)

    # --- INDICATOR CONFLUENCE ---
    indicators = _check_indicator_confluence(candles_5m, bias, asset_cfg)

    # --- PATTERNS & MOMENTUM ---
    patterns = _check_patterns(candles_5m, bias, asset_cfg)

    # --- SCORE BOTH DIRECTIONS ---
    long_score, long_reasons = _score_signal(
        "BULLISH", trend_info, ict, indicators, patterns, session, asset_cfg
    )
    short_score, short_reasons = _score_signal(
        "BEARISH", trend_info, ict, indicators, patterns, session, asset_cfg
    )

    print(f"\n  📊 SCORE: Long={long_score} | Short={short_score} | Need: {MIN_CONFIDENCE}+")

    # --- PICK DIRECTION ---
    signal_dir = None
    score = 0
    reasons = []

    if long_score > short_score and long_score >= MIN_CONFIDENCE:
        signal_dir = "LONG"
        score = min(long_score, 99)
        reasons = long_reasons
    elif short_score > long_score and short_score >= MIN_CONFIDENCE:
        signal_dir = "SHORT"
        score = min(short_score, 99)
        reasons = short_reasons

    if not signal_dir:
        print(f"  ❌ No signal — Confidence below {MIN_CONFIDENCE}%.")
        return None

    # --- MULTI-CONFIRMATION GATE ---
    # At least 2 of 3 core indicators must agree
    if signal_dir == "LONG":
        confirmations = sum([
            indicators.get("macd_bullish", False),
            indicators.get("rsi", 50) > 50,
            indicators.get("ema_bias") == "BULLISH",
        ])
    else:
        confirmations = sum([
            indicators.get("macd_bearish", False),
            indicators.get("rsi", 50) < 50,
            indicators.get("ema_bias") == "BEARISH",
        ])

    if confirmations >= 2:
        reasons.append(f"✅ {confirmations}/3 Indicator Confluence")

    # --- RISK-REWARD CALCULATION ---
    risk = _calculate_risk_reward(candles_5m, signal_dir, ict, indicators, asset_cfg)
    if risk is None:
        print("  ❌ Cannot compute valid stop-loss. No trade.")
        return None

    # --- SUPPORT / RESISTANCE CONTEXT ---
    supports, resistances = _find_sr_levels(candles_1h)

    # --- BUILD SIGNAL ---
    return {
        "pair": pair,
        "signal": signal_dir,
        "confidence": score,
        "reasons": reasons,
        "entry_price": risk["entry_price"],
        "sl_price": risk["sl_price"],
        "tp_price": risk["tp_price"],
        "sl_distance": risk["sl_distance"],
        "tp_distance": risk["tp_distance"],
        "lots": risk["lots"],
        "actual_risk": risk["actual_risk"],
        "rr_ratio": risk["rr_ratio"],
        # Context for mentor explanation
        "trend_1h": trend_info.get("trend_1h", "N/A"),
        "tf_bias": trend_info.get("tf_bias", "N/A"),
        "bos_type": trend_info.get("bos_type", "None"),
        "choch": trend_info.get("choch", False),
        "adx": indicators.get("adx", 0),
        "atr": indicators.get("atr", 0),
        "rsi": indicators.get("rsi", 50),
        "ema8": indicators.get("ema8"),
        "ema21": indicators.get("ema21"),
        "ema50": indicators.get("ema50"),
        "ema_aligned": indicators.get("ema_aligned", False),
        "vwap": indicators.get("vwap"),
        "vwap_bias": indicators.get("vwap_bias", "NEUTRAL"),
        "fvg": ict.get("fvg", "None"),
        "pattern": patterns.get("pattern", "None"),
        "ob_high": ict.get("ob_high"),
        "ob_low": ict.get("ob_low"),
        "in_order_block": ict.get("in_order_block", False),
        "swept_high": ict.get("swept_high", False),
        "swept_low": ict.get("swept_low", False),
        "asian_swept": patterns.get("asian_swept", False),
        "ote_in_zone": patterns.get("ote_in_zone", False),
        "supports": supports,
        "resistances": resistances,
        "session": session,
        "macro": snapshot.get("macro", {}),
        "news_blocked": False,
    }
