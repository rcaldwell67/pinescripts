"""Faithful Python backtest of Adaptive Pullback Momentum v6.1
Timeframe : 1D BTC-USD, period="max" (~11 years via yfinance, back to 2014)
Commission : 0.06% per side   Risk : 1% equity / trade
"""

import pandas as pd
import numpy as np
import yfinance as yf
import warnings
warnings.filterwarnings("ignore")

# ── Configuration ──────────────────────────────────────────────────────────────
TICKER     = "BTC-USD"
INTERVAL   = "1d"
PERIOD     = "max"
INIT_CAP   = 10_000.0
COMMISSION = 0.0006
RISK_PCT   = 0.01

# ── Strategy defaults (v6.1 sweep-optimised) ────────────────────────────────
EMA_FAST_LEN = 21
EMA_MID_LEN  = 50
EMA_SLOW_LEN = 200
ADX_LEN      = 14
ADX_THRESH   = 28.0
PB_PCT       = 0.15
VOL_MA_LEN   = 20
VOL_MULT     = 1.0
MIN_BODY     = 0.30
PANIC_MULT   = 2.0
ATR_LEN      = 14
ATR_BL_LEN   = 60
SL_MULT      = 2.0
TP_MULT      = 1.0
TRAIL_ACT    = 2.0
TRAIL_DIST   = 0.4
RSI_LEN      = 14
RSI_LO_L     = 42.0; RSI_HI_L = 72.0
RSI_LO_S     = 32.0; RSI_HI_S = 58.0
TRADE_LONGS  = True
TRADE_SHORTS = True
ATR_FLOOR    = 0.0

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
    u = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    v = (-d).clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100 / (1 + u / v.replace(0, np.nan))

