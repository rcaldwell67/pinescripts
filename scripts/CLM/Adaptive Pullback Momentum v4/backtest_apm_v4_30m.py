# ─────────────────────────────────────────────────────────────────────────────
# APM v4.2 — CLM 30m backtest
# Pine script: "Adaptive Pullback Momentum v4.2"
#
# CLM-specific tuning vs BTC-USD defaults (informed by v1 CLM 15m sweep):
#   ADX threshold : 25  → 18   (crude oil 30m trends at lower ADX than BTC)
#   ATR floor     : 0.20% → 0.10% (crude oil tick-% differs from crypto)
#   VOL_MULT      : 1.2× → 0.9×   (CME futures volume distribution differs)
#   PB_PCT        : 0.15% → 0.30% (crude oil has more EMA-zone noise)
#   PANIC_MULT    : 1.3× → 1.5×   (crude oil spikes are regime changes)
#   ADX slope     : ADDED — only enter on accelerating trend
#   DI spread     : ADDED — require DI_MINUS - DI_PLUS ≥ 5 for shorts,
#                           DI_PLUS - DI_MINUS ≥ 5 for longs
#   Momentum      : ADDED — 5-bar close momentum confirms direction
#   Cooldown      : ADDED — skip 1 signal after 2 consecutive SL exits
#   Longs / Shorts: both enabled (v4.2 benefits both directions at 30m)
# ─────────────────────────────────────────────────────────────────────────────

import subprocess, sys
for pkg in ["yfinance", "pandas", "numpy", "matplotlib", "pytz"]:
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])

import yfinance as yf
import pandas as pd
import numpy as np
import pytz
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import warnings
warnings.filterwarnings("ignore")

# ─── Configuration ─────────────────────────────────────────────────────────────
TICKER   = "CLM"
PERIOD   = "60d"    # Yahoo Finance intraday limit for sub-daily intervals
INTERVAL = "30m"

EMA_FAST   = 21
EMA_MID    = 50
EMA_SLOW   = 200
ADX_LEN    = 14
RSI_LEN    = 14
ATR_LEN    = 14
VOL_LEN    = 20
ATR_BL_LEN = 60      # ATR baseline length for panic detection

INITIAL_CAPITAL = 10_000.0
COMMISSION_PCT  = 0.0006   # 0.06% per side
RISK_PCT        = 0.01     # 1% equity risked per trade

# ── CLM-tuned Pine v4.2 parameters ───────────────────────────────────────────
PB_PCT     = 0.30    # wider pullback tolerance — crude oil EMA-zone noise
ADX_THRESH = 12      # sweep-optimal: DI spread+EMA+momentum already confirm direction
VOL_MULT   = 0.50    # sweep-optimal: 50% of avg vol; was 0.6 (funnel killer)
MIN_BODY   = 0.15    # slight relaxation for crude oil 30m bar structure
ATR_FLOOR  = 0.0010  # 0.10% — crude oil 30m bars are larger in % than BTC
SL_MULT    = 2.0     # stop   = entry ± ATR × SL_MULT
TP_MULT    = 3.5     # target = entry ± ATR × TP_MULT  (v4.2 sweep-peak)
TRAIL_ACT  = 3.5     # trail activates at ATR×3.5 (beyond TP; only big runners)
TRAIL_DIST = 1.5     # trail stays ATR×1.5 from best price
PANIC_MULT = 1.5     # crude oil spikes are regime-changing, not just noise

RSI_LO_L = 42;  RSI_HI_L = 68
RSI_LO_S = 30;  RSI_HI_S = 62   # widened: crude oil RSI momentum wider band

# ── CLM Enhancements (derived from v1 CLM 15m analysis) ──────────────────────
DI_SPREAD_MIN   = 3.0   # relaxed: min directional edge; was 5.0
ADX_SLOPE_BARS  = 1     # relaxed: ADX just needs to be above prior bar; was 2
MOMENTUM_BARS   = 5     # close must confirm direction vs N bars ago

CONSEC_LOSS_LIMIT    = 2   # trigger cooldown after N consecutive SL exits
CONSEC_LOSS_COOLDOWN = 1   # signals to skip during cooldown
TP_COOLDOWN_BARS     = 2   # mandatory pause after any TP — prevents same-bar re-entry chop

