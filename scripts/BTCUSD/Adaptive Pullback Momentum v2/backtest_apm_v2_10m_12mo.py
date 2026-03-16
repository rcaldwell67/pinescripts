# ─────────────────────────────────────────────────────────────────────────────
# APM v2.7 — BTCUSD 10m  ·  12-Month Backtest  (Alpaca Crypto)
# Mirrors "Adaptive Pullback Momentum v2.7" Pine script parameters.
# Shorts-only (BTCUSD sub-15m longs: WR too low historically).
#
# Data: Alpaca Crypto 5m bars → resampled to 10m (Alpaca has no native 10m)
# Period: 2025-03-12 → 2026-03-12  (12 months)
#
# v2.7 (TP sweep — net=+23.05% | WR=46.8% | PF=1.31 | 47T | MaxDD=-13.17%):
#   adx=16 | pb=0.30 | vol=0.7 | atr_floor=0.10% | tp=6.0 | trail_dist=0.1
#   max_bars=30 | risk=2.5%
# ─────────────────────────────────────────────────────────────────────────────

import subprocess, sys
for pkg in ["alpaca-py", "pandas", "numpy", "matplotlib", "pytz", "python-dotenv"]:
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])

import pandas as pd
import numpy as np
import pytz
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import warnings
warnings.filterwarnings("ignore")

from datetime import datetime, timezone, timedelta
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from dotenv import load_dotenv
import os

_ET = pytz.timezone("America/New_York")

# ─── Alpaca credentials ────────────────────────────────────────────────────────
_env = __import__('pathlib').Path(__file__).resolve().parent.parent.parent.parent / ".env"
load_dotenv(_env)
ALPACA_KEY    = os.getenv("ALPACA_PAPER_API_KEY", "")
ALPACA_SECRET = os.getenv("ALPACA_PAPER_API_SECRET", "")

# ─── Configuration ─────────────────────────────────────────────────────────────
TICKER   = "BTC/USD"

BACKTEST_END   = datetime(2026, 3, 12, tzinfo=timezone.utc)
BACKTEST_START = datetime(2025, 3, 12, tzinfo=timezone.utc)

EMA_FAST   = 21;  EMA_MID  = 50;  EMA_SLOW = 200
ADX_LEN    = 14;  RSI_LEN  = 14;  ATR_LEN  = 14;  VOL_LEN = 20
ATR_BL_LEN = 60

# ── Strategy parameters (v2.3 Stage-3 sweep-optimised starting point) ─────────
PB_PCT         = 0.30
ADX_THRESH     = 16
ADX_SLOPE_BARS = 0       # off
DI_SPREAD_MIN  = 0.0     # off
EMA_SLOPE_BARS = 0       # off (stage-1 winner)
MOMENTUM_BARS  = 5
VOL_MULT       = 0.7
MIN_BODY       = 0.20
ATR_FLOOR      = 0.0010  # 0.10% of price
PANIC_MULT     = 1.5
RSI_LO_S = 32;  RSI_HI_S = 58
RSI_LO_L = 42;  RSI_HI_L = 68

SL_MULT    = 2.0
TP_MULT    = 6.0
TRAIL_ACT  = 3.5
TRAIL_DIST = 0.1
MAX_BARS   = 30

RISK_PCT        = 0.025
INITIAL_CAPITAL = 10_000.0
COMMISSION_PCT  = 0.0006

TRADE_LONGS  = False
TRADE_SHORTS = True

SESSION_START_ET = 9
SESSION_END_ET   = 14

CONSEC_LOSS_LIMIT    = 2
CONSEC_LOSS_COOLDOWN = 1

