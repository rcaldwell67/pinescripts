# APM v3.4  —  BTC-USD 15m  (shorts only, sweep-optimised params)
# Timeframe: 15m  |  Ticker: BTC-USD  |  Period: max

import subprocess, sys

import yfinance as yf
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings("ignore")

# ── Config (Pine Script defaults) ─────────────────────────────────────────────
TICKER      = "BTC-USD"
PERIOD      = "max"
INTERVAL    = "15m"
INITIAL_CAP = 10_000.0
COMM        = 0.0006      # 0.06% per side
RISK_PCT    = 0.03        # 3% equity per trade (matches Pine default)

EMA_FAST    = 21
EMA_MID     = 50
EMA_SLOW    = 200
ADX_THRESH  = 28
ADX_LEN     = 14
PB_PCT      = 0.15        # %
RSI_LEN     = 14
RSI_LO_L    = 42;  RSI_HI_L = 68
RSI_LO_S    = 32;  RSI_HI_S = 58
VOL_LEN     = 20
VOL_MULT    = 1.2
ATR_LEN     = 14
ATR_FLOOR   = 0.0015
PANIC_MULT  = 1.3
MIN_BODY    = 0.20        # fraction of ATR
SL_MULT     = 2.0
TP_MULT     = 2.0
TRAIL_ACT   = 1.5
TRAIL_DIST  = 1.5
TRADE_LONGS = True

# ── Download ──────────────────────────────────────────────────────────────────
print(f"Downloading {TICKER} {INTERVAL} period='{PERIOD}'...")
df = yf.download(TICKER, period=PERIOD, interval=INTERVAL,
                 auto_adjust=True, progress=False)
df.columns = df.columns.get_level_values(0)
df.index   = pd.to_datetime(df.index, utc=True)
df.sort_index(inplace=True)
print(f"Rows: {len(df)}  Range: {df.index[0]} → {df.index[-1]}\n")

# ── Indicators ────────────────────────────────────────────────────────────────
def ema(s, n):  return s.ewm(span=n, adjust=False).mean()
def sma(s, n):  return s.rolling(n).mean()

def rsi_calc(s, n):
    d  = s.diff()
    g  = d.clip(lower=0).rolling(n).mean()
    ls = (-d).clip(lower=0).rolling(n).mean()
    return 100 - 100 / (1 + g / ls.replace(0, np.nan))