TRADE_LONGS  = False
TRADE_SHORTS = True

# ─── Download ──────────────────────────────────────────────────────────────────
print(f"Downloading {TICKER} {INTERVAL} period='{PERIOD}'...")
df = yf.download(TICKER, period=PERIOD, interval=INTERVAL,
                 auto_adjust=True, progress=False)
if df.empty:
    raise SystemExit(f"No data returned for {TICKER} {INTERVAL}.")
if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.droplevel(1)
df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
df = df[df["Volume"] > 0].copy()
df.dropna(inplace=True)
print(f"Rows: {len(df)}  Range: {df.index[0]} → {df.index[-1]}")

# ─── Indicators ────────────────────────────────────────────────────────────────
df["EMA_FAST"] = df["Close"].ewm(span=EMA_FAST, adjust=False).mean()
df["EMA_MID"]  = df["Close"].ewm(span=EMA_MID,  adjust=False).mean()
df["EMA_SLOW"] = df["Close"].ewm(span=EMA_SLOW, adjust=False).mean()

# RSI (Wilder smoothing)
delta  = df["Close"].diff()
avg_g  = delta.clip(lower=0).ewm(alpha=1 / RSI_LEN, adjust=False).mean()
avg_l  = (-delta).clip(lower=0).ewm(alpha=1 / RSI_LEN, adjust=False).mean()
df["RSI"] = 100 - (100 / (1 + avg_g / avg_l.replace(0, 1e-10)))

# ATR (Wilder smoothing)
hl  = df["High"] - df["Low"]
hpc = (df["High"] - df["Close"].shift(1)).abs()
lpc = (df["Low"]  - df["Close"].shift(1)).abs()
tr  = pd.concat([hl, hpc, lpc], axis=1).max(axis=1)
df["ATR"]    = tr.ewm(alpha=1 / ATR_LEN, adjust=False).mean()
df["ATR_BL"] = df["ATR"].rolling(ATR_BL_LEN).mean()

# Volume SMA
df["VOL_MA"] = df["Volume"].rolling(VOL_LEN).mean()

# ADX / DMI (Wilder smoothing)
up_move  = df["High"] - df["High"].shift(1)
dn_move  = df["Low"].shift(1) - df["Low"]
plus_dm  = np.where((up_move > dn_move) & (up_move > 0), up_move, 0.0)
minus_dm = np.where((dn_move > up_move) & (dn_move > 0), dn_move, 0.0)
s_plus   = pd.Series(plus_dm,  index=df.index).ewm(alpha=1 / ADX_LEN, adjust=False).mean()
s_minus  = pd.Series(minus_dm, index=df.index).ewm(alpha=1 / ADX_LEN, adjust=False).mean()
df["DI_PLUS"]  = 100 * s_plus  / df["ATR"]
df["DI_MINUS"] = 100 * s_minus / df["ATR"]
dx = 100 * (df["DI_PLUS"] - df["DI_MINUS"]).abs() / (
    (df["DI_PLUS"] + df["DI_MINUS"]).replace(0, 1e-10))
df["ADX"] = dx.ewm(alpha=1 / ADX_LEN, adjust=False).mean()

df.dropna(inplace=True)

# ─── Signal components ────────────────────────────────────────────────────────
tol       = PB_PCT / 100.0
body_size = (df["Close"] - df["Open"]).abs() / df["ATR"]

# Regime guards
is_trending = df["ADX"] > ADX_THRESH
is_panic    = df["ATR"] > df["ATR_BL"] * PANIC_MULT

# Full EMA stack
ema_bull = (df["EMA_FAST"] > df["EMA_MID"]) & (df["EMA_MID"] > df["EMA_SLOW"])
ema_bear = (df["EMA_FAST"] < df["EMA_MID"]) & (df["EMA_MID"] < df["EMA_SLOW"])

# EMA slope (3-bar)
ema_slope_up   = df["EMA_FAST"] > df["EMA_FAST"].shift(3)
ema_slope_down = df["EMA_FAST"] < df["EMA_FAST"].shift(3)