# ─── Download 5m data via Alpaca ───────────────────────────────────────────────
print(f"Downloading {TICKER} 5m via Alpaca  ({BACKTEST_START.date()} → {BACKTEST_END.date()}) ...")
client = CryptoHistoricalDataClient(ALPACA_KEY, ALPACA_SECRET)
TF5 = TimeFrame(5, TimeFrameUnit.Minute)
req = CryptoBarsRequest(
    symbol_or_symbols=TICKER,
    timeframe=TF5,
    start=BACKTEST_START,
    end=BACKTEST_END,
)
bars = client.get_crypto_bars(req)
raw  = bars.df.reset_index()
if isinstance(raw.columns, pd.MultiIndex):
    raw.columns = raw.columns.droplevel(0)
raw = raw.rename(columns={"timestamp": "time"}).set_index("time")
raw.index = pd.to_datetime(raw.index)
if raw.index.tzinfo is None:
    raw.index = raw.index.tz_localize("UTC")
raw = raw[["open", "high", "low", "close", "volume"]].rename(columns=str.title)
raw = raw[raw["Volume"] > 0].dropna()
print(f"  raw 5m bars: {len(raw)}")

# ─── Resample 5m → 10m ─────────────────────────────────────────────────────────
raw_et = raw.copy()
raw_et.index = raw_et.index.tz_convert(_ET)
df = raw_et.resample(
    "10min", label="left", closed="left", origin="start_day"
).agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
df = df[df["Volume"] > 0].dropna()
print(f"  10m bars: {len(df)}  |  {df.index[0]}..{df.index[-1]}")

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
df["ATR_BL"] = df["ATR"].rolling(ATR_BL_LEN).mean()
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
df["ET_HOUR"] = df.index.hour
print(f"  usable bars after warmup: {len(df)}")

# ─── Signal components ────────────────────────────────────────────────────────
tol = PB_PCT / 100.0

is_trending = df["ADX"] > ADX_THRESH
is_panic    = df["ATR"] > df["ATR_BL"] * PANIC_MULT

ema_bear = (df["EMA_FAST"] < df["EMA_MID"]) & (df["EMA_MID"] < df["EMA_SLOW"])

ema_slope_down = (pd.Series(True, index=df.index) if EMA_SLOPE_BARS == 0
                  else df["EMA_FAST"] < df["EMA_FAST"].shift(EMA_SLOPE_BARS))

pb_tol_dn     = df["EMA_FAST"].shift(1) * (1.0 - tol)
short_pullback = df["High"].shift(1) >= pb_tol_dn
short_recover  = (df["Close"] < df["EMA_FAST"]) & (df["Close"] < df["Open"])

body    = (df["Close"] - df["Open"]).abs() / df["ATR"].replace(0, 1e-10)
body_ok = body >= MIN_BODY

rsi_falling  = df["RSI"] < df["RSI"].shift(1)
rsi_short_ok = (df["RSI"] >= RSI_LO_S) & (df["RSI"] <= RSI_HI_S)

vol_ok       = df["Volume"] >= df["VOL_MA"] * VOL_MULT
atr_floor_ok = df["ATR"] / df["Close"] >= ATR_FLOOR

adx_rising = (pd.Series(True, index=df.index) if ADX_SLOPE_BARS == 0
              else df["ADX"] > df["ADX"].shift(ADX_SLOPE_BARS))
di_spread_ok_s = (df["DI_MINUS"] - df["DI_PLUS"]) >= DI_SPREAD_MIN
momentum_ok_s  = df["Close"] < df["Close"].shift(MOMENTUM_BARS)

session_ok = (df["ET_HOUR"] >= SESSION_START_ET) & (df["ET_HOUR"] < SESSION_END_ET)

short_signal = (
    TRADE_SHORTS   &
    short_pullback &
    short_recover  &
    body_ok        &
    ema_bear       &
    ema_slope_down &
    rsi_falling    &
    rsi_short_ok   &
    vol_ok         &
    is_trending    &
    adx_rising     &
    di_spread_ok_s &
    momentum_ok_s  &
    session_ok     &
    ~is_panic      &
    atr_floor_ok
)

print(f"\nSignals — Short: {short_signal.sum()}")

