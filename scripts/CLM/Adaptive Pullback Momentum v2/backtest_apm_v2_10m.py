# ─────────────────────────────────────────────────────────────────────────────
# APM v2.0 — CLM 10m backtest
# Mirrors "Adaptive Pullback Momentum v2.0" pine script parameters exactly.
# Shorts-only by default (same thesis as v1: longs at sub-15m WR too low).
#
# Data: yfinance 5m → resampled to 10m (yfinance has no native 10m interval)
# Period: 60d (max intraday window available from yfinance)
#
# v2.1 Stage-1 sweep (sweep_stage1_results.csv, 7416 combos — best by PF@≥8 trades):
#   ADX=20 | vol=0.7 | session_end=14 | adx_slope=0 (off) | di_spread=0 (off) | pb=0.30
#   tp=3.0 | sl=2.0
#   Result (10 trades): PF=7.785 | net=+9.01% | WR=90.0% | MaxDD=-1.31% | Calmar=6.865
#
# v2.2 Stage-2 sweep (sweep_stage2.py, 768 combos — best by Calmar):
#   panic=1.5 | tp=4.0 | sl=2.0 | max_bars=25 (NEW)
#   Result (11 trades): PF=63.604 | net=+9.75% | WR=90.9% | MaxDD=-0.15% | Calmar=63.653
#   Key insight: max_bars=25 cuts stalled trades before reversal → near-zero drawdown
#
# v2.3 Stage-3 sweep (sweep_stage3.py, 625 combos — best by net%):
#   trail_act=3.5 | trail_dist=0.3 | tp=6.0 | max_bars=30
#   Result (11 trades): PF=59.634 | net=+18.67% | WR=90.9% | MaxDD=-0.31% | Calmar=59.706
#   Key insight: late trail activation (3.5×ATR) + tight dist (0.3×ATR) + wider TP (6.0) → 2× return
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
PERIOD   = "60d"    # max intraday window from yfinance; 5m data resampled → 10m
INTERVAL = "10m"    # logical timeframe (data sourced as 5m and resampled)

EMA_FAST = 21
EMA_MID  = 50
EMA_SLOW = 200
ADX_LEN  = 14
RSI_LEN  = 14
ATR_LEN  = 14
VOL_LEN  = 20

# ── Strategy parameters (v2.2 sweep-optimised for CLM 10m) ──────────────────
PB_PCT      = 0.30    # stage1: wider pullback tolerance (was 0.15)
ADX_THRESH  = 20      # stage1: looser ADX threshold (was 28)
VOL_MULT    = 0.7     # stage1: loosened volume filter (was 1.2)
MIN_BODY    = 0.15    # body filter (unchanged)
ATR_FLOOR   = 0.0015  # 0.15% of price — low-vol filter (unchanged)
PANIC_MULT  = 1.5     # stage2: loosened panic filter (was 1.3)

RSI_LO_L = 42;  RSI_HI_L = 68   # long RSI band (unchanged)
RSI_LO_S = 32;  RSI_HI_S = 58   # short RSI band (unchanged)

SL_MULT    = 2.0    # stop   = entry ± ATR × SL_MULT (unchanged)
TP_MULT    = 6.0    # stage3: wider TP (4.0 → 6.0; let runners go)
TRAIL_ACT  = 3.5    # stage3: later trail activation (2.5 → 3.5×ATR) — let trade breathe
TRAIL_DIST = 0.3    # stage3: tighter trail (0.6 → 0.3×ATR) — lock gains quickly once active
MAX_BARS_IN_TRADE = 30  # stage3: slightly longer MB exit window (25 → 30)

RISK_PCT   = 0.01           # 1% equity per trade
INITIAL_CAPITAL = 10_000.0
COMMISSION_PCT  = 0.0006    # 0.06% per side

TRADE_LONGS  = False   # CLM sub-15m longs: WR too low (noise dominates)
TRADE_SHORTS = True

# ── Enhancement #1: Session filter — morning/midday session ──────────────────
SESSION_START_ET = 9
SESSION_END_ET   = 14   # stage1: extended to 14:00 ET (was 12)