# Pullback + recovery (combined, same as Pine entry trigger)
pb_tol_up = df["EMA_FAST"].shift(1) * (1.0 + tol)
pb_tol_dn = df["EMA_FAST"].shift(1) * (1.0 - tol)

long_pb  = ((df["Low"].shift(1)  <= pb_tol_up) &
            (df["Close"] > df["EMA_FAST"])       &
            (df["Close"] > df["Open"])             &
            (body_size >= MIN_BODY))

short_pb = ((df["High"].shift(1) >= pb_tol_dn) &
            (df["Close"] < df["EMA_FAST"])       &
            (df["Close"] < df["Open"])             &
            (body_size >= MIN_BODY))

# RSI momentum + bounds
rsi_rising  = df["RSI"] > df["RSI"].shift(1)
rsi_falling = df["RSI"] < df["RSI"].shift(1)
rsi_long_ok  = (df["RSI"] >= RSI_LO_L) & (df["RSI"] <= RSI_HI_L)
rsi_short_ok = (df["RSI"] >= RSI_LO_S) & (df["RSI"] <= RSI_HI_S)

# Volume + ATR floor
vol_ok       = df["Volume"] >= df["VOL_MA"] * VOL_MULT
atr_floor_ok = df["ATR"] / df["Close"] >= ATR_FLOOR

# Enhancement: rising ADX (accelerating trend)
adx_rising = df["ADX"] > df["ADX"].shift(ADX_SLOPE_BARS)

# Enhancement: DI spread confirms directional dominance
di_spread_ok_l = (df["DI_PLUS"]  - df["DI_MINUS"]) >= DI_SPREAD_MIN
di_spread_ok_s = (df["DI_MINUS"] - df["DI_PLUS"])  >= DI_SPREAD_MIN

# Enhancement: 5-bar momentum confirms direction
momentum_ok_l = df["Close"] > df["Close"].shift(MOMENTUM_BARS)
momentum_ok_s = df["Close"] < df["Close"].shift(MOMENTUM_BARS)

# ─── Final entry conditions ───────────────────────────────────────────────────
long_signal = (
    TRADE_LONGS    &
    long_pb        &
    ema_bull       &
    ema_slope_up   &
    rsi_rising     &
    rsi_long_ok    &
    vol_ok         &
    atr_floor_ok   &
    is_trending    &
    adx_rising     &
    di_spread_ok_l &
    momentum_ok_l  &
    ~is_panic
)

short_signal = (
    TRADE_SHORTS   &
    short_pb       &
    ema_bear       &
    ema_slope_down &
    rsi_falling    &
    rsi_short_ok   &
    vol_ok         &
    atr_floor_ok   &
    is_trending    &
    adx_rising     &
    di_spread_ok_s &
    momentum_ok_s  &
    ~is_panic
)

# ─── Signal filter pass-through diagnostics ───────────────────────────────────
components_long = [
    ("long_pb",        long_pb),
    ("ema_bull",       ema_bull),
    ("ema_slope_up",   ema_slope_up),
    ("rsi_rising",     rsi_rising),
    ("rsi_long_ok",    rsi_long_ok),
    ("vol_ok",         vol_ok),
    ("atr_floor_ok",   atr_floor_ok),
    ("is_trending",    is_trending),
    ("adx_rising",     adx_rising),
    ("di_spread_ok",   di_spread_ok_l),
    ("momentum_ok",    momentum_ok_l),
    ("~is_panic",      ~is_panic),
]
components_short = [
    ("short_pb",       short_pb),
    ("ema_bear",       ema_bear),
    ("ema_slope_down", ema_slope_down),
    ("rsi_falling",    rsi_falling),
    ("rsi_short_ok",   rsi_short_ok),
    ("vol_ok",         vol_ok),
    ("atr_floor_ok",   atr_floor_ok),
    ("is_trending",    is_trending),
    ("adx_rising",     adx_rising),
    ("di_spread_ok",   di_spread_ok_s),
    ("momentum_ok",    momentum_ok_s),
    ("~is_panic",      ~is_panic),
]

print("\n--- Signal filter pass-through (long) ---")
cum = pd.Series([True] * len(df), index=df.index)
for name, mask in components_long:
    cum = cum & mask
    print(f"  {name:<20} → {cum.sum():>4} rows pass")
