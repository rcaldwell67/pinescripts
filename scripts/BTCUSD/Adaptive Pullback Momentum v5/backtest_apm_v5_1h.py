"""Faithful Python backtest of Adaptive Pullback Momentum v5.1
Timeframe : 1h BTC-USD, period="max" (~730 days via yfinance)
Commission : 0.06 % per side   Risk : 4 % equity / trade

v5.1 optimal parameters (7-phase sweep over BTC-USD 1h max history):
  Longs only | ADX>35 | SL×1.5 | TP×1.5 | Trail act×2.5 | Trail dist×0.5
  Vol×1.5 | Body×0.20 | ATR floor 0.30% | EMA slope (3-bar) | RSI 42-72
  Result: +6.31%, PF=3.682, WR=83.3%, 12 trades, MaxDD=-1.18%
"""

import pandas as pd
import numpy as np
import yfinance as yf
import warnings
warnings.filterwarnings("ignore")

# ── Configuration ──────────────────────────────────────────────────────────────
TICKER     = "BTC-USD"
INTERVAL   = "1h"
PERIOD     = "max"          # ~730 days for 1h on yfinance
INIT_CAP   = 10_000.0
COMMISSION = 0.0006         # 0.06 % per side
RISK_PCT   = 0.04           # 4 % equity per trade; validated at +26.99% on current BTC window

# ── Strategy defaults (v5.1 — sweep-optimised) ────────────────────────────────
EMA_FAST_LEN = 21
EMA_MID_LEN  = 50
EMA_SLOW_LEN = 200
ADX_LEN      = 14
ADX_THRESH   = 35.0
PB_PCT       = 0.10         # % pullback tolerance
VOL_MA_LEN   = 20
VOL_MULT     = 1.5
MIN_BODY     = 0.20         # minimum body in ATR units
PANIC_MULT   = 1.5
ATR_LEN      = 14
ATR_BL_LEN   = 50          # ATR baseline (SMA of ATR)
SL_MULT      = 1.5
TP_MULT      = 1.5
TRAIL_ACT    = 2.5
TRAIL_DIST   = 0.5
RSI_LEN      = 14
RSI_LO_L     = 42.0; RSI_HI_L = 72.0   # long RSI band
RSI_LO_S     = 32.0; RSI_HI_S = 58.0   # short RSI band (unused — shorts off)
TRADE_LONGS  = True
TRADE_SHORTS = False
ATR_FLOOR    = 0.0030       # 0.30% of price — floors ATR for sizing
USE_EMA_SLOPE = True        # require EMA-fast rising (3-bar)

# ── Data download ──────────────────────────────────────────────────────────────
print(f"Downloading {TICKER} {INTERVAL} {PERIOD} …")
raw = yf.download(TICKER, period=PERIOD, interval=INTERVAL,
                  auto_adjust=True, progress=False)
raw.columns = [c[0] if isinstance(c, tuple) else c for c in raw.columns]
df = raw[["Open", "High", "Low", "Close", "Volume"]].copy().dropna()
df.index = pd.to_datetime(df.index)
print(f"  Rows: {len(df)}  |  {df.index[0].date()} → {df.index[-1].date()}")

# ── Indicators ─────────────────────────────────────────────────────────────────
def ema(s, n): return s.ewm(span=n, adjust=False).mean()

def rsi(s, n=14):
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    dn = (-d).clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))

def true_range(h, l, pc):
    return pd.concat([h - l,
                      (h - pc).abs(),
                      (l - pc).abs()], axis=1).max(axis=1)

def atr_series(h, l, c, n=14):
    tr = true_range(h, l, c.shift(1))
    return tr.ewm(alpha=1/n, adjust=False).mean()

