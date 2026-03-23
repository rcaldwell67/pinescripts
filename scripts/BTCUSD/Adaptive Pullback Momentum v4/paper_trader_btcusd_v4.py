

def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))


def append_trade(trade: dict) -> None:
    TRADES_FILE.parent.mkdir(parents=True, exist_ok=True)
    new_file = not TRADES_FILE.exists()

    with open(TRADES_FILE, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=TRADES_COLS)
        if new_file:
            w.writeheader()
        w.writerow({k: trade.get(k, "") for k in TRADES_COLS})
    log.info("Trade appended → %s", TRADES_FILE.name)

# ── Data fetching ──────────────────────────────────────────────────────────────
def fetch_bars(data_client) -> pd.DataFrame:
    end = datetime.now(timezone.utc)
    start = datetime(end.year, 1, 1, tzinfo=timezone.utc)
    req = CryptoBarsRequest(
        symbol_or_symbols=[SYMBOL],
        timeframe=TimeFrame(30, TimeFrameUnit.Minute),
        start=start,
        end=end,
    )
    try:
        bars = data_client.get_crypto_bars(req)
        df   = bars.df.reset_index()
    except Exception as e:
        log.error("fetch_bars failed: %s", e)
        return pd.DataFrame()
    if df.empty:
        return pd.DataFrame()

    df = (df[df["symbol"] == SYMBOL].copy()
            .sort_values("timestamp")
            .set_index("timestamp")
            [["open", "high", "low", "close", "volume"]]
            .rename(columns=str.title))
    df = df[df["Volume"] > 0].dropna()
    df.index = pd.to_datetime(df.index, utc=True)
    return df


# ── Indicators ────────────────────────────────────────────────────────────────
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()

    d["EMA_F"] = d["Close"].ewm(span=EMA_FAST_LEN, adjust=False).mean()
    d["EMA_M"] = d["Close"].ewm(span=EMA_MID_LEN,  adjust=False).mean()
    d["EMA_S"] = d["Close"].ewm(span=EMA_SLOW_LEN, adjust=False).mean()

    delta = d["Close"].diff()
    g  = delta.clip(lower=0).ewm(alpha=1/RSI_LEN, adjust=False).mean()
    lv = (-delta).clip(lower=0).ewm(alpha=1/RSI_LEN, adjust=False).mean()
    d["RSI"] = 100 - 100 / (1 + g / lv.replace(0, 1e-10))

    hl  = d["High"] - d["Low"]
    hpc = (d["High"] - d["Close"].shift()).abs()
    lpc = (d["Low"]  - d["Close"].shift()).abs()
    tr  = pd.concat([hl, hpc, lpc], axis=1).max(axis=1)
    d["ATR"]    = tr.ewm(alpha=1/ATR_LEN, adjust=False).mean()
    d["ATR_BL"] = d["ATR"].rolling(ATR_BL_LEN).mean()
    d["VOL_MA"] = d["Volume"].rolling(VOL_LEN).mean()

    up  = d["High"].diff()
    dn  = -d["Low"].diff()
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    atr_s = d["ATR"].replace(0, np.nan)
    d["DI_PLUS"]  = 100 * pd.Series(pdm, index=d.index).ewm(alpha=1/ADX_LEN, adjust=False).mean() / atr_s
    d["DI_MINUS"] = 100 * pd.Series(ndm, index=d.index).ewm(alpha=1/ADX_LEN, adjust=False).mean() / atr_s
    dx  = (100 * (d["DI_PLUS"] - d["DI_MINUS"]).abs()
               / (d["DI_PLUS"] + d["DI_MINUS"]).replace(0, 1e-10))
    d["ADX"] = dx.ewm(alpha=1/ADX_LEN, adjust=False).mean()

    return d.dropna()


