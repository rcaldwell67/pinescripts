# ─────────────────────────────────────────────────────────────────────────────
# APM v2.2 — Python backtest  (BTC-USD 30m, both directions)
#
# v2.2 changes vs v2.0 baseline:
#   Full EMA stack  : EMA21>EMA50>EMA200 (was close>EMA200 & EMA21>EMA50)
#   EMA slope filter: EMA21 trending in trade direction over 3 bars
#   RSI direction   : rising (long) / falling (short) on entry bar
#   Volume mult     : 1.2x  (was 1.0x)
#   Body filter     : 0.20x ATR  (was 0.15x)
#   ATR floor       : 0.20% of price  (new)
#   SL mult         : 2.0x  (was 1.5x)
#   TP mult         : 3.5x  (was 2.0x)  ← v2.2 sweep-peak
#   Trail activate  : 2.5x  (was 1.5x)
#   Trail distance  : 1.5x  (was 0.8x)  locked to entry-bar ATR
#   Panic mult      : 1.3x  (was 1.5x)
# ─────────────────────────────────────────────────────────────────────────────

import subprocess, sys
for pkg in ["yfinance", "pandas", "numpy", "matplotlib"]:
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])

import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import warnings
warnings.filterwarnings("ignore")

# ─── Configuration ─────────────────────────────────────────────────────────────
TICKER   = "BTC-USD"
PERIOD   = "max"
INTERVAL = "30m"

EMA_FAST = 21
EMA_MID  = 50
EMA_SLOW = 200
ADX_LEN  = 14
RSI_LEN  = 14
ATR_LEN  = 14
VOL_LEN  = 20
ATR_BL_LEN = 60      # ATR baseline SMA length (panic detection)

INITIAL_CAPITAL = 10_000.0
COMMISSION_PCT  = 0.0006   # 0.06% per side
RISK_PCT        = 0.01     # 1% equity risked per trade (matches Pine)

# ── v2.2 Pine Script defaults ─────────────────────────────────────────────────
PB_PCT     = 0.15    # pullback tolerance %
ADX_THRESH = 25      # ADX threshold (v2.x)
VOL_MULT   = 1.2     # volume multiplier (v2.1+)
MIN_BODY   = 0.20    # min |close-open|/ATR (v2.1+)
ATR_FLOOR  = 0.0020  # ATR must be >= 0.20% of price (v2.1+)
SL_MULT    = 2.0     # stop   = entry ± ATR×SL_MULT (v2.1+)
TP_MULT    = 3.5     # target = entry ± ATR×TP_MULT (v2.2)
TRAIL_ACT  = 2.5     # trail activates at ATR×TRAIL_ACT profit (v2.1+)
TRAIL_DIST = 1.5     # trail stays ATR×TRAIL_DIST from best price (v2.1+)
PANIC_MULT = 1.3     # ATR > ATR_BL × PANIC_MULT → no entries (v2.1+)

RSI_LO_L = 42;  RSI_HI_L = 68
RSI_LO_S = 32;  RSI_HI_S = 58

TRADE_LONGS  = True
TRADE_SHORTS = True

# ─── Download ──────────────────────────────────────────────────────────────────
print(f"Downloading {TICKER} {INTERVAL} period='{PERIOD}'...")
df = yf.download(TICKER, period=PERIOD, interval=INTERVAL,
                 auto_adjust=True, progress=False)
df.columns = df.columns.get_level_values(0)
df.index   = pd.to_datetime(df.index, utc=True)
df.sort_index(inplace=True)
print(f"Rows: {len(df)}  Range: {df.index[0]} → {df.index[-1]}")
print()

# ─── Indicators ────────────────────────────────────────────────────────────────
def ema(s, n):     return s.ewm(span=n, adjust=False).mean()
def sma(s, n):     return s.rolling(n).mean()
def rsi_calc(s, n):
    d  = s.diff()
    g  = d.clip(lower=0).rolling(n).mean()
    ls = (-d).clip(lower=0).rolling(n).mean()
    return 100 - 100 / (1 + g / ls.replace(0, np.nan))