print("--- Signal filter pass-through (short) ---")
cum = pd.Series([True] * len(df), index=df.index)
for name, mask in components_short:
    cum = cum & mask
    print(f"  {name:<20} → {cum.sum():>4} rows pass")

print(f"\nv4.2 Signals — Long: {long_signal.sum()}  Short: {short_signal.sum()}")

# ─── Alert helpers ─────────────────────────────────────────────────────────────
def _al(lines): return "\n".join(lines)

def entry_alert(direction, ts, cl, av, sd, qty, equity_at_entry, row):
    sl  = cl - sd if direction == "long" else cl + sd
    tp  = cl + av * TP_MULT if direction == "long" else cl - av * TP_MULT
    rr  = TP_MULT / SL_MULT
    dl  = "LONG" if direction == "long" else "SHORT"
    rb  = f"{RSI_LO_L}-{RSI_HI_L}" if direction == "long" else f"{RSI_LO_S}-{RSI_HI_S}"
    rdir  = "Rising" if direction == "long" else "Falling"
    stk   = "BULL"   if direction == "long" else "BEAR"
    slp   = "UP"     if direction == "long" else "DOWN"
    ss    = "-"  if direction == "long" else "+"
    ts_   = "+"  if direction == "long" else "-"
    body_v = abs(float(row["Close"]) - float(row["Open"])) / av
    return _al([
        f"APM v4.2-CLM | {dl} ENTRY | {TICKER} [{INTERVAL}]",
        f"Entry   : {cl:.4f}  |  Equity: ${equity_at_entry:.2f}",
        f"Stop    : {sl:.4f}  ({ss}{sd:.4f} = ATR×{SL_MULT})",
        f"Target  : {tp:.4f}  ({ts_}{av*TP_MULT:.4f} = ATR×{TP_MULT})",
        f"R:R     : 1:{rr:.2f}  |  Risk: ${equity_at_entry*RISK_PCT:.2f} ({RISK_PCT*100:.1f}%)",
        f"Qty     : {qty:.2f}",
        f"ATR     : {av:.4f} ({av/cl*100:.3f}% of price)",
        f"RSI     : {float(row['RSI']):.2f} [{rb}]  Dir: {rdir}",
        f"ADX     : {float(row['ADX']):.2f}  DI+: {float(row['DI_PLUS']):.2f}  DI-: {float(row['DI_MINUS']):.2f}  [min {ADX_THRESH}↑]",
        f"Vol/MA  : {float(row['Volume'])/float(row['VOL_MA']):.2f}×  [min {VOL_MULT}×]",
        f"Body    : {body_v:.3f}×ATR  [min {MIN_BODY}×]",
        f"EMA{EMA_FAST}/{EMA_MID}/{EMA_SLOW}: {float(row['EMA_FAST']):.4f}/{float(row['EMA_MID']):.4f}/{float(row['EMA_SLOW']):.4f}  Stack: {stk}  Slope: {slp}",
        f"Time    : {ts}",
    ])

def exit_alert(direction, ep, xp, dp, bars_held, equity_after,
               closed_count, win_count, ts):
    dl  = "LONG" if direction == "long" else "SHORT"
    res = "WIN"  if dp >= 0 else "LOSS"
    mv  = ((xp-ep)/ep*100) if direction == "long" else ((ep-xp)/ep*100)
    wr  = f"{win_count/closed_count*100:.1f}%" if closed_count else "--"
    ps  = "+" if dp >= 0 else ""
    ms  = "+" if mv >= 0 else ""
    return _al([
        f"APM v4.2-CLM | {dl} EXIT [{res}] | {TICKER} [{INTERVAL}]",
        f"Entry  : {ep:.4f}  →  Exit: {xp:.4f}",
        f"Move   : {ms}{mv:.3f}%",
        f"P&L    : {ps}{dp:.2f} USD",
        f"Bars   : {bars_held}  |  Equity: ${equity_after:.2f}",
        f"Trades : {closed_count}  |  Win rate: {wr}",
        f"Time   : {ts}",
    ])