def adx_series(h, l, c, n=14):
    up   = h.diff()
    dn   = -l.diff()
    pdm  = up.where((up > dn) & (up > 0), 0.0)
    ndm  = dn.where((dn > up) & (dn > 0), 0.0)
    tr14 = atr_series(h, l, c, n)
    pdi  = 100 * pdm.ewm(alpha=1/n, adjust=False).mean() / tr14.replace(0, np.nan)
    ndi  = 100 * ndm.ewm(alpha=1/n, adjust=False).mean() / tr14.replace(0, np.nan)
    dx   = (100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan))
    adx_ = dx.ewm(alpha=1/n, adjust=False).mean()
    return adx_

df["EMA_F"]  = ema(df["Close"], EMA_FAST_LEN)
df["EMA_M"]  = ema(df["Close"], EMA_MID_LEN)
df["EMA_S"]  = ema(df["Close"], EMA_SLOW_LEN)
df["ATR"]    = atr_series(df["High"], df["Low"], df["Close"], ATR_LEN)
df["ATR_BL"] = df["ATR"].rolling(ATR_BL_LEN).mean()
df["ADX"]    = adx_series(df["High"], df["Low"], df["Close"], ADX_LEN)
df["RSI"]    = rsi(df["Close"], RSI_LEN)
df["VOL_MA"] = df["Volume"].rolling(VOL_MA_LEN).mean()

# Body size in ATR units
df["BODY"] = (df["Close"] - df["Open"]).abs() / df["ATR"].replace(0, np.nan)
# EMA slope (3-bar)
df["EMA_F_SLOPE"] = df["EMA_F"] - df["EMA_F"].shift(3)
# Pullback conditions (use previous bar's low/high vs previous bar's EMA_F)
pb_tol_up = df["EMA_F"].shift(1) * (1.0 + PB_PCT / 100.0)
pb_tol_dn = df["EMA_F"].shift(1) * (1.0 - PB_PCT / 100.0)

long_pb  = (df["Low"].shift(1) <= pb_tol_up) & (df["Close"] > df["EMA_F"]) & \
           (df["Close"] > df["Open"]) & (df["BODY"] >= MIN_BODY)
short_pb = (df["High"].shift(1) >= pb_tol_dn) & (df["Close"] < df["EMA_F"]) & \
           (df["Close"] < df["Open"]) & (df["BODY"] >= MIN_BODY)

is_trending = df["ADX"] > ADX_THRESH
is_panic    = df["ATR"] > df["ATR_BL"] * PANIC_MULT

long_entry = (
    TRADE_LONGS &
    long_pb &
    (df["Close"] > df["EMA_S"]) &
    (df["EMA_F"] > df["EMA_M"]) &
    (~USE_EMA_SLOPE | (df["EMA_F_SLOPE"] > 0)) &
    (df["RSI"] >= RSI_LO_L) & (df["RSI"] <= RSI_HI_L) &
    (df["Volume"] >= df["VOL_MA"] * VOL_MULT) &
    is_trending & ~is_panic
)
short_entry = (
    TRADE_SHORTS &
    short_pb &
    (df["Close"] < df["EMA_S"]) &
    (df["EMA_F"] < df["EMA_M"]) &
    (~USE_EMA_SLOPE | (df["EMA_F_SLOPE"] < 0)) &
    (df["RSI"] >= RSI_LO_S) & (df["RSI"] <= RSI_HI_S) &
    (df["Volume"] >= df["VOL_MA"] * VOL_MULT) &
    is_trending & ~is_panic
)

# ── Bar-by-bar simulation ───────────────────────────────────────────────────────

# ── Alert helper functions ─────────────────────────────────────────────────────
def _al(lines): return "\n".join(lines)