def atr_calc(df, n):
    h, l, c = df["High"], df["Low"], df["Close"]
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def adx_calc(df, n):
    h, l, c = df["High"], df["Low"], df["Close"]
    up   = h.diff(); dn = -l.diff()
    pdm  = np.where((up > dn) & (up > 0), up, 0.0)
    ndm  = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr   = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    atr14 = tr.rolling(n).mean()
    pdi  = pd.Series(pdm, index=h.index).rolling(n).mean() / atr14 * 100
    ndi  = pd.Series(ndm, index=h.index).rolling(n).mean() / atr14 * 100
    dx   = ((pdi-ndi).abs() / (pdi+ndi).replace(0, np.nan) * 100)
    return pdi, ndi, dx.rolling(n).mean()

df["EMA_FAST"] = ema(df["Close"], EMA_FAST)
df["EMA_MID"]  = ema(df["Close"], EMA_MID)
df["EMA_SLOW"] = ema(df["Close"], EMA_SLOW)
df["RSI"]      = rsi_calc(df["Close"], RSI_LEN)
df["ATR"]      = atr_calc(df, ATR_LEN)
df["ATR_BL"]   = sma(df["ATR"], ATR_BL_LEN)
df["VOL_MA"]   = sma(df["Volume"], VOL_LEN)
df["DI_PLUS"], df["DI_MINUS"], df["ADX"] = adx_calc(df, ADX_LEN)
df.dropna(inplace=True)

# ─── Signal construction (v2.2 — full Pine Script filter set) ─────────────────
pb_tol_up  = df["EMA_FAST"].shift(1) * (1.0 + PB_PCT / 100.0)
pb_tol_dn  = df["EMA_FAST"].shift(1) * (1.0 - PB_PCT / 100.0)
body_size  = (df["Close"] - df["Open"]).abs() / df["ATR"]

# Pullback trigger: prev-bar tagged EMA zone, current bar confirms
long_pb  = (df["Low"].shift(1)  <= pb_tol_up) & \
           (df["Close"] > df["EMA_FAST"]) & \
           (df["Close"] > df["Open"]) & \
           (body_size >= MIN_BODY)

short_pb = (df["High"].shift(1) >= pb_tol_dn) & \
           (df["Close"] < df["EMA_FAST"]) & \
           (df["Close"] < df["Open"]) & \
           (body_size >= MIN_BODY)

is_trending  = df["ADX"] > ADX_THRESH
is_panic     = df["ATR"]  > df["ATR_BL"] * PANIC_MULT
vol_ok       = df["Volume"] >= df["VOL_MA"] * VOL_MULT
rsi_long_ok  = (df["RSI"] >= RSI_LO_L) & (df["RSI"] <= RSI_HI_L)
rsi_short_ok = (df["RSI"] >= RSI_LO_S) & (df["RSI"] <= RSI_HI_S)
atr_floor_ok = df["ATR"] / df["Close"] >= ATR_FLOOR

# v2.1+: full EMA stack alignment
ema_bull_full = (df["EMA_FAST"] > df["EMA_MID"]) & (df["EMA_MID"] > df["EMA_SLOW"])
ema_bear_full = (df["EMA_FAST"] < df["EMA_MID"]) & (df["EMA_MID"] < df["EMA_SLOW"])

# v2.1+: EMA slope filter (3-bar lookback)
ema_slope_up   = df["EMA_FAST"] > df["EMA_FAST"].shift(3)
ema_slope_down = df["EMA_FAST"] < df["EMA_FAST"].shift(3)

# v2.1+: RSI momentum direction
rsi_rising  = df["RSI"] > df["RSI"].shift(1)
rsi_falling = df["RSI"] < df["RSI"].shift(1)

long_signal = (
    TRADE_LONGS    &
    long_pb        &
    ema_bull_full  &
    ema_slope_up   &
    rsi_rising     &
    rsi_long_ok    &
    vol_ok         &
    atr_floor_ok   &
    is_trending    &
    ~is_panic
)

short_signal = (
    TRADE_SHORTS   &
    short_pb       &
    ema_bear_full  &
    ema_slope_down &
    rsi_falling    &
    rsi_short_ok   &
    vol_ok         &
    atr_floor_ok   &
    is_trending    &
    ~is_panic
)