# ─── Bar-by-bar simulation ────────────────────────────────────────────────────
bar_index     = {t: i for i, t in enumerate(df.index)}
equity        = INITIAL_CAPITAL
pos           = None
trades        = []
alerts        = []
eqcurve       = []
closed_count  = 0
win_count     = 0
consec_losses = 0
cooldown_bars = 0

for ts, row in df.iterrows():
    close = float(row["Close"]); high = float(row["High"])
    low   = float(row["Low"]);   atr  = float(row["ATR"])
    sd    = atr * SL_MULT

    htp = hsl = False

    if pos is not None:
        d = pos["direction"]
        if d == "long":
            if high > pos["best"]:
                pos["best"] = high
            if pos["best"] >= pos["trail_activate_px"]:
                pos["sl"] = max(pos["sl"], pos["best"] - pos["trail_dist_fixed"])
            htp = high >= pos["tp"]
            hsl = low  <= pos["sl"]
        else:  # short
            if low < pos["best"]:
                pos["best"] = low
            if pos["best"] <= pos["trail_activate_px"]:
                pos["sl"] = min(pos["sl"], pos["best"] + pos["trail_dist_fixed"])
            htp = low  <= pos["tp"]
            hsl = high >= pos["sl"]

    if htp or hsl:
        d   = pos["direction"]
        xp  = pos["tp"] if htp else pos["sl"]
        pnl = ((xp - pos["entry"]) / pos["entry"] if d == "long"
               else (pos["entry"] - xp) / pos["entry"])
        dp  = pnl * pos["notional"] - pos["notional"] * COMMISSION_PCT * 2
        equity      += dp
        closed_count += 1
        if dp > 0: win_count += 1

        # Enhancement: post-TP mandatory cooldown (prevents immediate re-entry chop)
        if htp:
            cooldown_bars = max(cooldown_bars, TP_COOLDOWN_BARS)
            consec_losses = 0
        else:  # SL — consecutive loss cooldown
            consec_losses += 1
            if consec_losses >= CONSEC_LOSS_LIMIT:
                cooldown_bars = max(cooldown_bars, CONSEC_LOSS_COOLDOWN)
                consec_losses = 0

        bars_held = bar_index[ts] - bar_index[pos["entry_time"]]
        trades.append({
            "entry_time": pos["entry_time"],
            "exit_time":  ts,
            "direction":  d,
            "entry":      pos["entry"],
            "exit":       xp,
            "result":     "TP" if htp else "SL",
            "pnl_pct":    round(pnl * 100, 3),
            "dollar_pnl": round(dp, 2),
            "equity":     round(equity, 2),
        })
        alerts.append((ts, "EXIT", exit_alert(
            d, pos["entry"], xp, dp, bars_held, equity,
            closed_count, win_count, ts)))
        pos = None

    if pos is None:
        if cooldown_bars > 0:
            cooldown_bars -= 1
        else:
            sig = ("long"  if bool(long_signal[ts])  else
                   "short" if bool(short_signal[ts]) else None)
            if sig:
                notl = min(equity * RISK_PCT / sd * close, equity * 5.0)
                sl   = close - sd if sig == "long" else close + sd
                tp   = (close + atr * TP_MULT if sig == "long"
                        else close - atr * TP_MULT)
                tap  = (close + atr * TRAIL_ACT if sig == "long"
                        else close - atr * TRAIL_ACT)
                qty  = notl / close
                pos  = {
                    "direction":         sig,
                    "entry":             close,
                    "entry_time":        ts,
                    "sl":                sl,
                    "tp":                tp,
                    "best":              close,
                    "notional":          notl,
                    "trail_activate_px": tap,
                    "trail_dist_fixed":  atr * TRAIL_DIST,
                }
                alerts.append((ts, "ENTRY", entry_alert(
                    sig, ts, close, atr, sd, qty, equity, row)))

    eqcurve.append({"time": ts, "equity": equity})

print(f"\nSimulation complete. Trades: {len(trades)}")

# ─── Statistics ───────────────────────────────────────────────────────────────
tdf = pd.DataFrame(trades)

if tdf.empty:
    print("No trades — consider relaxing a filter.")
    sys.exit(0)