def entry_alert(direction, ts, cl, av, atr_eff_v, atr_bl_v, sd, qty, equity_at_entry, row):
    sl  = cl - sd if direction == "long" else cl + sd
    tp  = cl + atr_eff_v * TP_MULT if direction == "long" else cl - atr_eff_v * TP_MULT
    rr  = TP_MULT / SL_MULT
    rsk = equity_at_entry * RISK_PCT
    dl  = "LONG" if direction == "long" else "SHORT"
    rr_range = f"{RSI_LO_L}-{RSI_HI_L}" if direction == "long" else f"{RSI_LO_S}-{RSI_HI_S}"
    rdir = "Rising" if direction == "long" else "Falling"
    stk  = "BULL" if direction == "long" else "BEAR"
    slp  = "UP"   if direction == "long" else "DOWN"
    ss   = "-" if direction == "long" else "+"
    ts_  = "+" if direction == "long" else "-"
    body_v = abs(float(row["Close"]) - float(row["Open"])) / av
    atr_fl = "OK" if av / cl >= ATR_FLOOR else "FAIL"
    return _al([
        f"APM v5.1 | {dl} ENTRY | {TICKER} [{INTERVAL}]",
        f"Entry   : {cl:.2f}  |  Equity: ${equity_at_entry:.2f}",
        f"Stop    : {sl:.2f}  ({ss}{sd:.2f} = ATR x{SL_MULT})",
        f"Target  : {tp:.2f}  ({ts_}{atr_eff_v*TP_MULT:.2f} = ATR x{TP_MULT})",
        f"R:R     : 1:{rr:.2f}  |  Risk: ${rsk:.2f} ({RISK_PCT*100:.1f}%)",
        f"Qty     : {qty:.4f}",
        f"ATR     : {av:.2f} ({av/cl*100:.3f}% of price)  |  Floor: {atr_fl}",
        f"RSI     : {float(row['RSI']):.2f} [{rr_range}]  |  Dir: {rdir}",
        f"ADX     : {float(row['ADX']):.2f}  DI+: n/a  DI-: n/a  [min {ADX_THRESH}]",
        f"Vol/MA  : {float(row['Volume'])/float(row['VOL_MA']):.2f}x  [min {VOL_MULT}x]",
        f"Body    : {body_v:.3f}x ATR  [min {MIN_BODY}x]",
        f"EMA{EMA_FAST_LEN}/{EMA_MID_LEN}/{EMA_SLOW_LEN}: {float(row['EMA_F']):.2f}/{float(row['EMA_M']):.2f}/{float(row['EMA_S']):.2f}  Stack: {stk}  Slope: {slp}",
        f"Trail on: {ts_}{atr_eff_v*TRAIL_ACT:.2f} (ATR x{TRAIL_ACT})  Dist: {atr_eff_v*TRAIL_DIST:.2f} (ATR x{TRAIL_DIST})",
        f"Time    : {ts}",
    ])

def trail_alert(direction, best, entry, new_sl, old_sl, tp, av, ts):
    dl   = "LONG" if direction == "long" else "SHORT"
    ds   = "-" if direction == "long" else "+"
    runup = abs(best - entry)
    rpct  = runup / entry * 100
    rs    = "+" if direction == "long" else "-"
    return _al([
        f"APM v5.1 | TRAIL STOP ACTIVATED | {TICKER} [{INTERVAL}]",
        f"Direction : {dl}",
        f"Best price: {best:.2f}  |  Entry: {entry:.2f}",
        f"Trail SL  : {new_sl:.2f}  (best {ds} ATR x{TRAIL_DIST} = {ds}{av*TRAIL_DIST:.2f})",
        f"Prev SL   : {old_sl:.2f}  |  Target: {tp:.2f}",
        f"Runup     : {rs}{runup:.2f} ({rpct:.2f}%)",
        f"Time      : {ts}",
    ])