# ─── Signal diagnostics ─────────────────────────────────────────────────────────
components_long = [
    ("long_pb",      long_pb),
    ("ema_bull_full",ema_bull_full),
    ("ema_slope_up", ema_slope_up),
    ("rsi_rising",   rsi_rising),
    ("rsi_long_ok",  rsi_long_ok),
    ("vol_ok",       vol_ok),
    ("atr_floor_ok", atr_floor_ok),
    ("is_trending",  is_trending),
    ("~is_panic",    ~is_panic),
]
components_short = [
    ("short_pb",      short_pb),
    ("ema_bear_full", ema_bear_full),
    ("ema_slope_dn",  ema_slope_down),
    ("rsi_falling",   rsi_falling),
    ("rsi_short_ok",  rsi_short_ok),
    ("vol_ok",        vol_ok),
    ("atr_floor_ok",  atr_floor_ok),
    ("is_trending",   is_trending),
    ("~is_panic",     ~is_panic),
]

print("--- Signal filter pass-through (long) ---")
cumulative = pd.Series([True]*len(df), index=df.index)
for name, mask in components_long:
    cumulative = cumulative & mask
    print(f"  {name:<18} → {cumulative.sum():>4} rows pass")
print("--- Signal filter pass-through (short) ---")
cumulative = pd.Series([True]*len(df), index=df.index)
for name, mask in components_short:
    cumulative = cumulative & mask
    print(f"  {name:<18} → {cumulative.sum():>4} rows pass")
print()
print(f"Signals — Long: {long_signal.sum()}  Short: {short_signal.sum()}")

# ─── Alert helper functions ─────────────────────────────────────────────────────────────
def _al(lines): return "\n".join(lines)

def entry_alert(direction, ts, cl, av, atr_bl_v, sd, qty, equity_at_entry, row):
    sl  = cl - sd if direction == "long" else cl + sd
    tp  = cl + av * TP_MULT if direction == "long" else cl - av * TP_MULT
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
    return _al([
        f"APM v2.2 | {dl} ENTRY | {TICKER} [{INTERVAL}]",
        f"Entry   : {cl:.2f}  |  Equity: ${equity_at_entry:.2f}",
        f"Stop    : {sl:.2f}  ({ss}{sd:.2f} = ATR x{SL_MULT})",
        f"Target  : {tp:.2f}  ({ts_}{av*TP_MULT:.2f} = ATR x{TP_MULT})",
        f"R:R     : 1:{rr:.2f}  |  Risk: ${rsk:.2f} ({RISK_PCT*100:.1f}%)",
        f"Qty     : {qty:.4f}",
        f"ATR     : {av:.2f} ({av/cl*100:.3f}% of price)  |  Floor: {'OK' if av/cl >= ATR_FLOOR else 'FAIL'}",
        f"RSI     : {float(row['RSI']):.2f} [{rr_range}]  |  Dir: {rdir}",
        f"ADX     : {float(row['ADX']):.2f}  DI+: {float(row['DI_PLUS']):.2f}  DI-: {float(row['DI_MINUS']):.2f}  [min {ADX_THRESH}]",
        f"Vol/MA  : {float(row['Volume'])/float(row['VOL_MA']):.2f}x  [min {VOL_MULT}x]",
        f"Body    : {body_v:.3f}x ATR  [min {MIN_BODY}x]",
        f"EMA{EMA_FAST}/{EMA_MID}/{EMA_SLOW}: {float(row['EMA_FAST']):.2f}/{float(row['EMA_MID']):.2f}/{float(row['EMA_SLOW']):.2f}  Stack: {stk}  Slope: {slp}",
        f"Trail on: {ts_}{av*TRAIL_ACT:.2f} (ATR x{TRAIL_ACT})  Dist: {av*TRAIL_DIST:.2f} (ATR x{TRAIL_DIST})",
        f"Time    : {ts}",
    ])

def trail_alert(direction, best, entry, new_sl, old_sl, tp, av, ts):
    dl   = "LONG" if direction == "long" else "SHORT"
    ds   = "-" if direction == "long" else "+"
    runup = abs(best - entry)
    rpct  = runup / entry * 100
    rs    = "+" if direction == "long" else "-"
    return _al([
        f"APM v2.2 | TRAIL STOP ACTIVATED | {TICKER} [{INTERVAL}]",
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
        f"APM v2.2 | {dl} EXIT [{res}] | {TICKER} [{INTERVAL}]",
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
        f"APM v2.2 | {lbl} | {TICKER} [{INTERVAL}]",
        f"ATR     : {atr_v:.2f}  |  ATR baseline: {atr_bl_v:.2f}",
        f"Ratio   : {atr_v/atr_bl_v:.2f}x  [threshold: {PANIC_MULT}x]",
        f"Status  : {status}",
        f"Time    : {ts}",
    ])