# ─── Filter diagnostics ───────────────────────────────────────────────────────
print("\n--- Signal filter pass-through (short) ---")
components = [
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
cum = pd.Series(True, index=df.index)
for name, mask in components:
    cum = cum & mask
    print(f"  {name:<20} → {int(cum.sum()):>4} bars pass")

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
        eqcurve.append({"time": ts, "equity": equity}); continue

    sd = atr * SL_MULT

    if pos is not None:
        bars_in_trade += 1
        if pos["direction"] == "short":
            if low < pos["best"]:
                pos["best"] = low
            if pos["best"] <= pos["trail_activate_px"]:
                pos["sl"] = min(pos["sl"], pos["best"] + pos["trail_dist_fixed"])

            mb_exit = (MAX_BARS > 0 and bars_in_trade >= MAX_BARS)
            htp = (not mb_exit) and (low  <= pos["tp"])
            hsl = (not mb_exit) and (high >= pos["sl"])

            if mb_exit or htp or hsl:
                xp      = close if mb_exit else (pos["tp"] if htp else pos["sl"])
                pnl_pct = (pos["entry"] - xp) / pos["entry"]
                dp      = pnl_pct * pos["notional"] - pos["notional"] * COMMISSION_PCT * 2
                equity += dp
                result  = "MB" if mb_exit else ("TP" if htp else "SL")
                if dp <= 0:
                    consec_losses += 1
                    if consec_losses >= CONSEC_LOSS_LIMIT:
                        cooldown_bars = CONSEC_LOSS_COOLDOWN; consec_losses = 0
                else:
                    consec_losses = 0
                trades.append({"entry_time": pos["entry_time"], "exit_time": ts,
                               "direction": "short", "entry": pos["entry"], "exit": xp,
                               "result": result, "pnl_pct": round(pnl_pct*100, 3),
                               "dollar_pnl": round(dp, 2), "equity": round(equity, 2)})
                pos = None; bars_in_trade = 0

    if pos is None:
        if cooldown_bars > 0:
            cooldown_bars -= 1
        elif short_signal.get(ts, False):
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

    eqcurve.append({"time": ts, "equity": equity})

print(f"\nSimulation complete. Trades: {len(trades)}")

# ─── Statistics ───────────────────────────────────────────────────────────────
tdf = pd.DataFrame(trades)
if tdf.empty:
    print("No trades — consider relaxing filters."); sys.exit(0)

wins   = tdf[tdf["dollar_pnl"] > 0]
losses = tdf[tdf["dollar_pnl"] <= 0]
final  = tdf["equity"].iloc[-1]
total  = tdf["dollar_pnl"].sum()
wr     = len(wins) / len(tdf) * 100
gp     = wins["dollar_pnl"].sum()   if not wins.empty   else 0.0
gl     = losses["dollar_pnl"].sum() if not losses.empty else 0.0
pf     = gp / abs(gl) if gl != 0 else float("inf")
net    = (final - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100

eq_s  = pd.Series([e["equity"] for e in eqcurve])
roll_max  = eq_s.cummax()
drawdown  = (eq_s - roll_max) / roll_max * 100
max_dd    = drawdown.min()
calmar    = (net / abs(max_dd)) if max_dd != 0 else float("inf")

tp_exits = (tdf["result"] == "TP").sum()
sl_exits = (tdf["result"] == "SL").sum()
mb_exits = (tdf["result"] == "MB").sum()

tdf["entry_time"] = pd.to_datetime(tdf["entry_time"])
tdf["exit_time"]  = pd.to_datetime(tdf["exit_time"])
tdf["duration"]   = tdf["exit_time"] - tdf["entry_time"]
avg_dur = tdf["duration"].mean()

longs_n  = (tdf["direction"] == "long").sum()
shorts_n = (tdf["direction"] == "short").sum()

print(f"\n{'='*60}")
print(f"APM v2.0 · 10m · BTCUSD · 12-Month Backtest")
print(f"{'='*60}")
print(f"Window  : {BACKTEST_START.date()} → {BACKTEST_END.date()}")
print(f"Trades  : {len(tdf)}     (Longs: {longs_n}  Shorts: {shorts_n})")
print(f"Win rate:   {wr:.1f}%  ({len(wins)}W / {len(losses)}L)")
print(f"Prof fac:  {pf:.3f}")
print(f"Net P&L : {total:+.2f} USD  ({net:+.2f}%)")
print(f"Max DD  :  {max_dd:.2f}%")
print(f"Calmar  :  {calmar:.3f}")
print(f"TP exits: {tp_exits}  |  SL exits: {sl_exits}  |  MB exits: {mb_exits}")
print(f"Avg dur : {avg_dur}")
print(f"{'='*60}")

# ─── Monthly breakdown ────────────────────────────────────────────────────────
tdf["month"] = tdf["entry_time"].dt.to_period("M")
monthly = tdf.groupby("month").agg(
    net_usd=("dollar_pnl", "sum"),
    trades=("dollar_pnl", "count"),
    wins=("dollar_pnl", lambda x: (x > 0).sum()),
).reset_index()
monthly["wr"] = monthly["wins"] / monthly["trades"] * 100
print("\nMonthly breakdown:")
for _, r in monthly.iterrows():
    print(f"  {r['month']}:  {r['net_usd']:+8.2f}  ({int(r['trades'])} trades, {r['wr']:.1f}% WR)")

# ─── Trade log ────────────────────────────────────────────────────────────────
print("\nTrade log:")
print(f"  {'#':>3}  {'Entry':19}  {'Exit':19}  {'Dir':5}  {'Entry$':>7}  {'Exit$':>7}  {'Res':5}  {'PnL%':>7}  {'$PnL':>8}  {'Eq':>9}")
for i, t in tdf.iterrows():
    print(f"  {int(i)+1:>3}  {str(t['entry_time'])[:19]:19}  {str(t['exit_time'])[:19]:19}  {t['direction']:5}  "
          f"{t['entry']:>7.4f}  {t['exit']:>7.4f}  {t['result']:5}  "
          f"{t['pnl_pct']:>7.3f}%  {t['dollar_pnl']:>8.2f}  {t['equity']:>9.2f}")

# ─── Save trade log ───────────────────────────────────────────────────────────
_dir = __import__("pathlib").Path(__file__).parent
out_csv = _dir / "apm_v2_12mo_trades_btcusd_10m.csv"
tdf[["entry_time", "exit_time", "direction", "entry", "exit",
     "result", "pnl_pct", "dollar_pnl", "equity"]].to_csv(out_csv, index=False)
print(f"\nTrade log saved → {out_csv.name}")

# ─── Dashboard export ─────────────────────────────────────────────────────────
from pathlib import Path as _Path
_dash_out = _Path(__file__).resolve().parent.parent.parent.parent / "docs" / "data" / "btcusd" / "v2_trades.csv"
tdf[["entry_time", "exit_time", "direction", "entry", "exit",
     "result", "pnl_pct", "dollar_pnl", "equity"]].to_csv(_dash_out, index=False)
print(f"Dashboard export  → {_dash_out}")

# ─── Equity curve plot ────────────────────────────────────────────────────────
edf = pd.DataFrame(eqcurve).set_index("time")
fig, ax = plt.subplots(figsize=(14, 5))
ax.plot(edf.index, edf["equity"], lw=1.2, color="#58a6ff")
ax.axhline(INITIAL_CAPITAL, lw=0.8, color="gray", linestyle="--", alpha=0.6)
ax.set_title(f"APM v2.0 · BTCUSD 10m · 12-mo Equity  {net:+.2f}%  |  {len(tdf)}T  WR={wr:.0f}%  PF={pf:.2f}  DD={max_dd:.1f}%")
ax.set_ylabel("Equity ($)"); ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
ax.grid(alpha=0.2); plt.tight_layout()
out_png = _dir / "apm_v2_12mo_equity_btcusd_10m.png"
plt.savefig(out_png, dpi=150)
print(f"Equity chart  saved → {out_png.name}")