def exit_alert(direction, ep, xp, pnl_dollar, comm_dollar, max_runup,
               bars_held, equity_after, closed_count, win_count, ts):
    dl   = "LONG" if direction == "long" else "SHORT"
    res  = "WIN" if pnl_dollar >= 0 else "LOSS"
    mv   = ((xp-ep)/ep*100) if direction=="long" else ((ep-xp)/ep*100)
    wr   = f"{win_count/closed_count*100:.1f}%" if closed_count else "--"
    ps   = "+" if pnl_dollar >= 0 else ""
    ms   = "+" if mv >= 0 else ""
    return _al([
        f"APM v5.1 | {dl} EXIT [{res}] | {TICKER} [{INTERVAL}]",
        f"Entry   : {ep:.2f}  ->  Exit: {xp:.2f}",
        f"Move    : {ms}{mv:.2f}%",
        f"P&L     : {ps}{pnl_dollar:.2f} USD",
        f"Comm    : -{comm_dollar:.2f} USD",
        f"Max runup: {max_runup:.2f}",
        f"Bars    : {bars_held}",
        f"Equity  : ${equity_after:.2f}",
        f"Trades  : {closed_count}  |  Win rate: {wr}",
        f"Time    : {ts}",
    ])

def panic_alert(started, atr_v, atr_bl_v, ts):
    lbl    = "PANIC REGIME STARTED" if started else "PANIC REGIME CLEARED"
    status = "New entries SUSPENDED" if started else "New entries RESUMED"
    return _al([
        f"APM v5.1 | {lbl} | {TICKER} [{INTERVAL}]",
        f"ATR     : {atr_v:.2f}  |  ATR baseline: {atr_bl_v:.2f}",
        f"Ratio   : {atr_v/atr_bl_v:.2f}x  [threshold: {PANIC_MULT}x]",
        f"Status  : {status}",
        f"Time    : {ts}",
    ])

# ── Simulation state ─────────────────────────────────────────────────────────────
equity     = INIT_CAP
in_trade   = False
direction  = None   # "long" | "short"
entry_px   = 0.0
sl_price   = 0.0
tp_price   = 0.0
best_price = 0.0
entry_atr  = 0.0

tradesdict   = []
alerts       = []
equity_curve = [equity]
win_count    = 0
closed_count = 0
prev_panic   = False
trail_active_f = False  # trail-alert one-shot per trade
max_runup_f    = 0.0
bar_index_map  = {t: i for i, t in enumerate(df.index)}

l_entry  = long_entry.values
s_entry  = short_entry.values
o        = df["Open"].values
h        = df["High"].values
l_       = df["Low"].values
c        = df["Close"].values
atr_v    = df["ATR"].values
idx      = df.index

COMM = COMMISSION