equity       = INITIAL_CAPITAL
pos          = None
trades       = []
alerts       = []
eqcurve      = []
win_count    = 0
closed_count = 0
prev_panic   = False
bar_index    = {t: i for i, t in enumerate(df.index)}

for ts, row in df.iterrows():
    close = float(row["Close"]); high = float(row["High"])
    low   = float(row["Low"]);   atr  = float(row["ATR"])
    atr_bl_v = float(row["ATR_BL"])
    cur_panic = bool(is_panic[ts])

    # ── panic edge alerts
    if cur_panic and not prev_panic:
        alerts.append((ts, "PANIC_START", panic_alert(True,  atr, atr_bl_v, ts)))
    elif not cur_panic and prev_panic:
        alerts.append((ts, "PANIC_CLEAR", panic_alert(False, atr, atr_bl_v, ts)))
    prev_panic = cur_panic

    # reset per-bar exit flags
    htp = hsl = False
    xp  = pnl = 0.0
    d   = None

    # ── manage open position
    if pos is not None:
        d = pos["direction"]
        if d == "long":
            if high > pos["best"]:
                pos["best"] = high
                pos["max_runup"] = max(pos["max_runup"], high - pos["entry"])
            if pos["best"] >= pos["trail_activate_px"]:
                new_sl = pos["best"] - pos["trail_dist_fixed"]
                new_sl = max(pos["sl"], new_sl)
                if not pos["trail_active"]:
                    pos["trail_active"] = True
                    alerts.append((ts, "TRAIL", trail_alert(
                        d, pos["best"], pos["entry"], new_sl,
                        pos["sl"], pos["tp"], pos["entry_atr"], ts)))
                pos["sl"] = new_sl
            htp = high >= pos["tp"]
            hsl = low  <= pos["sl"]
        else:  # short
            if low < pos["best"]:
                pos["best"] = low
                pos["max_runup"] = max(pos["max_runup"], pos["entry"] - low)
            if pos["best"] <= pos["trail_activate_px"]:
                new_sl = pos["best"] + pos["trail_dist_fixed"]
                new_sl = min(pos["sl"], new_sl)
                if not pos["trail_active"]:
                    pos["trail_active"] = True
                    alerts.append((ts, "TRAIL", trail_alert(
                        d, pos["best"], pos["entry"], new_sl,
                        pos["sl"], pos["tp"], pos["entry_atr"], ts)))
                pos["sl"] = new_sl
            htp = low  <= pos["tp"]
            hsl = high >= pos["sl"]

        if htp or hsl:
            xp  = pos["tp"] if htp else pos["sl"]
            pnl = ((xp - pos["entry"]) / pos["entry"] if d == "long"
                   else (pos["entry"] - xp) / pos["entry"])

    if htp or hsl:
        comm_dollar  = pos["notional"] * COMMISSION_PCT * 2
        dp           = pnl * pos["notional"] - comm_dollar
        equity      += dp
        closed_count += 1
        if dp > 0: win_count += 1
        bars_held = bar_index[ts] - bar_index[pos["entry_time"]]
        trades.append({
            "entry_time": pos["entry_time"], "exit_time": ts,
            "direction":  d,
            "entry":      pos["entry"],      "exit":   xp,
            "result":     "TP" if htp else "SL",
            "pnl_pct":    round(pnl * 100, 3),
            "dollar_pnl": round(dp, 2),
            "equity":     round(equity, 2),
        })
        alerts.append((ts, "EXIT", exit_alert(
            d, pos["entry"], xp, dp, comm_dollar, pos["max_runup"],
            bars_held, equity, closed_count, win_count, ts)))
        pos = None

    # ── new entry
    if pos is None:
        sig = ("long"  if bool(long_signal[ts])  else
               "short" if bool(short_signal[ts]) else None)
        if sig:
            sd    = atr * SL_MULT
            rc    = equity * RISK_PCT
            qty   = rc / sd
            notl  = qty * close
            notl  = min(notl, equity * 5.0)   # 5× leverage cap
            sl    = close - sd if sig == "long" else close + sd
            tp    = close + atr * TP_MULT if sig == "long" else close - atr * TP_MULT
            # lock trail thresholds to entry-bar ATR (avoids ATR-shrink bug)
            tap   = (close + atr * TRAIL_ACT if sig == "long"
                     else close - atr * TRAIL_ACT)
            tdf_v = atr * TRAIL_DIST
            qty_v = notl / close
            alerts.append((ts, "ENTRY", entry_alert(
                sig, ts, close, atr, atr_bl_v, sd, qty_v, equity, row)))
            pos = {"direction": sig, "entry": close, "entry_time": ts,
                   "sl": sl, "tp": tp, "best": close, "notional": notl,
                   "entry_atr": atr, "trail_activate_px": tap,
                   "trail_dist_fixed": tdf_v, "trail_active": False,
                   "max_runup": 0.0}

    eqcurve.append({"time": ts, "equity": equity})