wins   = tdf[tdf["dollar_pnl"] > 0]
losses = tdf[tdf["dollar_pnl"] <= 0]
final  = tdf["equity"].iloc[-1]
total  = tdf["dollar_pnl"].sum()
wr     = len(wins) / len(tdf) * 100
gp     = wins["dollar_pnl"].sum()   if not wins.empty   else 0.0
gl     = losses["dollar_pnl"].sum() if not losses.empty else 0.0
pf     = gp / abs(gl) if gl != 0 else float("inf")
tp_cnt = (tdf["result"] == "TP").sum()
sl_cnt = (tdf["result"] == "SL").sum()
long_c = (tdf["direction"] == "long").sum()
shrt_c = (tdf["direction"] == "short").sum()
aw     = wins["dollar_pnl"].mean()   if not wins.empty   else 0.0
al     = losses["dollar_pnl"].mean() if not losses.empty else 0.0
rr     = aw / abs(al) if al != 0 else float("inf")
ret    = (final / INITIAL_CAPITAL - 1) * 100

eq_s = pd.Series([e["equity"] for e in eqcurve])
mdd  = ((eq_s - eq_s.cummax()) / eq_s.cummax() * 100).min()

print("=" * 60)
print(f"  APM v4.2 (CLM-tuned)  —  {TICKER} {INTERVAL}  ({PERIOD})")
print("=" * 60)
print(f"  Initial capital   :  ${INITIAL_CAPITAL:>10,.2f}")
print(f"  Final equity      :  ${final:>10,.2f}")
print(f"  Net P&L           : ${total:>+11,.2f}")
print(f"  Return            : {ret:>+10.2f} %")
print(f"  Max drawdown      : {mdd:>10.2f} %")
print(f"  Profit factor     : {pf:>10.3f}")
print("-" * 60)
print(f"  Total trades      : {len(tdf):>5}")
print(f"    Long  trades    : {long_c:>5}")
print(f"    Short trades    : {shrt_c:>5}")
print(f"  TP exits          : {tp_cnt:>5}")
print(f"  SL exits          : {sl_cnt:>5}")
print(f"  Win rate          : {wr:>9.1f} %")
print(f"  Avg win           :  ${aw:>+9,.2f}")
print(f"  Avg loss          :  ${al:>+9,.2f}")
print(f"  Avg R:R           : {rr:>10.2f}")
print(f"  Best trade        :  ${tdf['dollar_pnl'].max():>+9,.2f}")
print(f"  Worst trade       :  ${tdf['dollar_pnl'].min():>+9,.2f}")
print("=" * 60)

for direction in ["long", "short"]:
    sub = tdf[tdf["direction"] == direction]
    if sub.empty:
        continue
    sw   = sub[sub["dollar_pnl"] > 0]
    sl_  = sub[sub["dollar_pnl"] <= 0]
    sub_wr  = len(sw) / len(sub) * 100
    sub_pnl = sub["dollar_pnl"].sum()
    sub_pf  = (sw["dollar_pnl"].sum() / abs(sl_["dollar_pnl"].sum())
               if not sl_.empty else float("inf"))
    print(f"  {direction.upper():<6} trades={len(sub):>3}  WR={sub_wr:.0f}%  "
          f"PF={sub_pf:.3f}  net=${sub_pnl:+.2f}")

out_csv = f"apm_v4_trades_{TICKER.lower()}_{INTERVAL}.csv"
tdf.to_csv(out_csv, index=False)
print(f"\nTrades CSV → {out_csv}")

# ─── Alerts log ───────────────────────────────────────────────────────────────
SEP = "-" * 70
alert_out = f"apm_v4_alerts_{TICKER.lower()}_{INTERVAL}.txt"
with open(alert_out, "w") as f:
    for ts, atype, msg in alerts:
        f.write(SEP + "\n" + msg + "\n")
    f.write(SEP + "\n")
entry_cnt = sum(1 for _, t, _ in alerts if t == "ENTRY")
exit_cnt  = sum(1 for _, t, _ in alerts if t == "EXIT")
print(f"Alerts (entries={entry_cnt}  exits={exit_cnt}) → {alert_out}")