# ── Enhancement #2: DI spread — bear dominance for shorts ─────────────────────
DI_SPREAD_MIN = 0.0    # stage1: disabled (was 5.0) — DI spread hurts entries

# ── Enhancement #3: ADX slope — accelerating trend ────────────────────────────
ADX_SLOPE_BARS = 0     # stage1: disabled (was 2) — slope filter not beneficial
EMA_SLOPE_BARS = 0     # stage1: EMA fast slope filter off (was 3) — limits good entries

# ── Enhancement #4: 5-bar momentum — close below close 5 bars ago (shorts) ───
MOMENTUM_BARS = 5

# ── Enhancement #5: Consecutive loss cooldown ─────────────────────────────────
CONSEC_LOSS_LIMIT    = 2   # trigger cooldown after N consecutive SL exits
CONSEC_LOSS_COOLDOWN = 1   # signals to skip during cooldown

# ─── Download (5m → resample to 10m) ──────────────────────────────────────────
print(f"Downloading {TICKER} 5m (period='{PERIOD}') → resampling to 10m ...")
raw = yf.download(TICKER, period=PERIOD, interval="5m", auto_adjust=True, progress=False)
if raw.empty:
    raise SystemExit(f"No data returned for {TICKER} 5m.")
if isinstance(raw.columns, pd.MultiIndex):
    raw.columns = raw.columns.droplevel(1)
raw = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
raw = raw[raw["Volume"] > 0].copy()
raw.dropna(inplace=True)

# Resample 5m → 10m (anchor to 9:30 ET so bars align with session open)
_ET = pytz.timezone("America/New_York")
raw.index = pd.to_datetime(raw.index)
if raw.index.tzinfo is None:
    raw.index = raw.index.tz_localize("UTC")
raw_et = raw.copy()
raw_et.index = raw_et.index.tz_convert(_ET)