# ── Signal evaluation ─────────────────────────────────────────────────────────
def check_signal(df: pd.DataFrame) -> dict | None:
    needed = EMA_SLOPE_BARS + 5
    if len(df) < needed:
        log.debug("Not enough bars: %d < %d", len(df), needed)
        return None

    bar  = df.iloc[-1]
    prev = df.iloc[-2]

    close  = float(bar["Close"])
    atr    = float(bar["ATR"])
    atr_bl = float(bar["ATR_BL"])
    opn    = float(bar["Open"])

    if float(bar["ADX"]) <= ADX_THRESH:
        log.info("Filter: ADX %.2f ≤ %d — skip", float(bar["ADX"]), ADX_THRESH)
        return None
    if atr > atr_bl * PANIC_MULT:
        log.info("Filter: PANIC mode — ATR %.4f > ATR_BL %.4f × %.2f — skip", atr, atr_bl, PANIC_MULT)
        return None
    if atr < close * ATR_FLOOR:
        log.info("Filter: ATR floor — ATR %.4f < Close %.2f × %.4f — skip", atr, close, ATR_FLOOR)
        return None

    if float(bar["Volume"]) < float(bar["VOL_MA"]) * VOL_MULT:
        log.info("Filter: Volume %.2f < VOL_MA %.2f × %.2f — skip", float(bar["Volume"]), float(bar["VOL_MA"]), VOL_MULT)
        return None
    body = abs(close - opn) / atr
    if body < MIN_BODY:
        log.info("Filter: Body %.4f < MIN_BODY %.4f — skip", body, MIN_BODY)
        return None

    ema_f_now  = float(bar["EMA_F"])
    ema_m_now  = float(bar["EMA_M"])
    ema_s_now  = float(bar["EMA_S"])
    ema_f_prev = float(prev["EMA_F"])
    rsi        = float(bar["RSI"])
    rsi_prev   = float(df["RSI"].iloc[-2])

    stop_dist = atr * SL_MULT

    # ── Long signal ─────────────────────────────────────────────────────────
    if TRADE_LONGS:
        ema_bull  = ema_f_now > ema_m_now and ema_m_now > ema_s_now
        long_pb   = (float(prev["Low"]) <= ema_f_prev * (1.0 + PB_PCT / 100.0)
                     and close > ema_f_now
                     and close > opn)
        rsi_ok_l  = RSI_LO_L <= rsi <= RSI_HI_L

        # EMA slope: EMA_F rising vs N bars ago
        ema_slope_l = True
        if EMA_SLOPE_BARS > 0 and len(df) > EMA_SLOPE_BARS + 2:
            ema_f_past = float(df["EMA_F"].iloc[-1 - EMA_SLOPE_BARS])
            ema_slope_l = ema_f_now > ema_f_past

        rsi_rising = (not USE_RSI_DIR) or (rsi > rsi_prev)

        if not ema_bull:
            log.info("Filter: Not EMA bull — skip")
        if not long_pb:
            log.info("Filter: Not long PB — skip")
        if not rsi_ok_l:
            log.info("Filter: RSI %.2f not in long band [%d, %d] — skip", rsi, RSI_LO_L, RSI_HI_L)
        if not ema_slope_l:
            log.info("Filter: EMA slope not rising — skip")
        if not rsi_rising:
            log.info("Filter: RSI not rising — skip")

        if ema_bull and long_pb and rsi_ok_l and ema_slope_l and rsi_rising:
            sl = close - stop_dist
            tp = close + atr * TP_MULT
            log.info(
                "LONG SIGNAL: entry=%.2f  sl=%.2f  tp=%.2f  "
                "atr=%.2f  adx=%.1f  rsi=%.1f",
                close, sl, tp, atr, float(bar["ADX"]), rsi,
            )
            return {
                "direction":         "long",
                "entry":             close,
                "sl":                sl,
                "tp":                tp,
                "trail_activate_px": close + atr * TRAIL_ACT,
                "trail_dist_atr":    atr * TRAIL_DIST,
                "entry_atr":         atr,
            }

    # ── Short signal ─────────────────────────────────────────────────────────
    if TRADE_SHORTS:
        ema_bear  = ema_f_now < ema_m_now and ema_m_now < ema_s_now
        short_pb  = (float(prev["High"]) >= ema_f_prev * (1.0 - PB_PCT / 100.0)
                     and close < ema_f_now
                     and close < opn)
        rsi_ok_s  = RSI_LO_S <= rsi <= RSI_HI_S

        ema_slope_s = True
        if EMA_SLOPE_BARS > 0 and len(df) > EMA_SLOPE_BARS + 2:
            ema_f_past = float(df["EMA_F"].iloc[-1 - EMA_SLOPE_BARS])
            ema_slope_s = ema_f_now < ema_f_past

        rsi_falling = (not USE_RSI_DIR) or (rsi < rsi_prev)

        if not ema_bear:
            log.info("Filter: Not EMA bear — skip")
        if not short_pb:
            log.info("Filter: Not short PB — skip")
        if not rsi_ok_s:
            log.info("Filter: RSI %.2f not in short band [%d, %d] — skip", rsi, RSI_LO_S, RSI_HI_S)
        if not ema_slope_s:
            log.info("Filter: EMA slope not falling — skip")
        if not rsi_falling:
            log.info("Filter: RSI not falling — skip")

        if ema_bear and short_pb and rsi_ok_s and ema_slope_s and rsi_falling:
            sl = close + stop_dist
            tp = close - atr * TP_MULT
            log.info(
                "SHORT SIGNAL: entry=%.2f  sl=%.2f  tp=%.2f  "
                "atr=%.2f  adx=%.1f  rsi=%.1f",
                close, sl, tp, atr, float(bar["ADX"]), rsi,
            )
            return {
                "direction":         "short",
                "entry":             close,
                "sl":                sl,
                "tp":                tp,
                "trail_activate_px": close - atr * TRAIL_ACT,
                "trail_dist_atr":    atr * TRAIL_DIST,
                "entry_atr":         atr,
            }

    log.info(
        "No signal  close=%.2f  ADX=%.1f  RSI=%.1f  EMA_F=%.2f  EMA_M=%.2f",
        close, float(bar["ADX"]), rsi, ema_f_now, ema_m_now,
    )
    return None