print("\n── Alert preview (first 2 entries + 2 exits) ──")
shown_e = shown_x = 0
for ts, atype, msg in alerts:
    if atype == "ENTRY" and shown_e < 2:
        print(SEP); print(msg); shown_e += 1
    elif atype == "EXIT"  and shown_x < 2:
        print(SEP); print(msg); shown_x += 1
    if shown_e >= 2 and shown_x >= 2:
        break

# ─── Charts ───────────────────────────────────────────────────────────────────
ec_df = pd.DataFrame(eqcurve).set_index("time")
plt.style.use("dark_background")

fig, axes = plt.subplots(3, 1, figsize=(18, 14),
                         gridspec_kw={"height_ratios": [3, 1.5, 1.5]})
fig.suptitle(
    f"APM v4.2 (CLM-tuned)  ·  {TICKER} {INTERVAL}  ·  "
    f"ADX>{ADX_THRESH}↑  DI>{DI_SPREAD_MIN}  Mom{MOMENTUM_BARS}b  |  "
    f"SL×{SL_MULT} TP×{TP_MULT}  Return={ret:+.2f}%  PF={pf:.3f}",
    fontsize=11)

# Panel 1 — price + EMAs + trade markers
ax1 = axes[0]
ax1.plot(df.index, df["Close"],    color="#cccccc", lw=0.7, label="Close")
ax1.plot(df.index, df["EMA_SLOW"], color="#f6e05e", lw=2.0, label=f"EMA {EMA_SLOW}")
ax1.plot(df.index, df["EMA_MID"],  color="#f6ad55", lw=1.0, ls="--", alpha=0.8, label=f"EMA {EMA_MID}")
ax1.plot(df.index, df["EMA_FAST"], color="#5b9ef4", lw=1.0, ls="--", alpha=0.8, label=f"EMA {EMA_FAST}")

for _, t in tdf.iterrows():
    mrkr  = "^" if t["direction"] == "long"  else "v"
    e_col = "#68d391" if t["direction"] == "long" else "#fc8181"
    w_col = "#68d391" if t["dollar_pnl"] >= 0     else "#fc8181"
    ax1.scatter(t["entry_time"], t["entry"], marker=mrkr, color=e_col, s=70, zorder=5)
    ax1.scatter(t["exit_time"],  t["exit"],  marker="x",  color=w_col, s=50, zorder=5)

ax1.set_ylabel("Price")
ax1.legend(loc="upper left", fontsize=8)
ax1.grid(alpha=0.15)
ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))

# Panel 2 — equity curve
eq_col = "#68d391" if ec_df["equity"].iloc[-1] >= INITIAL_CAPITAL else "#fc8181"
ax2 = axes[1]
ax2.plot(ec_df.index, ec_df["equity"], color=eq_col, lw=1.5)
ax2.axhline(INITIAL_CAPITAL, color="white", ls=":", lw=0.8, alpha=0.5)
ax2.fill_between(ec_df.index, INITIAL_CAPITAL, ec_df["equity"],
                 where=(ec_df["equity"] >= INITIAL_CAPITAL), alpha=0.2, color="#68d391")
ax2.fill_between(ec_df.index, INITIAL_CAPITAL, ec_df["equity"],
                 where=(ec_df["equity"] < INITIAL_CAPITAL), alpha=0.2, color="#fc8181")
ax2.set_ylabel("Equity ($)")
ax2.grid(alpha=0.15)
ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))

# Panel 3 — per-trade P&L bars
ax3 = axes[2]
bar_c = ["#68d391" if v >= 0 else "#fc8181" for v in tdf["dollar_pnl"]]
ax3.bar(range(len(tdf)), tdf["dollar_pnl"], color=bar_c, width=0.6)
ax3.axhline(0, color="white", lw=0.7, alpha=0.5)
ax3.set_xticks(range(len(tdf)))
ax3.set_xticklabels([f"T{i+1}\n{r}" for i, r in enumerate(tdf["result"])], fontsize=7)
ax3.set_ylabel("P&L ($)")
ax3.grid(alpha=0.15)

plt.tight_layout()
out_png = f"apm_v4_equity_{TICKER.lower()}_{INTERVAL}.png"
plt.savefig(out_png, dpi=150, bbox_inches="tight")
print(f"Chart → {out_png}")