for i in range(EMA_SLOW_LEN + 50, len(df)):
    curr_atr = atr_v[i]
    if np.isnan(curr_atr) or curr_atr == 0:
        equity_curve.append(equity)
        continue

    # Apply ATR floor
    eff_atr = max(curr_atr, c[i] * ATR_FLOOR)
    row     = df.iloc[i]
    cur_ts  = idx[i]
    cur_panic = bool(is_panic.iloc[i])

    # panic edge alerts
    if cur_panic and not prev_panic:
        alerts.append((cur_ts, "PANIC_START", panic_alert(True,  curr_atr, float(df["ATR_BL"].iloc[i]), cur_ts)))
    elif not cur_panic and prev_panic:
        alerts.append((cur_ts, "PANIC_CLEAR", panic_alert(False, curr_atr, float(df["ATR_BL"].iloc[i]), cur_ts)))
    prev_panic = cur_panic

    exited = False

    if in_trade:
        # Update best price
        if direction == "long":
            if h[i] > best_price:
                best_price = h[i]
                max_runup_f = max(max_runup_f, h[i] - entry_px)
            # Activate trailing stop
            if best_price >= entry_px + entry_atr * TRAIL_ACT:
                trail_sl = best_price - entry_atr * TRAIL_DIST
                if trail_sl > sl_price:
                    if not trail_active_f:
                        trail_active_f = True
                        alerts.append((cur_ts, "TRAIL", trail_alert(
                            "long", best_price, entry_px, trail_sl,
                            sl_price, tp_price, entry_atr, cur_ts)))
                    sl_price = trail_sl

            # Check SL (low touches or crosses sl_price)
            if l_[i] <= sl_price:
                exit_px  = min(o[i], sl_price)   # gap-down fills at open
                pnl      = (exit_px - entry_px) * qty
                comm     = (entry_px + exit_px) * qty * COMM
                net_pnl  = pnl - comm
                equity  += net_pnl
                closed_count += 1
                if net_pnl > 0: win_count += 1
                bars_h = bar_index_map[cur_ts] - bar_index_map[entry_time]
                tradesdict.append({"entry_time": entry_time, "exit_time": cur_ts,
                                "direction": "long", "entry": entry_px,
                                "exit": exit_px, "pnl": net_pnl, "equity": equity,
                                "exit_reason": "SL"})
                alerts.append((cur_ts, "EXIT", exit_alert(
                    "long", entry_px, exit_px, net_pnl, comm, max_runup_f,
                    bars_h, equity, closed_count, win_count, cur_ts)))
                in_trade = False; exited = True

            elif not exited and h[i] >= tp_price:
                exit_px  = max(o[i], tp_price)
                pnl      = (exit_px - entry_px) * qty
                comm     = (entry_px + exit_px) * qty * COMM
                net_pnl  = pnl - comm
                equity  += net_pnl
                closed_count += 1
                if net_pnl > 0: win_count += 1
                bars_h = bar_index_map[cur_ts] - bar_index_map[entry_time]
                tradesdict.append({"entry_time": entry_time, "exit_time": cur_ts,
                                "direction": "long", "entry": entry_px,
                                "exit": exit_px, "pnl": net_pnl, "equity": equity,
                                "exit_reason": "TP"})
                alerts.append((cur_ts, "EXIT", exit_alert(
                    "long", entry_px, exit_px, net_pnl, comm, max_runup_f,
                    bars_h, equity, closed_count, win_count, cur_ts)))
                in_trade = False; exited = True

        else:  # short
            if l_[i] < best_price:
                best_price = l_[i]
                max_runup_f = max(max_runup_f, entry_px - l_[i])
            if best_price <= entry_px - entry_atr * TRAIL_ACT:
                trail_sl = best_price + entry_atr * TRAIL_DIST
                if trail_sl < sl_price:
                    if not trail_active_f:
                        trail_active_f = True
                        alerts.append((cur_ts, "TRAIL", trail_alert(
                            "short", best_price, entry_px, trail_sl,
                            sl_price, tp_price, entry_atr, cur_ts)))
                    sl_price = trail_sl

            if h[i] >= sl_price:
                exit_px  = max(o[i], sl_price)
                pnl      = (entry_px - exit_px) * qty
                comm     = (entry_px + exit_px) * qty * COMM
                net_pnl  = pnl - comm
                equity  += net_pnl
                closed_count += 1
                if net_pnl > 0: win_count += 1
                bars_h = bar_index_map[cur_ts] - bar_index_map[entry_time]
                tradesdict.append({"entry_time": entry_time, "exit_time": cur_ts,
                                "direction": "short", "entry": entry_px,
                                "exit": exit_px, "pnl": net_pnl, "equity": equity,
                                "exit_reason": "SL"})
                alerts.append((cur_ts, "EXIT", exit_alert(
                    "short", entry_px, exit_px, net_pnl, comm, max_runup_f,
                    bars_h, equity, closed_count, win_count, cur_ts)))
                in_trade = False; exited = True

            elif not exited and l_[i] <= tp_price:
                exit_px  = min(o[i], tp_price)
                pnl      = (entry_px - exit_px) * qty
                comm     = (entry_px + exit_px) * qty * COMM
                net_pnl  = pnl - comm
                equity  += net_pnl
                closed_count += 1
                if net_pnl > 0: win_count += 1
                bars_h = bar_index_map[cur_ts] - bar_index_map[entry_time]
                tradesdict.append({"entry_time": entry_time, "exit_time": cur_ts,
                                "direction": "short", "entry": entry_px,
                                "exit": exit_px, "pnl": net_pnl, "equity": equity,
                                "exit_reason": "TP"})
                alerts.append((cur_ts, "EXIT", exit_alert(
                    "short", entry_px, exit_px, net_pnl, comm, max_runup_f,
                    bars_h, equity, closed_count, win_count, cur_ts)))
                in_trade = False; exited = True

    if not in_trade:
        if l_entry[i]:
            stop_dist     = eff_atr * SL_MULT
            entry_px      = c[i]
            sl_price      = entry_px - stop_dist
            tp_price      = entry_px + eff_atr * TP_MULT
            entry_atr     = eff_atr
            best_price    = entry_px
            qty           = equity * RISK_PCT / stop_dist
            entry_time    = cur_ts
            trail_active_f= False
            max_runup_f   = 0.0
            direction     = "long"; in_trade = True
            alerts.append((cur_ts, "ENTRY", entry_alert(
                "long", cur_ts, c[i], curr_atr, eff_atr,
                float(df["ATR_BL"].iloc[i]), stop_dist, qty, equity, row)))
        elif s_entry[i]:
            stop_dist     = eff_atr * SL_MULT
            entry_px      = c[i]
            sl_price      = entry_px + stop_dist
            tp_price      = entry_px - eff_atr * TP_MULT
            entry_atr     = eff_atr
            best_price    = entry_px
            qty           = equity * RISK_PCT / stop_dist
            entry_time    = cur_ts
            trail_active_f= False
            max_runup_f   = 0.0
            direction     = "short"; in_trade = True
            alerts.append((cur_ts, "ENTRY", entry_alert(
                "short", cur_ts, c[i], curr_atr, eff_atr,
                float(df["ATR_BL"].iloc[i]), stop_dist, qty, equity, row)))

    equity_curve.append(equity)