# ── Alpaca helpers ─────────────────────────────────────────────────────────────
def get_open_position(tc):
    try:
        return tc.get_open_position(SYMBOL.replace("/", ""))
    except Exception:
        return None


def cancel_order_safe(tc, order_id: str) -> None:
    try:
        tc.cancel_order_by_id(order_id)
        log.info("Cancelled order %s", order_id)
    except Exception as e:
        log.warning("cancel_order %s: %s", order_id, e)


def find_exit_fill(tc, pos: dict) -> tuple[float, str]:
    after_dt  = datetime.fromisoformat(pos["entry_time"])
    direction = pos["direction"]
    exit_side = "sell" if direction == "long" else "buy"
    try:
        orders = tc.get_orders(GetOrdersRequest(
            status=QueryOrderStatus.CLOSED,
            symbols=[SYMBOL.replace("/", "")],
            after=after_dt,
            limit=10,
        ))
    except Exception as e:
        log.warning("get_orders failed: %s", e)
        return pos["sl"], "SL"

    for o in orders:
        if getattr(o.status, "value", None) == "filled" and o.filled_avg_price:
            oid = str(o.id)
            fp  = float(o.filled_avg_price)
            if oid == pos.get("tp_order_id"):
                return fp, "TP"
            if oid == pos.get("sl_order_id"):
                return fp, "SL"

    entry = pos["entry"]
    tp    = pos["tp"]
    for o in orders:
        if (getattr(o.status, "value", None) == "filled"
                and o.filled_avg_price
                and getattr(o.side, "value", None) == exit_side):
            fp = float(o.filled_avg_price)
            if direction == "long":
                if fp >= entry + (tp - entry) * 0.95:
                    return fp, "TP"
                elif fp < entry:
                    return fp, "SL"
                return fp, "Trail"
            else:
                if fp <= entry - (entry - tp) * 0.95:
                    return fp, "TP"
                elif fp > entry:
                    return fp, "SL"
                return fp, "Trail"
    return pos["sl"], "SL"


def submit_entry(tc, direction: str, qty: float) -> None:
    side = OrderSide.BUY if direction == "long" else OrderSide.SELL
    tc.submit_order(MarketOrderRequest(
        symbol=SYMBOL, qty=qty, side=side,
        time_in_force=TimeInForce.GTC,
        client_order_id=f"apm_btc_v4_entry_{int(datetime.now(timezone.utc).timestamp())}",
    ))


def submit_sl(tc, direction: str, qty: float, sl_price: float) -> str:
    side = OrderSide.SELL if direction == "long" else OrderSide.BUY
    o = tc.submit_order(StopOrderRequest(
        symbol=SYMBOL, qty=qty, side=side,
        time_in_force=TimeInForce.GTC,
        stop_price=round(sl_price, 2),
        client_order_id=f"apm_btc_v4_sl_{int(datetime.now(timezone.utc).timestamp())}",
    ))
    return str(o.id)


def submit_tp(tc, direction: str, qty: float, tp_price: float) -> str:
    side = OrderSide.SELL if direction == "long" else OrderSide.BUY
    o = tc.submit_order(LimitOrderRequest(
        symbol=SYMBOL, qty=qty, side=side,
        time_in_force=TimeInForce.GTC,
        limit_price=round(tp_price, 2),
        client_order_id=f"apm_btc_v4_tp_{int(datetime.now(timezone.utc).timestamp())}",
    ))
    return str(o.id)