print(f"\nSimulation complete. Trades: {len(trades)}")

# ─── Stats ──────────────────────────────────────────────────────────────────────
tdf = pd.DataFrame(trades)

if tdf.empty:
    print("No trades generated.")
else:
    wins  = tdf[tdf["dollar_pnl"] >  0]
    losss = tdf[tdf["dollar_pnl"] <= 0]
    wp    = len(wins) / len(tdf) * 100
    ret   = (equity / INITIAL_CAPITAL - 1) * 100
    pf    = (wins["dollar_pnl"].sum() / abs(losss["dollar_pnl"].sum())
             if not losss.empty and losss["dollar_pnl"].sum() != 0 else float("inf"))
    rr    = (wins["dollar_pnl"].mean() / abs(losss["dollar_pnl"].mean())
             if not losss.empty else float("inf"))
    eq_s  = pd.Series([e["equity"] for e in eqcurve])
    mdd   = ((eq_s - eq_s.cummax()) / eq_s.cummax() * 100).min()
    longs_df  = tdf[tdf["direction"] == "long"]
    shorts_df = tdf[tdf["direction"] == "short"]

    print()
    print("=" * 60)
    print(f"  APM v2.2  —  {TICKER} {INTERVAL}  (max)")
    print("=" * 60)
    print(f"  Initial capital   :  $ {INITIAL_CAPITAL:>10,.2f}")
    print(f"  Final equity      :  $ {equity:>10,.2f}")
    print(f"  Net P&L           : $ {equity - INITIAL_CAPITAL:>+10,.2f}")
    print(f"  Return            :  {ret:>10.2f} %")
    print(f"  Max drawdown      :  {mdd:>10.2f} %")
    print(f"  Profit factor     :  {pf:>10.3f}")
    print("-" * 60)
    print(f"  Total trades      : {len(tdf):>6}")
    print(f"    Long  trades    : {len(longs_df):>6}")
    print(f"    Short trades    : {len(shorts_df):>6}")
    print(f"  TP exits          : {(tdf['result']=='TP').sum():>6}")
    print(f"  SL exits          : {(tdf['result']=='SL').sum():>6}")
    print(f"  Win rate          :  {wp:>10.1f} %")
    print(f"  Avg win           :  $ {wins['dollar_pnl'].mean():>+9.2f}")
    print(f"  Avg loss          :  $ {losss['dollar_pnl'].mean():>+9.2f}")
    print(f"  Avg R:R           :  {rr:>10.2f}")
    print(f"  Best trade        :  $ {tdf['dollar_pnl'].max():>+9.2f}")
    print(f"  Worst trade       :  $ {tdf['dollar_pnl'].min():>+9.2f}")
    print("=" * 60)

    # per-direction breakdown
    for direction in ["long", "short"]:
        sub = tdf[tdf["direction"] == direction]
        if sub.empty:
            continue
        sub_w  = sub[sub["dollar_pnl"] >  0]
        sub_l  = sub[sub["dollar_pnl"] <= 0]
        sub_wr = len(sub_w) / len(sub) * 100
        sub_pf = (sub_w["dollar_pnl"].sum() / abs(sub_l["dollar_pnl"].sum())
                  if not sub_l.empty and sub_l["dollar_pnl"].sum() != 0 else float("inf"))
        sub_pnl = sub["dollar_pnl"].sum()
        print(f"  {direction.upper():<6} trades={len(sub):>3}  "
              f"WR={sub_wr:.0f}%  PF={sub_pf:.3f}  net=${sub_pnl:+.2f}")

    # ── CSV ──────────────────────────────────────────────────────────────────
    out_csv = f"apm_v2_trades_{TICKER.replace('-','').lower()}_{INTERVAL}.csv"
    tdf.to_csv(out_csv, index=False)
    print(f"Trades CSV → {out_csv}")