# ── Results ────────────────────────────────────────────────────────────────────
trades = tradesdict
tdf = pd.DataFrame(trades)
print(f"\n{'='*55}")
print(f"  APM v5.1 (sweep-optimised)  |  {TICKER} {INTERVAL}  |  Longs Only")
print(f"{'='*55}")

if tdf.empty:
    print("  No trades generated.")
else:
    wins    = tdf[tdf["pnl"] > 0]
    losses  = tdf[tdf["pnl"] <= 0]
    total   = len(tdf)
    wr      = len(wins) / total * 100
    net_pnl = tdf["pnl"].sum()
    net_pct = net_pnl / INIT_CAP * 100
    gp      = wins["pnl"].sum()
    gl      = abs(losses["pnl"].sum())
    pf      = gp / gl if gl > 0 else float("inf")
    avg_w   = wins["pnl"].mean() if not wins.empty else 0
    avg_l   = losses["pnl"].mean() if not losses.empty else 0

    eq_arr  = np.array(equity_curve)
    roll_max = np.maximum.accumulate(eq_arr)
    dd       = (eq_arr - roll_max) / roll_max * 100
    max_dd   = dd.min()

    longs_df  = tdf[tdf["direction"] == "long"]
    shorts_df = tdf[tdf["direction"] == "short"]

    print(f"  Period   : {df.index[0].date()} → {df.index[-1].date()}")
    print(f"  Trades   : {total}  (L={len(longs_df)}, S={len(shorts_df)})")
    print(f"  Win rate : {wr:.1f}%  ({len(wins)}W / {len(losses)}L)")
    print(f"  Net P&L  : ${net_pnl:+.2f}  ({net_pct:+.2f}%)")
    print(f"  Prof Fac : {pf:.3f}")
    print(f"  Avg Win  : ${avg_w:+.2f}   Avg Loss: ${avg_l:+.2f}")
    print(f"  Max DD   : {max_dd:.2f}%")
    print(f"  Final Eq : ${equity:,.2f}")

    if not longs_df.empty:
        lw = (longs_df["pnl"] > 0).sum()
        print(f"\n  Longs : {len(longs_df)} trades  WR={lw/len(longs_df)*100:.1f}%  "
              f"Net=${longs_df['pnl'].sum():+.2f}")
    if not shorts_df.empty:
        sw = (shorts_df["pnl"] > 0).sum()
        print(f"  Shorts: {len(shorts_df)} trades  WR={sw/len(shorts_df)*100:.1f}%  "
              f"Net=${shorts_df['pnl'].sum():+.2f}")

    print(f"\n  Exit breakdown:")
    print(tdf["exit_reason"].value_counts().to_string())

    # --- Canonical v4 schema ---
    tdf = tdf.rename(columns={"pnl": "dollar_pnl", "exit_reason": "result"}).copy()
    tdf["equity_before"] = tdf["equity"] - tdf["dollar_pnl"]
    tdf["pnl_pct"] = (tdf["dollar_pnl"] / tdf["equity_before"] * 100).round(3)
    tdf = tdf[["entry_time", "exit_time", "direction", "entry", "exit", "result", "pnl_pct", "dollar_pnl", "equity"]]
    tdf.to_csv("apm_v5_trades_btcusd_1h.csv", index=False)
    print(f"\n  Saved → apm_v5_trades_btcusd_1h.csv")

    # ── Dashboard export ──────────────────────────────────────────────────────
    from pathlib import Path as _Path
    _dash_out = _Path(__file__).resolve().parent.parent.parent.parent / "docs" / "data" / "btcusd" / "v5_trades.csv"
    dash = tdf.rename(columns={"pnl": "dollar_pnl"}).copy()
    dash["equity_before"] = dash["equity"] - dash["dollar_pnl"]
    dash["pnl_pct"] = (dash["dollar_pnl"] / dash["equity_before"] * 100).round(3)
    dash = dash[["entry_time","exit_time","direction","entry","exit","exit_reason","pnl_pct","dollar_pnl","equity"]]
    dash.to_csv(_dash_out, index=False)
    print(f"  Saved → {_dash_out.relative_to(_Path(__file__).resolve().parent.parent.parent.parent)}")