df = raw_et.resample("10min", label="left", closed="left", origin="start_day").agg(
    {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
).dropna()
# Keep only bars that have data (non-zero volume after resample)
df = df[df["Volume"] > 0].copy()
print(f"5m rows: {len(raw)}  →  10m bars: {len(df)}  |  {df.index[0]} → {df.index[-1]}")

# ─── Indicators ───────────────────────────────────────────────────────────────
df["EMA_FAST"] = df["Close"].ewm(span=EMA_FAST, adjust=False).mean()
df["EMA_MID"]  = df["Close"].ewm(span=EMA_MID,  adjust=False).mean()
df["EMA_SLOW"] = df["Close"].ewm(span=EMA_SLOW, adjust=False).mean()

delta  = df["Close"].diff()
avg_g  = delta.clip(lower=0).ewm(alpha=1 / RSI_LEN, adjust=False).mean()
avg_l  = (-delta).clip(lower=0).ewm(alpha=1 / RSI_LEN, adjust=False).mean()
df["RSI"] = 100 - (100 / (1 + avg_g / avg_l.replace(0, 1e-10)))

hl  = df["High"] - df["Low"]
hpc = (df["High"] - df["Close"].shift(1)).abs()
lpc = (df["Low"]  - df["Close"].shift(1)).abs()
tr  = pd.concat([hl, hpc, lpc], axis=1).max(axis=1)
df["ATR"]    = tr.ewm(alpha=1 / ATR_LEN, adjust=False).mean()
df["ATR_BL"] = df["ATR"].rolling(60).mean()

df["VOL_MA"] = df["Volume"].rolling(VOL_LEN).mean()

up_move  = df["High"] - df["High"].shift(1)
dn_move  = df["Low"].shift(1) - df["Low"]
plus_dm  = np.where((up_move > dn_move) & (up_move > 0), up_move, 0.0)
minus_dm = np.where((dn_move > up_move) & (dn_move > 0), dn_move, 0.0)
s_plus   = pd.Series(plus_dm,  index=df.index).ewm(alpha=1 / ADX_LEN, adjust=False).mean()
s_minus  = pd.Series(minus_dm, index=df.index).ewm(alpha=1 / ADX_LEN, adjust=False).mean()
df["DI_PLUS"]  = 100 * s_plus  / df["ATR"].replace(0, 1e-10)
df["DI_MINUS"] = 100 * s_minus / df["ATR"].replace(0, 1e-10)
dx = 100 * (df["DI_PLUS"] - df["DI_MINUS"]).abs() / (
    (df["DI_PLUS"] + df["DI_MINUS"]).replace(0, 1e-10))
df["ADX"] = dx.ewm(alpha=1 / ADX_LEN, adjust=False).mean()

df.dropna(inplace=True)

# ET hour for session filter (index is already in ET after resample)
df["ET_HOUR"] = df.index.hour
df.dropna(inplace=True)

# ─── Signal components ────────────────────────────────────────────────────────
tol = PB_PCT / 100.0

is_trending = df["ADX"] > ADX_THRESH
is_panic    = df["ATR"] > df["ATR_BL"] * PANIC_MULT

ema_bull = (df["EMA_FAST"] > df["EMA_MID"]) & (df["EMA_MID"] > df["EMA_SLOW"])
ema_bear = (df["EMA_FAST"] < df["EMA_MID"]) & (df["EMA_MID"] < df["EMA_SLOW"])

ema_slope_up   = pd.Series(True, index=df.index) if EMA_SLOPE_BARS == 0 \
             else df["EMA_FAST"] > df["EMA_FAST"].shift(EMA_SLOPE_BARS)
ema_slope_down = pd.Series(True, index=df.index) if EMA_SLOPE_BARS == 0 \
             else df["EMA_FAST"] < df["EMA_FAST"].shift(EMA_SLOPE_BARS)

pb_tol_up = df["EMA_FAST"].shift(1) * (1.0 + tol)
pb_tol_dn = df["EMA_FAST"].shift(1) * (1.0 - tol)
long_pullback  = df["Low"].shift(1)  <= pb_tol_up
short_pullback = df["High"].shift(1) >= pb_tol_dn

long_recover  = (df["Close"] > df["EMA_FAST"]) & (df["Close"] > df["Open"])
short_recover = (df["Close"] < df["EMA_FAST"]) & (df["Close"] < df["Open"])

body       = (df["Close"] - df["Open"]).abs() / df["ATR"].replace(0, 1e-10)
body_ok    = body >= MIN_BODY

rsi_rising  = df["RSI"] > df["RSI"].shift(1)
rsi_falling = df["RSI"] < df["RSI"].shift(1)

rsi_long_ok  = (df["RSI"] >= RSI_LO_L) & (df["RSI"] <= RSI_HI_L)
rsi_short_ok = (df["RSI"] >= RSI_LO_S) & (df["RSI"] <= RSI_HI_S)

vol_ok       = df["Volume"] >= df["VOL_MA"] * VOL_MULT
atr_floor_ok = df["ATR"] / df["Close"] >= ATR_FLOOR

# Enhancement #1: Session filter
session_ok = (df["ET_HOUR"] >= SESSION_START_ET) & (df["ET_HOUR"] < SESSION_END_ET)

# Enhancement #2: DI bear dominance (shorts)
di_spread_ok_s = (df["DI_MINUS"] - df["DI_PLUS"]) >= DI_SPREAD_MIN

# Enhancement #3: Rising ADX
adx_rising = pd.Series(True, index=df.index) if ADX_SLOPE_BARS == 0 \
             else df["ADX"] > df["ADX"].shift(ADX_SLOPE_BARS)

# Enhancement #4: 5-bar momentum (shorts)
momentum_ok_s = df["Close"] < df["Close"].shift(MOMENTUM_BARS)

# ─── Final entry conditions ───────────────────────────────────────────────────
long_signal = (
    TRADE_LONGS     &
    long_pullback   &
    long_recover    &
    body_ok         &
    ema_bull        &
    ema_slope_up    &
    rsi_rising      &
    rsi_long_ok     &
    vol_ok          &
    is_trending     &
    session_ok      &
    ~is_panic       &
    atr_floor_ok
)

short_signal = (
    TRADE_SHORTS    &
    short_pullback  &
    short_recover   &
    body_ok         &
    ema_bear        &
    ema_slope_down  &
    rsi_falling     &
    rsi_short_ok    &
    vol_ok          &
    is_trending     &
    adx_rising      &
    di_spread_ok_s  &
    momentum_ok_s   &
    session_ok      &
    ~is_panic       &
    atr_floor_ok
)

# ─── Filter diagnostics ───────────────────────────────────────────────────────
print("\n--- Signal filter pass-through (short) ---")
components_short = [
    ("short_pullback",  short_pullback),
    ("short_recover",   short_recover),
    ("body_ok",         body_ok),
    ("ema_bear",        ema_bear),
    ("ema_slope_down",  ema_slope_down),
    ("rsi_falling",     rsi_falling),
    ("rsi_short_ok",    rsi_short_ok),
    ("vol_ok",          vol_ok),
    ("is_trending",     is_trending),
    ("adx_rising",      adx_rising),
    ("di_spread_ok",    di_spread_ok_s),
    ("momentum_ok",     momentum_ok_s),
    ("session_ok",      session_ok),
    ("~is_panic",       ~is_panic),
    ("atr_floor_ok",    atr_floor_ok),
]
cum = pd.Series([True] * len(df), index=df.index)
for name, mask in components_short:
    cum = cum & mask
    print(f"  {name:<20} → {cum.sum():>4} rows pass")

print(f"\nv2.0 Signals — Long: {long_signal.sum()}  Short: {short_signal.sum()}")

# ─── Bar-by-bar simulation ────────────────────────────────────────────────────
equity        = INITIAL_CAPITAL
pos           = None
trades        = []
eqcurve       = []
consec_losses = 0
cooldown_bars = 0
bars_in_trade = 0

for ts, row in df.iterrows():
    close = float(row["Close"]); high = float(row["High"])
    low   = float(row["Low"]);   atr  = float(row["ATR"])
    if atr == 0 or np.isnan(atr):
        eqcurve.append({"time": ts, "equity": equity})
        continue
    sd = atr * SL_MULT

    if pos is not None:
        bars_in_trade += 1
        if pos["direction"] == "short":
            if low < pos["best"]:
                pos["best"] = low
            # Trailing stop update
            if pos["best"] <= pos["trail_activate_px"]:
                pos["sl"] = min(pos["sl"], pos["best"] + pos["trail_dist_fixed"])

            # Max bars exit
            if MAX_BARS_IN_TRADE > 0 and bars_in_trade >= MAX_BARS_IN_TRADE:
                xp      = close
                pnl_pct = (pos["entry"] - xp) / pos["entry"]
                dp      = pnl_pct * pos["notional"] - pos["notional"] * COMMISSION_PCT * 2
                equity += dp
                if dp <= 0:
                    consec_losses += 1
                    if consec_losses >= CONSEC_LOSS_LIMIT:
                        cooldown_bars = CONSEC_LOSS_COOLDOWN; consec_losses = 0
                else:
                    consec_losses = 0
                trades.append({"entry_time": pos["entry_time"], "exit_time": ts,
                               "direction": "short", "entry": pos["entry"], "exit": xp,
                               "result": "MB", "pnl_pct": round(pnl_pct*100,3),
                               "dollar_pnl": round(dp,2), "equity": round(equity,2)})
                pos = None; bars_in_trade = 0; eqcurve.append({"time": ts, "equity": equity}); continue

            htp = low  <= pos["tp"]
            hsl = high >= pos["sl"]

            if htp or hsl:
                xp      = pos["tp"] if htp else pos["sl"]
                pnl_pct = (pos["entry"] - xp) / pos["entry"]
                dp      = pnl_pct * pos["notional"] - pos["notional"] * COMMISSION_PCT * 2
                equity += dp
                result  = "TP" if htp else "SL"

                if dp <= 0:
                    consec_losses += 1
                    if consec_losses >= CONSEC_LOSS_LIMIT:
                        cooldown_bars = CONSEC_LOSS_COOLDOWN
                        consec_losses = 0
                else:
                    consec_losses = 0

                trades.append({
                    "entry_time": pos["entry_time"],
                    "exit_time":  ts,
                    "direction":  "short",
                    "entry":      pos["entry"],
                    "exit":       xp,
                    "result":     result,
                    "pnl_pct":    round(pnl_pct * 100, 3),
                    "dollar_pnl": round(dp, 2),
                    "equity":     round(equity, 2),
                })
                pos = None; bars_in_trade = 0

        else:  # long
            if high > pos["best"]:
                pos["best"] = high
            if pos["best"] >= pos["trail_activate_px"]:
                pos["sl"] = max(pos["sl"], pos["best"] - pos["trail_dist_fixed"])

            htp = high >= pos["tp"]
            hsl = low  <= pos["sl"]

            if htp or hsl:
                xp      = pos["tp"] if htp else pos["sl"]
                pnl_pct = (xp - pos["entry"]) / pos["entry"]
                dp      = pnl_pct * pos["notional"] - pos["notional"] * COMMISSION_PCT * 2
                equity += dp
                result  = "TP" if htp else "SL"

                if dp <= 0:
                    consec_losses += 1
                    if consec_losses >= CONSEC_LOSS_LIMIT:
                        cooldown_bars = CONSEC_LOSS_COOLDOWN
                        consec_losses = 0
                else:
                    consec_losses = 0

                trades.append({
                    "entry_time": pos["entry_time"],
                    "exit_time":  ts,
                    "direction":  "long",
                    "entry":      pos["entry"],
                    "exit":       xp,
                    "result":     result,
                    "pnl_pct":    round(pnl_pct * 100, 3),
                    "dollar_pnl": round(dp, 2),
                    "equity":     round(equity, 2),
                })
                pos = None; bars_in_trade = 0

    if pos is None:
        if cooldown_bars > 0:
            cooldown_bars -= 1
        else:
            if bool(short_signal.get(ts, False)):
                notl = min(equity * RISK_PCT / sd * close, equity * 5.0)
                pos  = {
                    "direction":         "short",
                    "entry":             close,
                    "entry_time":        ts,
                    "sl":                close + sd,
                    "tp":                close - atr * TP_MULT,
                    "best":              close,
                    "notional":          notl,
                    "trail_activate_px": close - atr * TRAIL_ACT,
                    "trail_dist_fixed":  atr * TRAIL_DIST,
                }
                bars_in_trade = 0
            elif bool(long_signal.get(ts, False)):
                notl = min(equity * RISK_PCT / sd * close, equity * 5.0)
                pos  = {
                    "direction":         "long",
                    "entry":             close,
                    "entry_time":        ts,
                    "sl":                close - sd,
                    "tp":                close + atr * TP_MULT,
                    "best":              close,
                    "notional":          notl,
                    "trail_activate_px": close + atr * TRAIL_ACT,
                    "trail_dist_fixed":  atr * TRAIL_DIST,
                }
                bars_in_trade = 0

    eqcurve.append({"time": ts, "equity": equity})

print(f"\nSimulation complete. Trades: {len(trades)}")

# ─── Statistics ───────────────────────────────────────────────────────────────
tdf = pd.DataFrame(trades)

if tdf.empty:
    print("No trades — consider relaxing a filter.")
    sys.exit(0)

wins    = tdf[tdf["dollar_pnl"] > 0]
losses  = tdf[tdf["dollar_pnl"] <= 0]
final   = tdf["equity"].iloc[-1]
total   = tdf["dollar_pnl"].sum()
wr      = len(wins) / len(tdf) * 100
gp      = wins["dollar_pnl"].sum()   if not wins.empty   else 0.0
gl      = losses["dollar_pnl"].sum() if not losses.empty else 0.0
pf      = gp / abs(gl) if gl != 0 else float("inf")
tp_cnt  = (tdf["result"] == "TP").sum()
sl_cnt  = (tdf["result"] == "SL").sum()
long_c  = (tdf["direction"] == "long").sum()
shrt_c  = (tdf["direction"] == "short").sum()
aw      = wins["dollar_pnl"].mean()   if not wins.empty   else 0.0
al      = losses["dollar_pnl"].mean() if not losses.empty else 0.0
rr      = aw / abs(al) if al != 0 else float("inf")
ret     = (final / INITIAL_CAPITAL - 1) * 100

eq_s = pd.Series([e["equity"] for e in eqcurve])
mdd  = ((eq_s - eq_s.cummax()) / eq_s.cummax() * 100).min()

print("=" * 60)
print(f"  APM v2.0  —  {TICKER} {INTERVAL}  ({PERIOD})")
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

out_csv = f"apm_v2_trades_{TICKER.lower()}_{INTERVAL}.csv"
tdf.to_csv(out_csv, index=False)
print(f"\nTrades CSV → {out_csv}")

# ─── Alert log ────────────────────────────────────────────────────────────────
alert_lines = []
for _, t in tdf.iterrows():
    sign   = "SHORT" if t["direction"] == "short" else "LONG"
    result = t["result"]
    dp     = t["dollar_pnl"]
    alert_lines.append(
        f"APM v2.0 | {sign} {result} | {TICKER} [{INTERVAL}]\n"
        f"Entry   : {t['entry']:.2f}  Exit: {t['exit']:.2f}\n"
        f"P&L     : ${dp:+.2f}  ({t['pnl_pct']:+.3f}%)\n"
        f"Entry time: {t['entry_time']}  Exit time: {t['exit_time']}\n"
    )
out_txt = f"apm_v2_alerts_{TICKER.lower()}_{INTERVAL}.txt"
with open(out_txt, "w") as f:
    f.write(("\n" + "-" * 60 + "\n").join(alert_lines))
print(f"Alerts log  → {out_txt}")

# ─── Charts ───────────────────────────────────────────────────────────────────
ec_df = pd.DataFrame(eqcurve).set_index("time")
plt.style.use("dark_background")

fig, axes = plt.subplots(3, 1, figsize=(18, 14),
                         gridspec_kw={"height_ratios": [3, 1.5, 1.5]})
fig.suptitle(
    f"APM v2.0  ·  {TICKER} {INTERVAL}  ·  "
    f"ADX>{ADX_THRESH}↑  DI>{DI_SPREAD_MIN}  Mom{MOMENTUM_BARS}b  Session 09:30–12:00 ET  |  "
    f"SL×{SL_MULT} TP×{TP_MULT}  Return={ret:+.2f}%  PF={pf:.3f}",
    fontsize=10)

ax1 = axes[0]
ax1.plot(df.index, df["Close"],    color="#cccccc", lw=0.6, label="Close")
ax1.plot(df.index, df["EMA_SLOW"], color="#f6e05e", lw=1.8, label=f"EMA{EMA_SLOW}")
ax1.plot(df.index, df["EMA_MID"],  color="#f6ad55", lw=1.0, ls="--", alpha=0.8, label=f"EMA{EMA_MID}")
ax1.plot(df.index, df["EMA_FAST"], color="#5b9ef4", lw=1.0, ls="--", alpha=0.8, label=f"EMA{EMA_FAST}")
for _, t in tdf.iterrows():
    mrkr  = "^" if t["direction"] == "long" else "v"
    e_col = "#68d391" if t["direction"] == "long" else "#fc8181"
    w_col = "#68d391" if t["dollar_pnl"] >= 0 else "#fc8181"
    ax1.scatter(t["entry_time"], t["entry"], marker=mrkr, color=e_col, s=70, zorder=5)
    ax1.scatter(t["exit_time"],  t["exit"],  marker="x",  color=w_col, s=50, zorder=5)
ax1.set_ylabel("Price")
ax1.legend(loc="upper left", fontsize=8)
ax1.grid(alpha=0.15)
ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))

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

ax3 = axes[2]
bar_c = ["#68d391" if v >= 0 else "#fc8181" for v in tdf["dollar_pnl"]]
ax3.bar(range(len(tdf)), tdf["dollar_pnl"], color=bar_c, width=0.6)
ax3.axhline(0, color="white", lw=0.7, alpha=0.5)
ax3.set_xticks(range(len(tdf)))
ax3.set_xticklabels([f"T{i+1}\n{r}" for i, r in enumerate(tdf["result"])], fontsize=7)
ax3.set_ylabel("P&L ($)")
ax3.grid(alpha=0.15)

plt.tight_layout()
out_png = f"apm_v2_equity_{TICKER.lower()}_{INTERVAL}.png"
plt.savefig(out_png, dpi=150, bbox_inches="tight")
print(f"Chart → {out_png}")