def atr_calc(df, n):
    h, l, c = df["High"], df["Low"], df["Close"]
    tr = pd.concat([h - l,
                    (h - c.shift()).abs(),
                    (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def adx_calc(df, n):
    h, l, c = df["High"], df["Low"], df["Close"]
    up = h.diff(); dn = -l.diff()
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr  = pd.concat([h - l,
                     (h - c.shift()).abs(),
                     (l - c.shift()).abs()], axis=1).max(axis=1)
    at  = tr.rolling(n).mean()
    pdi = pd.Series(pdm, index=h.index).rolling(n).mean() / at * 100
    ndi = pd.Series(ndm, index=h.index).rolling(n).mean() / at * 100
    dx  = ((pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan) * 100)
    return pdi, ndi, dx.rolling(n).mean()

df["EMA_FAST"] = ema(df["Close"], EMA_FAST)
df["EMA_MID"]  = ema(df["Close"], EMA_MID)
df["EMA_SLOW"] = ema(df["Close"], EMA_SLOW)
df["RSI"]      = rsi_calc(df["Close"], RSI_LEN)
df["ATR"]      = atr_calc(df, ATR_LEN)
df["ATR_BL"]   = sma(df["ATR"], 60)
df["VOL_MA"]   = sma(df["Volume"], VOL_LEN)
df["DI_PLUS"], df["DI_MINUS"], df["ADX"] = adx_calc(df, ADX_LEN)
df.dropna(inplace=True)

# ── Signals (v3.2 — full v2 filter set) ─────────────────────────────────────────
full_bull   = (df["EMA_FAST"] > df["EMA_MID"]) & (df["EMA_MID"] > df["EMA_SLOW"])
full_bear   = (df["EMA_FAST"] < df["EMA_MID"]) & (df["EMA_MID"] < df["EMA_SLOW"])
slope_up    = df["EMA_FAST"] > df["EMA_FAST"].shift(3)
slope_down  = df["EMA_FAST"] < df["EMA_FAST"].shift(3)
rsi_rising  = df["RSI"] > df["RSI"].shift(1)
rsi_falling = df["RSI"] < df["RSI"].shift(1)
atr_ok      = df["ATR"] / df["Close"] >= ATR_FLOOR
pb_tol_up  = df["EMA_FAST"].shift(1) * (1.0 + PB_PCT / 100.0)
pb_tol_dn  = df["EMA_FAST"].shift(1) * (1.0 - PB_PCT / 100.0)
body_size  = (df["Close"] - df["Open"]).abs() / df["ATR"]

long_pb  = (df["Low"].shift(1)  <= pb_tol_up) & \
           (df["Close"] > df["EMA_FAST"]) & \
           (df["Close"] > df["Open"]) & \
           (body_size >= MIN_BODY)

short_pb = (df["High"].shift(1) >= pb_tol_dn) & \
           (df["Close"] < df["EMA_FAST"]) & \
           (df["Close"] < df["Open"]) & \
           (body_size >= MIN_BODY)

is_trending = df["ADX"]  > ADX_THRESH
is_panic    = df["ATR"]  > df["ATR_BL"] * PANIC_MULT
vol_ok      = df["Volume"] >= df["VOL_MA"] * VOL_MULT
rsi_long_ok = (df["RSI"] >= RSI_LO_L) & (df["RSI"] <= RSI_HI_L)
rsi_short_ok= (df["RSI"] >= RSI_LO_S) & (df["RSI"] <= RSI_HI_S)

long_sig  = (pd.Series(False, index=df.index) if not TRADE_LONGS else
             (~is_panic & is_trending & long_pb & full_bull & slope_up &
              rsi_rising & rsi_long_ok & vol_ok & atr_ok))
short_sig = (~is_panic & is_trending & short_pb & full_bear  & slope_down &
             rsi_falling & rsi_short_ok & vol_ok & atr_ok)

# ── Simulation ────────────────────────────────────────────────────────────────
equity = INITIAL_CAP
pos    = None
trades = []
alerts = []

def fmt_alert(lines):
    """Join alert lines the same way Pine's \\n separator works."""
    return "\n".join(lines)

def entry_alert(direction, row, ts, cl, av, atr_bl_v, sd, qty, equity_at_entry, df_row):
    sl  = cl - sd if direction == "long" else cl + sd
    tp  = cl + av * TP_MULT if direction == "long" else cl - av * TP_MULT
    rr  = TP_MULT / SL_MULT
    rsk = equity_at_entry * RISK_PCT
    dir_label = "LONG" if direction == "long" else "SHORT"
    rsi_range = f"{RSI_LO_L}-{RSI_HI_L}" if direction == "long" else f"{RSI_LO_S}-{RSI_HI_S}"
    rsi_dir   = "Rising" if direction == "long" else "Falling"
    stack     = "BULL" if direction == "long" else "BEAR"
    slope     = "UP"   if direction == "long" else "DOWN"
    trail_on  = av * TRAIL_ACT
    trail_dist_v = av * TRAIL_DIST
    sl_sign   = "-" if direction == "long" else "+"
    tp_sign   = "+" if direction == "long" else "-"
    trail_sign= "+" if direction == "long" else "-"
    body_v    = abs(float(df_row["Close"]) - float(df_row["Open"])) / av
    lines = [
        f"APM v3.4 | {dir_label} ENTRY | {TICKER} [{INTERVAL}]",
        f"Entry   : {cl:.2f}  |  Equity: ${equity_at_entry:.2f}",
        f"Stop    : {sl:.2f}  ({sl_sign}{sd:.2f} = ATR x{SL_MULT})",
        f"Target  : {tp:.2f}  ({tp_sign}{av * TP_MULT:.2f} = ATR x{TP_MULT})",
        f"R:R     : 1:{rr:.2f}  |  Risk: ${rsk:.2f} ({RISK_PCT*100:.1f}%)",
        f"Qty     : {qty:.4f}",
        f"ATR     : {av:.2f} ({av/cl*100:.3f}% of price)  |  Floor: {'OK' if av/cl >= ATR_FLOOR else 'FAIL'}",
        f"RSI     : {float(df_row['RSI']):.2f} [{rsi_range}]  |  Dir: {rsi_dir}",
        f"ADX     : {float(df_row['ADX']):.2f}  DI+: {float(df_row['DI_PLUS']):.2f}  DI-: {float(df_row['DI_MINUS']):.2f}  [min {ADX_THRESH}]",
        f"Vol/MA  : {float(df_row['Volume'])/float(df_row['VOL_MA']):.2f}x  [min {VOL_MULT}x]",
        f"Body    : {body_v:.3f}x ATR  [min {MIN_BODY}x]",
        f"EMA{EMA_FAST}/{EMA_MID}/{EMA_SLOW}: {float(df_row['EMA_FAST']):.2f}/{float(df_row['EMA_MID']):.2f}/{float(df_row['EMA_SLOW']):.2f}  Stack: {stack}  Slope: {slope}",
        f"Trail on: {trail_sign}{trail_on:.2f} (ATR x{TRAIL_ACT})  Dist: {trail_dist_v:.2f} (ATR x{TRAIL_DIST})",
        f"Time    : {ts}",
    ]
    return fmt_alert(lines)

def trail_alert(direction, best, entry, new_sl, old_sl, tp, runup, av, ts):
    dir_label = "LONG" if direction == "long" else "SHORT"
    dist_v    = av * TRAIL_DIST
    dist_sign = "-" if direction == "long" else "+"
    runup_pct = abs(runup) / entry * 100
    runup_sign= "+" if direction == "long" else "-"
    lines = [
        f"APM v3.4 | TRAIL STOP ACTIVATED | {TICKER} [{INTERVAL}]",
        f"Direction : {dir_label}",
        f"Best price: {best:.2f}  |  Entry: {entry:.2f}",
        f"Trail SL  : {new_sl:.2f}  (best {dist_sign} ATR x{TRAIL_DIST} = {dist_sign}{dist_v:.2f})",
        f"Prev SL   : {old_sl:.2f}  |  Target: {tp:.2f}",
        f"Runup     : {runup_sign}{abs(best - entry):.2f} ({runup_pct:.2f}%)",
        f"Time      : {ts}",
    ]
    return fmt_alert(lines)

def exit_alert(direction, ep, xp, pnl_dollar, comm_dollar, max_runup,
               bars_held, equity_after, closed_count, win_count, ts):
    dir_label = "LONG" if direction == "long" else "SHORT"
    result    = "WIN" if pnl_dollar >= 0 else "LOSS"
    mvpct     = ((xp - ep) / ep * 100) if direction == "long" else ((ep - xp) / ep * 100)
    wr        = f"{win_count/closed_count*100:.1f}%" if closed_count else "--"
    pnl_sign  = "+" if pnl_dollar >= 0 else ""
    mv_sign   = "+" if mvpct >= 0 else ""
    lines = [
        f"APM v3.4 | {dir_label} EXIT [{result}] | {TICKER} [{INTERVAL}]",
        f"Entry   : {ep:.2f}  ->  Exit: {xp:.2f}",
        f"Move    : {mv_sign}{mvpct:.2f}%",
        f"P&L     : {pnl_sign}{pnl_dollar:.2f} USD",
        f"Comm    : -{comm_dollar:.2f} USD",
        f"Max runup: {max_runup:.2f}",
        f"Bars    : {bars_held}",
        f"Equity  : ${equity_after:.2f}",
        f"Trades  : {closed_count}  |  Win rate: {wr}",
        f"Time    : {ts}",
    ]
    return fmt_alert(lines)

def panic_alert(started, atr_v, atr_bl_v, ts):
    state_label = "PANIC REGIME STARTED" if started else "PANIC REGIME CLEARED"
    status      = "New entries SUSPENDED" if started else "New entries RESUMED"
    lines = [
        f"APM v3.4 | {state_label} | {TICKER} [{INTERVAL}]",
        f"ATR     : {atr_v:.2f}  |  ATR baseline: {atr_bl_v:.2f}",
        f"Ratio   : {atr_v/atr_bl_v:.2f}x  [threshold: {PANIC_MULT}x]",
        f"Status  : {status}",
        f"Time    : {ts}",
    ]
    return fmt_alert(lines)

# track closed-trade counts for win rate in exit alert
win_count   = 0
closed_count= 0
prev_panic  = False
bar_index   = {ts: i for i, ts in enumerate(df.index)}

for ts, row in df.iterrows():
    cl = float(row["Close"]); hi = float(row["High"])
    lo = float(row["Low"]);   av = float(row["ATR"])
    atr_bl_v = float(row["ATR_BL"])
    cur_panic = bool(is_panic[ts])

    # ── Panic regime edge alerts ──────────────────────────────────────────
    if cur_panic and not prev_panic:
        alerts.append((ts, "PANIC_START", panic_alert(True,  av, atr_bl_v, ts)))
    elif not cur_panic and prev_panic:
        alerts.append((ts, "PANIC_CLEAR", panic_alert(False, av, atr_bl_v, ts)))
    prev_panic = cur_panic

    hit_tp = hit_sl = False
    exit_price = pnl = 0.0

    if pos is not None:
        d = pos["direction"]
        if d == "long":
            if hi > pos["best"]:
                pos["best"] = hi
                pos["max_runup"] = max(pos["max_runup"], hi - pos["entry"])
            if pos["best"] >= pos["entry"] + av * TRAIL_ACT:
                trail_sl = pos["best"] - av * TRAIL_DIST
                new_sl   = max(pos["sl"], trail_sl)
                if not pos["trail_active"]:
                    pos["trail_active"] = True
                    alerts.append((ts, "TRAIL", trail_alert(
                        d, pos["best"], pos["entry"], new_sl,
                        pos["sl"], pos["tp"],
                        pos["best"] - pos["entry"], av, ts)))
                pos["sl"] = new_sl
            hit_tp = hi >= pos["tp"]
            hit_sl = lo <= pos["sl"]
        else:
            if lo < pos["best"]:
                pos["best"] = lo
                pos["max_runup"] = max(pos["max_runup"], pos["entry"] - lo)
            if pos["best"] <= pos["entry"] - av * TRAIL_ACT:
                trail_sl = pos["best"] + av * TRAIL_DIST
                new_sl   = min(pos["sl"], trail_sl)
                if not pos["trail_active"]:
                    pos["trail_active"] = True
                    alerts.append((ts, "TRAIL", trail_alert(
                        d, pos["best"], pos["entry"], new_sl,
                        pos["sl"], pos["tp"],
                        pos["entry"] - pos["best"], av, ts)))
                pos["sl"] = new_sl
            hit_tp = lo <= pos["tp"]
            hit_sl = hi >= pos["sl"]

        if hit_tp or hit_sl:
            exit_price = pos["tp"] if hit_tp else pos["sl"]
            if d == "long":
                pnl = (exit_price - pos["entry"]) / pos["entry"]
            else:
                pnl = (pos["entry"] - exit_price) / pos["entry"]

    if hit_tp or hit_sl:
        comm_dollar = pos["notional"] * COMM * 2
        dollar_pnl  = pnl * pos["notional"] - comm_dollar
        equity     += dollar_pnl
        closed_count += 1
        if dollar_pnl > 0: win_count += 1
        bars_held = bar_index[ts] - bar_index[pos["entry_time"]]
        trades.append({
            "entry_time":  pos["entry_time"],
            "exit_time":   ts,
            "direction":   pos["direction"],
            "entry":       round(pos["entry"], 2),
            "exit":        round(exit_price, 2),
            "result":      "TP" if hit_tp else "SL",
            "pnl_pct":     round(pnl * 100, 3),
            "dollar_pnl":  round(dollar_pnl, 2),
            "equity":      round(equity, 2),
        })
        alerts.append((ts, "EXIT", exit_alert(
            pos["direction"], pos["entry"], exit_price,
            dollar_pnl, comm_dollar, pos["max_runup"],
            bars_held, equity, closed_count, win_count, ts)))
        pos = None

    if pos is None:
        sig = ("long" if bool(long_sig[ts]) else
               "short" if bool(short_sig[ts]) else None)
        if sig:
            sd       = av * SL_MULT
            notional = min(equity * RISK_PCT / sd * cl, equity * 5.0)
            sl       = cl - sd if sig == "long" else cl + sd
            tp       = cl + av * TP_MULT if sig == "long" else cl - av * TP_MULT
            qty      = notional / cl
            alerts.append((ts, "ENTRY", entry_alert(
                sig, row, ts, cl, av, atr_bl_v, sd, qty, equity, row)))
            pos = {
                "direction":    sig,
                "entry":        cl,
                "entry_time":   ts,
                "sl":           sl,
                "tp":           tp,
                "best":         cl,
                "notional":     notional,
                "trail_active": False,
                "max_runup":    0.0,
            }

# ── Stats ─────────────────────────────────────────────────────────────────────
tdf = pd.DataFrame(trades)
if tdf.empty:
    print("No trades generated.")
else:
    wins   = tdf[tdf["dollar_pnl"] > 0]
    losses = tdf[tdf["dollar_pnl"] <= 0]
    wr     = len(wins) / len(tdf) * 100
    ret    = (equity / INITIAL_CAP - 1) * 100
    pf     = (wins["dollar_pnl"].sum() / abs(losses["dollar_pnl"].sum())
              if not losses.empty and losses["dollar_pnl"].sum() != 0 else float("inf"))

    pk = INITIAL_CAP; mdd = 0.0
    for e in tdf["equity"]:
        if e > pk: pk = e
        dd = (e - pk) / pk * 100
        if dd < mdd: mdd = dd

    print("=" * 55)
    print(f"  APM v3.4  |  {TICKER} {INTERVAL}  (shorts only)")
    print("=" * 55)
    print(f"  Initial capital :  ${INITIAL_CAP:>10,.2f}")
    print(f"  Final equity    :  ${equity:>10,.2f}")
    print(f"  Net P&L         : ${equity-INITIAL_CAP:>+10,.2f}")
    print(f"  Return          :  {ret:>10.2f} %")
    print(f"  Max drawdown    :  {mdd:>10.2f} %")
    print(f"  Profit factor   :  {pf:>10.3f}")
    print("-" * 55)
    print(f"  Total trades    : {len(tdf):>6}")
    print(f"    Long  trades  : {(tdf['direction']=='long').sum():>6}")
    print(f"    Short trades  : {(tdf['direction']=='short').sum():>6}")
    print(f"  TP exits        : {(tdf['result']=='TP').sum():>6}")
    print(f"  SL exits        : {(tdf['result']=='SL').sum():>6}")
    print(f"  Win rate        :  {wr:>10.1f} %")
    print("=" * 55)
    for d in ["long", "short"]:
        sub  = tdf[tdf["direction"] == d]
        if sub.empty: continue
        sw   = sub[sub["dollar_pnl"] > 0]
        sl   = sub[sub["dollar_pnl"] <= 0]
        swr  = len(sw) / len(sub) * 100
        spf  = (sw["dollar_pnl"].sum() / abs(sl["dollar_pnl"].sum())
                if not sl.empty and sl["dollar_pnl"].sum() != 0 else float("inf"))
        print(f"  {d.upper():<6} trades={len(sub):>3}  WR={swr:.0f}%  "
              f"PF={spf:.3f}  net=${sub['dollar_pnl'].sum():+.2f}")

    out = f"apm_v3_trades_{TICKER.replace('-','').lower()}_{INTERVAL}.csv"
    # Ensure v2 schema column order
    tdf = tdf[["entry_time", "exit_time", "direction", "entry", "exit", "result", "pnl_pct", "dollar_pnl", "equity"]]
    tdf.to_csv(out, index=False)
    print(f"\nTrades saved → {out}")

# ── Write alerts log ─────────────────────────────────────────────────────────
alert_types = {"ENTRY": 0, "TRAIL": 0, "EXIT": 0, "PANIC_START": 0, "PANIC_CLEAR": 0}
SEP = "-" * 70
alert_out = f"apm_v3_alerts_{TICKER.replace('-','').lower()}_{INTERVAL}.txt"
with open(alert_out, "w") as f:
    for ts, atype, msg in alerts:
        alert_types[atype] += 1
        f.write(SEP + "\n")
        f.write(msg + "\n")
    f.write(SEP + "\n")

print(f"\nAlerts summary:")
for k, v in alert_types.items():
    print(f"  {k:<14}: {v}")
print(f"\nAlerts log  → {alert_out}")
print(f"Total alerts: {len(alerts)}")

# ── Print first 5 alerts as preview ──────────────────────────────────────────
print("\n" + "=" * 55)
print("  ALERT PREVIEW (first 5)")
print("=" * 55)
for ts, atype, msg in alerts[:5]:
    print(SEP)
    print(msg)

# ── Push to Google Sheets (optional — requires service_account.json) ──────────
from pathlib import Path as _Path
_SA_KEY = _Path(__file__).parent / "service_account.json"
if _SA_KEY.exists():
    from push_to_sheets import push_results
    push_results(
        trades       = trades,
        alerts       = alerts,
        symbol       = TICKER,
        interval     = INTERVAL,
        period       = PERIOD,
        initial_cap  = INITIAL_CAP,
        final_equity = equity,
    )
else:
    print(f"\nSkipping Google Sheets push — service_account.json not found.")
    print(f"See push_to_sheets.py for setup instructions.")

# --- Write final state for dashboard integration ---
import json
from pathlib import Path
state_out = Path("/home/rcaldwell67/repo/pinescripts/docs/data/btcusd/v3_paper_state.json")
final_state = {
    "position": None,
    "equity": round(equity, 2),
    "last_bar_ts": str(df.index[-1]) if not df.empty else None
}
with open(state_out, "w") as f:
    json.dump(final_state, f, indent=2)
print(f"\nFinal state written → {state_out}")