def atr_series(h, l, c, n=14):
    tr = pd.concat([h - l,
                    (h - c.shift(1)).abs(),
                    (l - c.shift(1)).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False).mean()

def adx_series(h, l, c, n=14):
    up = h.diff(); dn = -l.diff()
    pdm = up.where((up > dn) & (up > 0), 0.0)
    ndm = dn.where((dn > up) & (dn > 0), 0.0)
    tr14 = atr_series(h, l, c, n)
    pdi = 100 * pdm.ewm(alpha=1/n, adjust=False).mean() / tr14.replace(0, np.nan)
    ndi = 100 * ndm.ewm(alpha=1/n, adjust=False).mean() / tr14.replace(0, np.nan)
    dx  = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
    return dx.ewm(alpha=1/n, adjust=False).mean()

def di_series(h, l, c, n=14):
    up = h.diff(); dn = -l.diff()
    pdm = up.where((up > dn) & (up > 0), 0.0)
    ndm = dn.where((dn > up) & (dn > 0), 0.0)
    tr14 = atr_series(h, l, c, n)
    pdi = 100 * pdm.ewm(alpha=1/n, adjust=False).mean() / tr14.replace(0, np.nan)
    ndi = 100 * ndm.ewm(alpha=1/n, adjust=False).mean() / tr14.replace(0, np.nan)
    return pdi, ndi

df["EMA_F"]  = ema(df["Close"], EMA_FAST_LEN)
df["EMA_M"]  = ema(df["Close"], EMA_MID_LEN)
df["EMA_S"]  = ema(df["Close"], EMA_SLOW_LEN)
df["ATR"]    = atr_series(df["High"], df["Low"], df["Close"], ATR_LEN)
df["ATR_BL"] = df["ATR"].rolling(ATR_BL_LEN).mean()
df["ADX"]       = adx_series(df["High"], df["Low"], df["Close"], ADX_LEN)
df["DI_PLUS"], df["DI_MINUS"] = di_series(df["High"], df["Low"], df["Close"], ADX_LEN)
df["RSI"]       = rsi(df["Close"], RSI_LEN)
df["VOL_MA"] = df["Volume"].rolling(VOL_MA_LEN).mean()
df["BODY"]   = (df["Close"] - df["Open"]).abs() / df["ATR"].replace(0, np.nan)

pb_tol_up = df["EMA_F"].shift(1) * (1.0 + PB_PCT / 100.0)
pb_tol_dn = df["EMA_F"].shift(1) * (1.0 - PB_PCT / 100.0)

long_pb  = (df["Low"].shift(1) <= pb_tol_up) & (df["Close"] > df["EMA_F"]) & \
           (df["Close"] > df["Open"]) & (df["BODY"] >= MIN_BODY)
short_pb = (df["High"].shift(1) >= pb_tol_dn) & (df["Close"] < df["EMA_F"]) & \
           (df["Close"] < df["Open"]) & (df["BODY"] >= MIN_BODY)

is_trending = df["ADX"] > ADX_THRESH
is_panic    = df["ATR"] > df["ATR_BL"] * PANIC_MULT

long_entry = (
    TRADE_LONGS & long_pb &
    (df["Close"] > df["EMA_S"]) & (df["EMA_F"] > df["EMA_M"]) &
    (df["RSI"] >= RSI_LO_L) & (df["RSI"] <= RSI_HI_L) &
    (df["Volume"] >= df["VOL_MA"] * VOL_MULT) &
    is_trending & ~is_panic
)
short_entry = (
    TRADE_SHORTS & short_pb &
    (df["Close"] < df["EMA_S"]) & (df["EMA_F"] < df["EMA_M"]) &
    (df["RSI"] >= RSI_LO_S) & (df["RSI"] <= RSI_HI_S) &
    (df["Volume"] >= df["VOL_MA"] * VOL_MULT) &
    is_trending & ~is_panic
)

# ── Alert helpers ─────────────────────────────────────────────────────────────
def _al(): return "-" * 70

def entry_alert(direction, ts, cl, av, sd, qty, equity_at_entry, row):
    rr       = TP_MULT / SL_MULT
    risk     = equity_at_entry * RISK_PCT
    atr_p    = av / cl * 100
    vol      = float(row["Volume"]) / float(row["VOL_MA"])
    body     = float(row["BODY"])
    ef, em, es = float(row["EMA_F"]), float(row["EMA_M"]), float(row["EMA_S"])
    rsi_v    = float(row["RSI"])
    adx_v    = float(row["ADX"])
    dip      = float(row["DI_PLUS"])
    dim      = float(row["DI_MINUS"])
    if direction == "long":
        stop   = cl - sd;  tgt = cl + av * TP_MULT
        stop_s = f"(-{sd:.2f} = ATR x{SL_MULT})"
        tgt_s  = f"(+{av * TP_MULT:.2f} = ATR x{TP_MULT})"
        tsign  = "+"; rsi_range = f"{RSI_LO_L}-{RSI_HI_L}"
        rsi_dir = "Rising"; stack = "BULL"
    else:
        stop   = cl + sd;  tgt = cl - av * TP_MULT
        stop_s = f"(+{sd:.2f} = ATR x{SL_MULT})"
        tgt_s  = f"(-{av * TP_MULT:.2f} = ATR x{TP_MULT})"
        tsign  = "-"; rsi_range = f"{RSI_LO_S}-{RSI_HI_S}"
        rsi_dir = "Falling"; stack = "BEAR"
    return (
        f"APM v6.1 | {direction.upper()} ENTRY | BTC-USD [1D]\n"
        f"Entry   : {cl:.2f}  |  Equity: ${equity_at_entry:.2f}\n"
        f"Stop    : {stop:.2f}  {stop_s}\n"
        f"Target  : {tgt:.2f}  {tgt_s}\n"
        f"R:R     : 1:{rr:.2f}  |  Risk: ${risk:.2f} ({RISK_PCT*100:.1f}%)\n"
        f"Qty     : {qty:.4f}\n"
        f"ATR     : {av:.2f} ({atr_p:.3f}% of price)\n"
        f"RSI     : {rsi_v:.2f} [{rsi_range}]  |  Dir: {rsi_dir}\n"
        f"ADX     : {adx_v:.2f}  DI+: {dip:.2f}  DI-: {dim:.2f}  [min {ADX_THRESH}]\n"
        f"Vol/MA  : {vol:.2f}x  [min {VOL_MULT}x]\n"
        f"Body    : {body:.3f}x ATR  [min {MIN_BODY}x]\n"
        f"EMA21/50/200: {ef:.2f}/{em:.2f}/{es:.2f}  Stack: {stack}\n"
        f"Trail on: {tsign}{av * TRAIL_ACT:.2f} (ATR x{TRAIL_ACT})  Dist: {av * TRAIL_DIST:.2f} (ATR x{TRAIL_DIST})\n"
        f"Time    : {ts}"
    )

def trail_alert(direction, ts, best_px, entry_px, new_sl, target, av, entry_atr):
    runup = best_px - entry_px if direction == "long" else entry_px - best_px
    tsign = "-" if direction == "long" else "+"
    detail = f"(best {tsign} ATR x{TRAIL_DIST} = {tsign}{av * TRAIL_DIST:.2f})"
    orig_sl = entry_px - entry_atr * SL_MULT if direction == "long" else entry_px + entry_atr * SL_MULT
    return (
        f"APM v6.1 | TRAIL STOP ACTIVATED | BTC-USD [1D]\n"
        f"Direction : {direction.upper()}\n"
        f"Best price: {best_px:.2f}  |  Entry: {entry_px:.2f}\n"
        f"Trail SL  : {new_sl:.2f}  {detail}\n"
        f"Prev SL   : {orig_sl:.2f}  |  Target: {target:.2f}\n"
        f"Runup     : +{runup:.2f} ({runup / entry_px * 100:.2f}%)\n"
        f"Time      : {ts}"
    )

def exit_alert(direction, ts, entry_px, exit_px, net_pnl, comm, max_runup, bars, equity_after):
    move = (exit_px - entry_px) / entry_px * 100 if direction == "long" else (entry_px - exit_px) / entry_px * 100
    result = "WIN" if net_pnl > 0 else "LOSS"
    return (
        f"APM v6.1 | {direction.upper()} EXIT [{result}] | BTC-USD [1D]\n"
        f"Entry   : {entry_px:.2f}  ->  Exit: {exit_px:.2f}\n"
        f"Move    : {move:+.2f}%\n"
        f"P&L     : {net_pnl:+.2f} USD\n"
        f"Comm    : -{comm:.2f} USD\n"
        f"Max runup: {max_runup:.2f}\n"
        f"Bars    : {bars}\n"
        f"Equity  : ${equity_after:.2f}\n"
        f"Trades  : {closed_count}  |  Win rate: {win_count/closed_count*100:.1f}%\n"
        f"Time    : {ts}"
    )

def panic_alert(started, av, atr_bl_v, ts):
    status = "STARTED" if started else "CLEARED"
    action = "New entries SUSPENDED" if started else "New entries RESUMED"
    return (
        f"APM v6.1 | PANIC REGIME {status} | BTC-USD [1D]\n"
        f"ATR     : {av:.2f}  |  ATR baseline: {atr_bl_v:.2f}\n"
        f"Ratio   : {av / atr_bl_v:.2f}x  [threshold: {PANIC_MULT}x]\n"
        f"Status  : {action}\n"
        f"Time    : {ts}"
    )

# ── Bar-by-bar simulation ──────────────────────────────────────────────────────
equity     = INIT_CAP
in_trade   = False
direction  = None
entry_px   = sl_price = tp_price = best_price = entry_atr = qty = 0.0
entry_time = None

tradesdict     = []
alerts         = []
equity_curve   = [equity]
win_count      = 0
closed_count   = 0
prev_panic     = False
trail_active_f = False
max_runup_f    = 0.0
bar_index_map  = {t: i for i, t in enumerate(df.index)}

l_e  = long_entry.values
s_e  = short_entry.values
o    = df["Open"].values
h    = df["High"].values
l_   = df["Low"].values
c    = df["Close"].values
atr_v = df["ATR"].values
idx  = df.index

for i in range(len(df)):
    ca = atr_v[i]
    if np.isnan(ca) or ca == 0:
        equity_curve.append(equity); continue

    eff = max(ca, c[i] * ATR_FLOOR)  # always == ca since ATR_FLOOR=0.0
    row       = df.iloc[i]
    cur_ts    = idx[i]
    cur_panic = bool(is_panic.iloc[i])
    if cur_panic and not prev_panic:
        alerts.append((cur_ts, "PANIC_START", panic_alert(True,  ca, float(df["ATR_BL"].iloc[i]), cur_ts)))
    elif not cur_panic and prev_panic:
        alerts.append((cur_ts, "PANIC_CLEAR", panic_alert(False, ca, float(df["ATR_BL"].iloc[i]), cur_ts)))
    prev_panic = cur_panic
    exited = False

    if in_trade:
        if direction == "long":
            if h[i] > best_price: best_price = h[i]
            max_runup_f = max(max_runup_f, best_price - entry_px)
            if best_price >= entry_px + entry_atr * TRAIL_ACT:
                t = best_price - entry_atr * TRAIL_DIST
                if t > sl_price: sl_price = t
                if not trail_active_f:
                    trail_active_f = True
                    alerts.append((cur_ts, "TRAIL", trail_alert(
                        "long", cur_ts, best_price, entry_px, sl_price, tp_price, ca, entry_atr)))
            if l_[i] <= sl_price:
                ep = min(o[i], sl_price); pnl = (ep - entry_px) * qty
                comm = (entry_px + ep) * qty * COMMISSION
                net_pnl = pnl - comm; equity += net_pnl
                closed_count += 1
                if net_pnl > 0: win_count += 1
                bars_held = i - bar_index_map[entry_time]
                tradesdict.append({"entry_time": entry_time, "exit_time": cur_ts,
                                   "direction": "long", "entry": entry_px, "exit": ep,
                                   "dollar_pnl": net_pnl, "equity": equity, "result": "SL",
                                   "max_runup": max_runup_f, "bars": bars_held,
                                   "pnl_pct": (ep - entry_px) / entry_px * 100})
                alerts.append((cur_ts, "EXIT", exit_alert(
                    "long", cur_ts, entry_px, ep, net_pnl, comm, max_runup_f, bars_held, equity)))
                in_trade = False; exited = True
            elif h[i] >= tp_price:
                ep = max(o[i], tp_price); pnl = (ep - entry_px) * qty
                comm = (entry_px + ep) * qty * COMMISSION
                net_pnl = pnl - comm; equity += net_pnl
                closed_count += 1
                if net_pnl > 0: win_count += 1
                bars_held = i - bar_index_map[entry_time]
                tradesdict.append({"entry_time": entry_time, "exit_time": cur_ts,
                                   "direction": "long", "entry": entry_px, "exit": ep,
                                   "dollar_pnl": net_pnl, "equity": equity, "result": "TP",
                                   "max_runup": max_runup_f, "bars": bars_held,
                                   "pnl_pct": (ep - entry_px) / entry_px * 100})
                alerts.append((cur_ts, "EXIT", exit_alert(
                    "long", cur_ts, entry_px, ep, net_pnl, comm, max_runup_f, bars_held, equity)))
                in_trade = False; exited = True

        else:  # short
            if l_[i] < best_price: best_price = l_[i]
            max_runup_f = max(max_runup_f, entry_px - best_price)
            if best_price <= entry_px - entry_atr * TRAIL_ACT:
                t = best_price + entry_atr * TRAIL_DIST
                if t < sl_price: sl_price = t
                if not trail_active_f:
                    trail_active_f = True
                    alerts.append((cur_ts, "TRAIL", trail_alert(
                        "short", cur_ts, best_price, entry_px, sl_price, tp_price, ca, entry_atr)))
            if h[i] >= sl_price:
                ep = max(o[i], sl_price); pnl = (entry_px - ep) * qty
                comm = (entry_px + ep) * qty * COMMISSION
                net_pnl = pnl - comm; equity += net_pnl
                closed_count += 1
                if net_pnl > 0: win_count += 1
                bars_held = i - bar_index_map[entry_time]
                tradesdict.append({"entry_time": entry_time, "exit_time": cur_ts,
                                   "direction": "short", "entry": entry_px, "exit": ep,
                                   "dollar_pnl": net_pnl, "equity": equity, "result": "SL",
                                   "max_runup": max_runup_f, "bars": bars_held,
                                   "pnl_pct": (entry_px - ep) / entry_px * 100})
                alerts.append((cur_ts, "EXIT", exit_alert(
                    "short", cur_ts, entry_px, ep, net_pnl, comm, max_runup_f, bars_held, equity)))
                in_trade = False; exited = True
            elif l_[i] <= tp_price:
                ep = min(o[i], tp_price); pnl = (entry_px - ep) * qty
                comm = (entry_px + ep) * qty * COMMISSION
                net_pnl = pnl - comm; equity += net_pnl
                closed_count += 1
                if net_pnl > 0: win_count += 1
                bars_held = i - bar_index_map[entry_time]
                tradesdict.append({"entry_time": entry_time, "exit_time": cur_ts,
                                   "direction": "short", "entry": entry_px, "exit": ep,
                                   "dollar_pnl": net_pnl, "equity": equity, "result": "TP",
                                   "max_runup": max_runup_f, "bars": bars_held,
                                   "pnl_pct": (entry_px - ep) / entry_px * 100})
                alerts.append((cur_ts, "EXIT", exit_alert(
                    "short", cur_ts, entry_px, ep, net_pnl, comm, max_runup_f, bars_held, equity)))
                in_trade = False; exited = True

    if not in_trade:
        if l_e[i]:
            sd = eff * SL_MULT; entry_px = c[i]; sl_price = entry_px - sd
            tp_price = entry_px + eff * TP_MULT; entry_atr = eff
            best_price = entry_px; qty = equity * RISK_PCT / sd
            entry_time = idx[i]; direction = "long"; in_trade = True
            trail_active_f = False; max_runup_f = 0.0
            alerts.append((entry_time, "ENTRY", entry_alert(
                "long", entry_time, c[i], ca, sd, qty, equity, row)))
        elif s_e[i]:
            sd = eff * SL_MULT; entry_px = c[i]; sl_price = entry_px + sd
            tp_price = entry_px - eff * TP_MULT; entry_atr = eff
            best_price = entry_px; qty = equity * RISK_PCT / sd
            entry_time = idx[i]; direction = "short"; in_trade = True
            trail_active_f = False; max_runup_f = 0.0
            alerts.append((entry_time, "ENTRY", entry_alert(
                "short", entry_time, c[i], ca, sd, qty, equity, row)))

    equity_curve.append(equity)

# ── Results ────────────────────────────────────────────────────────────────────
trades = tradesdict
tdf = pd.DataFrame(trades)
print(f"\n{'='*58}")
print(f"  APM v6.1 (sweep-optimised)  |  {TICKER} {INTERVAL}  |  Longs & Shorts")
print(f"{'='*58}")

if tdf.empty:
    print("  No trades generated.")
else:
    wins   = tdf[tdf["dollar_pnl"] > 0]; losses = tdf[tdf["dollar_pnl"] <= 0]
    total  = len(tdf); wr = len(wins) / total * 100
    net    = tdf["dollar_pnl"].sum(); net_pct = net / INIT_CAP * 100
    gp     = wins["dollar_pnl"].sum(); gl = abs(losses["dollar_pnl"].sum())
    pf     = gp / gl if gl > 0 else float("inf")
    avg_w  = wins["dollar_pnl"].mean() if not wins.empty else 0
    avg_l  = losses["dollar_pnl"].mean() if not losses.empty else 0

    eq_arr   = np.array(equity_curve)
    roll_max = np.maximum.accumulate(eq_arr)
    dd       = ((eq_arr - roll_max) / roll_max * 100).min()

    longs_df  = tdf[tdf["direction"] == "long"]
    shorts_df = tdf[tdf["direction"] == "short"]

    print(f"  Period   : {df.index[0].date()} → {df.index[-1].date()}")
    print(f"  Trades   : {total}  (L={len(longs_df)}, S={len(shorts_df)})")
    print(f"  Win rate : {wr:.1f}%  ({len(wins)}W / {len(losses)}L)")
    print(f"  Net P&L  : ${net:+.2f}  ({net_pct:+.2f}%)")
    print(f"  Prof Fac : {pf:.3f}")
    print(f"  Avg Win  : ${avg_w:+.2f}   Avg Loss: ${avg_l:+.2f}")
    print(f"  Max DD   : {dd:.2f}%")
    print(f"  Final Eq : ${equity:,.2f}")

    if not longs_df.empty:
        lw = (longs_df["dollar_pnl"] > 0).sum()
        print(f"\n  Longs : {len(longs_df)} trades  WR={lw/len(longs_df)*100:.1f}%  "
              f"Net=${longs_df['dollar_pnl'].sum():+.2f}")
    if not shorts_df.empty:
        sw = (shorts_df["dollar_pnl"] > 0).sum()
        print(f"  Shorts: {len(shorts_df)} trades  WR={sw/len(shorts_df)*100:.1f}%  "
              f"Net=${shorts_df['dollar_pnl'].sum():+.2f}")

    print(f"\n  Exit breakdown:")
    print(tdf["result"].value_counts().to_string())

    # Year-by-year breakdown
    tdf["year"] = pd.to_datetime(tdf["entry_time"]).dt.year
    print(f"\n  Year-by-year:")
    for yr, grp in tdf.groupby("year"):
        yw = (grp["dollar_pnl"] > 0).sum(); yn = len(grp)
        print(f"    {yr}  n={yn:2d}  WR={yw/yn*100:.0f}%  Net=${grp['dollar_pnl'].sum():+.2f}")

    tdf.to_csv("apm_v6_trades_btcusd_1d.csv", index=False)
    print(f"\n  Saved → apm_v6_trades_btcusd_1d.csv")

    # ── Dashboard export ──────────────────────────────────────────────────────
    from pathlib import Path as _Path
    _dash_out = _Path(__file__).resolve().parent.parent.parent.parent / "docs" / "data" / "btcusd" / "v6_trades.csv"
    dash = tdf.rename(columns={"result": "exit_reason"}).copy()
    dash = dash[["entry_time","exit_time","direction","entry","exit","exit_reason","pnl_pct","dollar_pnl","equity","year"]]
    dash.to_csv(_dash_out, index=False)
    print(f"  Saved → {_dash_out.relative_to(_Path(__file__).resolve().parent.parent.parent.parent)}")

print(f"{'='*58}")

# ── Alert output ───────────────────────────────────────────────────────────────
type_counts = {}
for _, atype, _ in alerts:
    type_counts[atype] = type_counts.get(atype, 0) + 1

SEP = "-" * 70
alert_log = ("\n" + SEP + "\n").join(msg for _, _, msg in alerts)
with open("apm_v6_alerts_btcusd_1d.txt", "w") as f:
    f.write(alert_log)

print(f"\nAlerts summary:")
for k in ["ENTRY", "TRAIL", "EXIT", "PANIC_START", "PANIC_CLEAR"]:
    if k in type_counts:
        print(f"  {k:<14}: {type_counts[k]}")
print(f"Total alerts: {len(alerts)}")
print(f"Alerts log  → apm_v6_alerts_btcusd_1d.txt")

preview = [msg for _, atype, msg in alerts if atype not in ("PANIC_START", "PANIC_CLEAR")][:3]
if preview:
    print(f"\n{'='*58}\n  ALERT PREVIEW (first 3 non-panic)\n{'='*58}")
    for msg in preview:
        print(SEP)
        print(msg)

# ── Google Sheets push (optional) ─────────────────────────────────────────────
import os
SA = os.path.join(os.path.dirname(__file__), "service_account.json")
if os.path.exists(SA):
    from push_to_sheets_v6 import push_results
    push_results(
        trades      = trades,
        alerts      = alerts,
        symbol      = TICKER,
        interval    = INTERVAL,
        period      = PERIOD,
        initial_cap = INIT_CAP,
        final_equity= equity,
    )
else:
    print(f"\nSkipping Google Sheets push — service_account.json not found.")
    print(f"See push_to_sheets_v6.py for setup instructions.")