def _record_closed_trade(state: dict, pos: dict, exit_price: float,
                         result: str, bars_held=None) -> None:
    entry     = pos["entry"]
    notional  = pos["notional"]
    direction = pos["direction"]
    pnl_pct   = ((exit_price - entry) / entry if direction == "long"
                 else (entry - exit_price) / entry)
    dollar_pnl = pnl_pct * notional - notional * COMMISSION_PCT * 2
    state["equity"] += dollar_pnl
    if bars_held is None:
        bars_held = pos.get("bars_in_trade", "?")
    append_trade({
        "entry_time":  pos["entry_time"],
        "exit_time":   datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00:00"),
        "direction":   direction,
        "entry":       round(entry, 2),
        "exit":        round(exit_price, 2),
        "exit_reason": result,
        "bars_held":   bars_held,
        "pnl_pct":     round(pnl_pct * 100, 3),
        "dollar_pnl":  round(dollar_pnl, 2),
        "equity":      round(state["equity"], 2),
    })
    log.info(
        "Closed: %s %s  exit=%.2f  pnl=%+.2f  equity=%.2f",
        result, direction, exit_price, dollar_pnl, state["equity"],
    )
    state["position"] = None


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    log.info("=== APM v4.2 Paper Trader — %s 30m (longs + shorts) ===", SYMBOL)

    if not API_KEY or not API_SECRET:
        log.error("Missing credentials — set ALPACA_PAPER_API_KEY / ALPACA_PAPER_API_SECRET.")
        # log_failure("Missing credentials", "API_KEY or API_SECRET not set")
        sys.exit(1)

    data_client    = CryptoHistoricalDataClient(API_KEY, API_SECRET)
    trading_client = TradingClient(API_KEY, API_SECRET, paper=True)


    log.info("\n=== BACKTEST: Simulating all YTD bars for trade generation ===")
    df = fetch_bars(data_client)
    if df.empty or len(df) < MIN_BARS:
        msg = f"Insufficient bars ({len(df)} < {MIN_BARS}) — skipping."
        log.warning(msg)
        return
    df = compute_indicators(df)
    if df.empty:
        return

    state = {"position": None, "equity": INITIAL_CAPITAL, "last_bar_ts": None}
    # Limit to 500 bars for quick test
    max_bars = min(len(df), MIN_BARS + 500)
    for i in range(MIN_BARS, max_bars):
        if (i - MIN_BARS) % 100 == 0:
            log.info(f"Progress: {i - MIN_BARS} / {max_bars - MIN_BARS} bars processed...")
        subdf = df.iloc[:i+1]
        ts = subdf.index[-1]
        bar = subdf.iloc[-1]
        signal = check_signal(subdf)
        # If in a position, simulate exit if SL/TP hit
        if state["position"] is not None:
            pos = state["position"]
            direction = pos["direction"]
            entry = pos["entry"]
            sl = pos["sl"]
            tp = pos["tp"]
            price = float(bar["Close"])
            exit_reason = None
            if direction == "long":
                if price <= sl:
                    exit_reason = "SL"
                elif price >= tp:
                    exit_reason = "TP"
            else:
                if price >= sl:
                    exit_reason = "SL"
                elif price <= tp:
                    exit_reason = "TP"
            if exit_reason:
                pnl_pct = ((price - entry) / entry) if direction == "long" else ((entry - price) / entry)
                dollar_pnl = pnl_pct * pos["notional"] - pos["notional"] * COMMISSION_PCT * 2
                state["equity"] += dollar_pnl
                append_trade({
                    "entry_time": pos["entry_time"],
                    "exit_time": ts.strftime("%Y-%m-%d %H:%M:%S+00:00"),
                    "direction": direction,
                    "entry": round(entry, 2),
                    "exit": round(price, 2),
                    "exit_reason": exit_reason,
                    "bars_held": i - pos["bar_idx"],
                    "pnl_pct": round(pnl_pct * 100, 3),
                    "dollar_pnl": round(dollar_pnl, 2),
                    "equity": round(state["equity"], 2),
                })
                state["position"] = None
        # If not in a position, check for new signal
        if state["position"] is None and signal is not None:
            stop_dist = abs(signal["entry"] - signal["sl"])
            eq = state["equity"]
            qty = round(eq * RISK_PCT / stop_dist, 6)
            qty = max(0.0001, qty)
            notional = qty * signal["entry"]
            if notional > eq * LEV_CAP:
                qty = round(eq * LEV_CAP / signal["entry"], 6)
                qty = max(0.0001, qty)
                notional = qty * signal["entry"]
            state["position"] = {
                "entry_time": ts.strftime("%Y-%m-%d %H:%M:%S+00:00"),
                "direction": signal["direction"],
                "entry": signal["entry"],
                "sl": signal["sl"],
                "tp": signal["tp"],
                "notional": notional,
                "bar_idx": i,
            }


if __name__ == "__main__":
    # Call the parameter sweep main function
    import sys, inspect
    main_candidates = [(name, obj) for name, obj in globals().items() if callable(obj) and name == "main"]
    for name, obj in main_candidates:
        src = inspect.getsource(obj)
        if "PARAMETER SWEEP" in src or "Sweep:" in src:
            obj()
            sys.exit(0)