print(f"{'='*55}")

# ── Write alert log ───────────────────────────────────────────────────────────────
SEP = "-" * 70
alert_out   = f"apm_v5_alerts_{TICKER.replace('-','').lower()}_{INTERVAL}.txt"
alert_types = {t: 0 for t in ["ENTRY","TRAIL","EXIT","PANIC_START","PANIC_CLEAR"]}
with open(alert_out, "w") as f:
    for ts, atype, msg in alerts:
        alert_types[atype] += 1
        f.write(SEP + "\n" + msg + "\n")
    f.write(SEP + "\n")

print(f"\nAlerts summary:")
for k, v in alert_types.items():
    print(f"  {k:<14}: {v}")
print(f"Total alerts: {len(alerts)}")
print(f"Alerts log  → {alert_out}")

print("\n" + "=" * 55)
print("  ALERT PREVIEW (first 3 non-panic)")
print("=" * 55)
shown = 0
for ts, atype, msg in alerts:
    if atype in ("ENTRY", "TRAIL", "EXIT"):
        print(SEP); print(msg)
        shown += 1
        if shown >= 3: break

# ── Google Sheets push (requires service_account.json) ─────────────────────
from pathlib import Path as _Path
_SA_KEY = _Path(__file__).parent / "service_account.json"
if _SA_KEY.exists():
    from push_to_sheets_v5 import push_results
    push_results(
        trades       = trades,
        alerts       = alerts,
        symbol       = TICKER,
        interval     = INTERVAL,
        period       = PERIOD,
        initial_cap  = INIT_CAP,
        final_equity = equity,
    )
else:
    print(f"\nSkipping Google Sheets push — service_account.json not found.")
    print(f"See push_to_sheets_v5.py for setup instructions.")