# ─── Write alerts log ──────────────────────────────────────────────────────────────────
SEP = "-" * 70
alert_types = {t: 0 for t in ["ENTRY","TRAIL","EXIT","PANIC_START","PANIC_CLEAR"]}
alert_out   = f"apm_v2_alerts_{TICKER.replace('-','').lower()}_{INTERVAL}.txt"
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

# ─── Push to Google Sheets (requires service_account.json) ─────────────────────
from pathlib import Path as _Path
_SA_KEY = _Path(__file__).parent / "service_account.json"
if _SA_KEY.exists():
    from push_to_sheets_v2 import push_results
    _tdf = pd.DataFrame(trades) if trades else pd.DataFrame()
    push_results(
        trades       = trades,
        alerts       = alerts,
        symbol       = TICKER,
        interval     = INTERVAL,
        period       = PERIOD,
        initial_cap  = INITIAL_CAPITAL,
        final_equity = equity,
    )
else:
    print(f"\nSkipping Google Sheets push — service_account.json not found.")
    print(f"See push_to_sheets_v2.py for setup instructions.")

# ── Equity chart ─────────────────────────────────────────────────────────────
if not tdf.empty:
    eq_df = pd.DataFrame(eqcurve).set_index("time")
    fig, axes = plt.subplots(2, 1, figsize=(14, 8),
                              gridspec_kw={"height_ratios": [3, 1]})
    ax1, ax2 = axes

    ax1.plot(eq_df.index, eq_df["equity"], color="#63b3ed", linewidth=1.5, label="Equity")
    ax1.axhline(INITIAL_CAPITAL, color="#718096", linewidth=0.8, linestyle="--", alpha=0.7)
    ax1.fill_between(eq_df.index, eq_df["equity"], INITIAL_CAPITAL,
                     where=eq_df["equity"] >= INITIAL_CAPITAL, alpha=0.15, color="#48bb78")
    ax1.fill_between(eq_df.index, eq_df["equity"], INITIAL_CAPITAL,
                     where=eq_df["equity"] <  INITIAL_CAPITAL, alpha=0.15, color="#fc8181")
    for _, t in tdf.iterrows():
        ax1.axvline(t["exit_time"], alpha=0.15,
                    color="#48bb78" if t["dollar_pnl"] > 0 else "#fc8181", linewidth=0.6)

    # drawdown subplot
    dd = (eq_s - eq_s.cummax()) / eq_s.cummax() * 100
    ax2.fill_between(eq_df.index, dd.values, 0, color="#fc8181", alpha=0.6)
    ax2.set_ylabel("Drawdown %"); ax2.set_ylim(min(dd.min() * 1.1, -0.5), 1)

    color_ret = "#48bb78" if ret >= 0 else "#fc8181"
    ax1.set_title(f"APM v2.2  |  {TICKER} {INTERVAL}  |  "
                  f"Return: {ret:+.2f}%  PF: {pf:.3f}  WR: {wp:.1f}%  "
                  f"Trades: {len(tdf)}  MaxDD: {mdd:.2f}%",
                  color=color_ret, fontsize=11)
    ax1.set_ylabel("Equity ($)")
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    fig.autofmt_xdate()
    fig.patch.set_facecolor("#0d0d1a"); ax1.set_facecolor("#0d0d1a"); ax2.set_facecolor("#0d0d1a")
    for ax in [ax1, ax2]:
        ax.tick_params(colors="#718096"); ax.yaxis.label.set_color("#718096")
        for spine in ax.spines.values(): spine.set_edgecolor("#2d3748")
    ax1.title.set_color(color_ret)
    plt.tight_layout()
    out_png = f"apm_v2_equity_{TICKER.replace('-','').lower()}_{INTERVAL}.png"
    plt.savefig(out_png, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Chart → {out_png}")
