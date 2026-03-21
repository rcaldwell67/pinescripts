# ─────────────────────────────────────────────────────────────────────────────
# APM v1.0 — CLM 5m  ·  Year-To-Date Backtest
# Mirrors "Adaptive Pullback Momentum v1.0 · 5m" Pine script exactly.
# Shorts-only (CLM sub-15m longs: win-rate too low historically).
#
# Parameters (from Pine v1.0 5m, Stage-3 sweep-optimised on CLM):
#   ADX=20 | ADX_SLOPE=0 (off) | DI_SPREAD=0 (off) | PB=0.20%
#   EMA_SLOPE=3 bars | MOMENTUM=5 bars | SESSION 9–14 ET
#   SL×2.0 | TP×6.0 | TRAIL_ACT=3.5× | TRAIL_DIST=0.3×
#   MAX_BARS=30 | ATR_FLOOR=0.15% | PANIC=1.5× | VOL=0.7× | MIN_BODY=0.15×
#
# Data: yfinance 5m, period=60d (max intraday window)
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
from indicators_signals import build_indicators_signals

_ET = pytz.timezone("America/New_York")

# ─── Configuration ─────────────────────────────────────────────────────────────
TICKER   = "CLM"
PERIOD   = "60d"       # yfinance max for 5m data
INTERVAL = "5m"

YTD_START = pd.Timestamp("2026-01-01", tz="America/New_York")

EMA_FAST = 21;  EMA_MID = 50;  EMA_SLOW = 200
ADX_LEN  = 14;  RSI_LEN = 14;  ATR_LEN  = 14;  VOL_LEN = 20
ATR_BL_LEN = 60


# Strategy parameters (can be replaced by argparse or config)
PB_PCT         = 0.20
ADX_THRESH     = 20
ADX_SLOPE_BARS = 0
DI_SPREAD_MIN  = 0.0
EMA_SLOPE_BARS = 3
MOMENTUM_BARS  = 5
VOL_MULT       = 0.7
MIN_BODY       = 0.15
ATR_FLOOR      = 0.0015
PANIC_MULT     = 1.5
RSI_LO_S       = 30;  RSI_HI_S = 58
RSI_LO_L       = 42;  RSI_HI_L = 68
SL_MULT    = 2.0
TP_MULT    = 6.0
TRAIL_ACT  = 3.5
TRAIL_DIST = 0.3
MAX_BARS   = 30
RISK_PCT        = 0.01
INITIAL_CAPITAL = 10_000.0
COMMISSION_PCT  = 0.0006
TRADE_LONGS  = False
TRADE_SHORTS = True
SESSION_START_ET = 9
SESSION_END_ET   = 14
CONSEC_LOSS_LIMIT    = 2
CONSEC_LOSS_COOLDOWN = 1

# ─── Download 5m data ──────────────────────────────────────────────────────────
print(f"Downloading {TICKER} {INTERVAL} (period='{PERIOD}') ...")
raw = yf.download(TICKER, period=PERIOD, interval=INTERVAL,
                  auto_adjust=True, progress=False)
if raw.empty:
    raise SystemExit(f"No data returned for {TICKER} {INTERVAL}.")
if isinstance(raw.columns, pd.MultiIndex):
    raw.columns = raw.columns.droplevel(1)
raw = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
raw = raw[raw["Volume"] > 0].dropna()
raw.index = pd.to_datetime(raw.index)
if raw.index.tzinfo is None:
    raw.index = raw.index.tz_localize("UTC")
raw.index = raw.index.tz_convert(_ET)
df = raw.copy()
df["EMA_MID"]  = df["Close"].ewm(span=EMA_MID,  adjust=False).mean()
df["EMA_SLOW"] = df["Close"].ewm(span=EMA_SLOW, adjust=False).mean()
delta  = df["Close"].diff()
avg_g  = delta.clip(lower=0).ewm(alpha=1/RSI_LEN, adjust=False).mean()
avg_l  = (-delta).clip(lower=0).ewm(alpha=1/RSI_LEN, adjust=False).mean()
df["RSI"] = 100 - (100 / (1 + avg_g / avg_l.replace(0, 1e-10)))
hl  = df["High"] - df["Low"]
hpc = (df["High"] - df["Close"].shift(1)).abs()
lpc = (df["Low"]  - df["Close"].shift(1)).abs()
df["ATR"]    = tr.ewm(alpha=1/ATR_LEN, adjust=False).mean()
df["ATR_BL"] = df["ATR"].rolling(ATR_BL_LEN).mean()
df["VOL_MA"] = df["Volume"].rolling(VOL_LEN).mean()
up_move  = df["High"] - df["High"].shift(1)
dn_move  = df["Low"].shift(1) - df["Low"]
s_plus   = pd.Series(plus_dm,  index=df.index).ewm(alpha=1/ADX_LEN, adjust=False).mean()
s_minus  = pd.Series(minus_dm, index=df.index).ewm(alpha=1/ADX_LEN, adjust=False).mean()
df["DI_PLUS"]  = 100 * s_plus  / df["ATR"].replace(0, 1e-10)
df["DI_MINUS"] = 100 * s_minus / df["ATR"].replace(0, 1e-10)
dx = 100 * (df["DI_PLUS"] - df["DI_MINUS"]).abs() / (
df["ADX"] = dx.ewm(alpha=1/ADX_LEN, adjust=False).mean()
df.dropna(inplace=True)
df["ET_HOUR"] = df.index.hour    # ET already
tol = PB_PCT / 100.0
session_ok = (df["ET_HOUR"] >= SESSION_START_ET) & (df["ET_HOUR"] < SESSION_END_ET)





# --- Use shared indicator/signal logic ---
df, long_signal, short_signal = build_indicators_signals(
    df,
    ema_fast=EMA_FAST, ema_mid=EMA_MID, ema_slow=EMA_SLOW,
    adx_len=ADX_LEN, rsi_len=RSI_LEN, atr_len=ATR_LEN, vol_len=VOL_LEN, atr_bl_len=ATR_BL_LEN,
    adx_thresh=ADX_THRESH, pb_pct=PB_PCT, vol_mult=VOL_MULT, atr_floor=ATR_FLOOR, panic_mult=PANIC_MULT,
    ema_slope_bars=EMA_SLOPE_BARS, momentum_bars=MOMENTUM_BARS, min_body=MIN_BODY,
    di_spread_min=DI_SPREAD_MIN, adx_slope_bars=ADX_SLOPE_BARS,
    rsi_lo_s=RSI_LO_S, rsi_hi_s=RSI_HI_S, rsi_lo_l=RSI_LO_L, rsi_hi_l=RSI_HI_L,
    session_start=SESSION_START_ET, session_end=SESSION_END_ET,
    trade_longs=TRADE_LONGS, trade_shorts=TRADE_SHORTS
)

# ─── Filter pass-through diagnostics ──────────────────────────────────────────
print("\n─── Signal filter pass-through (SHORT) ───")
components_short = [
    ("short_pb",        short_pb),
    ("ema_bear",        ema_bear),
    ("ema_slope_down",  ema_slope_down),
    ("rsi_falling",     rsi_falling),
    ("rsi_short_ok",    rsi_short_ok),
    ("vol_ok",          vol_ok),
    ("body_ok",         body_ok),
    ("is_trending",     is_trending),
    ("adx_rising",      adx_rising),
    ("di_spread_ok_s",  di_spread_ok_s),
    ("mom_ok_s",        mom_ok_s),
    ("session_ok",      session_ok),
    ("~is_panic",       ~is_panic),
    ("atr_floor_ok",    atr_fl),
]
cum = pd.Series([True] * len(df), index=df.index)
for name, mask in components_short:
    cum = cum & mask
    print(f"  {name:<20} → cumulative {cum.sum():>5} rows pass")

print(f"\nFinal signals  →  Shorts: {short_signal.sum()}  |  Longs: {long_signal.sum()}")

# ─── Trim to YTD window for simulation ────────────────────────────────────────
df_ytd = df[df.index >= YTD_START].copy()
ls_ytd = long_signal.reindex(df_ytd.index, fill_value=False)
ss_ytd = short_signal.reindex(df_ytd.index, fill_value=False)
print(f"\nYTD window ({YTD_START.date()} → {df_ytd.index[-1].date()})"
      f"  —  {len(df_ytd)} bars  |  signals: {ss_ytd.sum()} short  {ls_ytd.sum()} long")

# ─── Bar-by-bar simulation ────────────────────────────────────────────────────
equity        = INITIAL_CAPITAL
pos           = None
trades        = []
eqcurve       = []
consec_losses = 0
cooldown_bars = 0
bars_in_trade = 0

for ts, row in df_ytd.iterrows():
    close = float(row["Close"]); high = float(row["High"])
    low   = float(row["Low"]);   atr  = float(row["ATR"])
    if atr == 0 or np.isnan(atr):
        eqcurve.append({"time": ts, "equity": equity})
        continue
    sd = atr * SL_MULT

    # ── Manage open position ──────────────────────────────────────────────────
    if pos is not None:
        bars_in_trade += 1

        if pos["direction"] == "short":
            # Update best price
            if low < pos["best"]:
                pos["best"] = low
            # Trail stop (once runup >= trail activate distance)
            if pos["best"] <= pos["trail_activate_px"]:
                new_sl = pos["best"] + pos["trail_dist_fixed"]
                if new_sl < pos["sl"]:
                    pos["sl"] = new_sl
            # Max bars exit (at close of bar)
            if MAX_BARS > 0 and bars_in_trade >= MAX_BARS:
                xp      = close
                pnl_raw = (pos["entry"] - xp) / pos["entry"]
                dp      = pnl_raw * pos["notional"] - pos["notional"] * COMMISSION_PCT * 2
                equity += dp
                if dp <= 0:
                    consec_losses += 1
                    if consec_losses >= CONSEC_LOSS_LIMIT:
                        cooldown_bars = CONSEC_LOSS_COOLDOWN; consec_losses = 0
                else:
                    consec_losses = 0
                trades.append({"entry_time": pos["entry_time"], "exit_time": ts,
                               "direction": "short", "entry": pos["entry"], "exit": xp,
                               "result": "MB",
                               "pnl_pct": round(pnl_raw * 100, 3),
                               "dollar_pnl": round(dp, 2), "equity": round(equity, 2)})
                pos = None; bars_in_trade = 0
                eqcurve.append({"time": ts, "equity": equity})
                continue
            # TP / SL check (inbar)
            hit_tp = low  <= pos["tp"]
            hit_sl = high >= pos["sl"]
            if hit_tp or hit_sl:
                xp      = pos["tp"] if hit_tp else pos["sl"]
                pnl_raw = (pos["entry"] - xp) / pos["entry"]
                dp      = pnl_raw * pos["notional"] - pos["notional"] * COMMISSION_PCT * 2
                equity += dp
                result  = "TP" if hit_tp else "SL"
                if dp <= 0:
                    consec_losses += 1
                    if consec_losses >= CONSEC_LOSS_LIMIT:
                        cooldown_bars = CONSEC_LOSS_COOLDOWN; consec_losses = 0
                else:
                    consec_losses = 0
                trades.append({"entry_time": pos["entry_time"], "exit_time": ts,
                               "direction": "short", "entry": pos["entry"], "exit": xp,
                               "result": result,
                               "pnl_pct": round(pnl_raw * 100, 3),
                               "dollar_pnl": round(dp, 2), "equity": round(equity, 2)})
                pos = None; bars_in_trade = 0

        else:  # long
            if high > pos["best"]:
                pos["best"] = high
            if pos["best"] >= pos["trail_activate_px"]:
                new_sl = pos["best"] - pos["trail_dist_fixed"]
                if new_sl > pos["sl"]:
                    pos["sl"] = new_sl
            if MAX_BARS > 0 and bars_in_trade >= MAX_BARS:
                xp      = close
                pnl_raw = (xp - pos["entry"]) / pos["entry"]
                dp      = pnl_raw * pos["notional"] - pos["notional"] * COMMISSION_PCT * 2
                equity += dp
                if dp <= 0:
                    consec_losses += 1
                    if consec_losses >= CONSEC_LOSS_LIMIT:
                        cooldown_bars = CONSEC_LOSS_COOLDOWN; consec_losses = 0
                else:
                    consec_losses = 0
                trades.append({"entry_time": pos["entry_time"], "exit_time": ts,
                               "direction": "long", "entry": pos["entry"], "exit": xp,
                               "result": "MB",
                               "pnl_pct": round(pnl_raw * 100, 3),
                               "dollar_pnl": round(dp, 2), "equity": round(equity, 2)})
                pos = None; bars_in_trade = 0
                eqcurve.append({"time": ts, "equity": equity})
                continue
            hit_tp = high >= pos["tp"]
            hit_sl = low  <= pos["sl"]
            if hit_tp or hit_sl:
                xp      = pos["tp"] if hit_tp else pos["sl"]
                pnl_raw = (xp - pos["entry"]) / pos["entry"]
                dp      = pnl_raw * pos["notional"] - pos["notional"] * COMMISSION_PCT * 2
                equity += dp
                result  = "TP" if hit_tp else "SL"
                if dp <= 0:
                    consec_losses += 1
                    if consec_losses >= CONSEC_LOSS_LIMIT:
                        cooldown_bars = CONSEC_LOSS_COOLDOWN; consec_losses = 0
                else:
                    consec_losses = 0
                trades.append({"entry_time": pos["entry_time"], "exit_time": ts,
                               "direction": "long", "entry": pos["entry"], "exit": xp,
                               "result": result,
                               "pnl_pct": round(pnl_raw * 100, 3),
                               "dollar_pnl": round(dp, 2), "equity": round(equity, 2)})
                pos = None; bars_in_trade = 0

    # ── Check for new entry ───────────────────────────────────────────────────
    if pos is None:
        if cooldown_bars > 0:
            cooldown_bars -= 1
        else:
            if bool(ss_ytd.get(ts, False)):
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
                    "trail_dist_fixed":  atr   * TRAIL_DIST,
                }
                bars_in_trade = 0
            elif bool(ls_ytd.get(ts, False)):
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
                    "trail_dist_fixed":  atr   * TRAIL_DIST,
                }
                bars_in_trade = 0

    eqcurve.append({"time": ts, "equity": equity})

print(f"\nSimulation complete — {len(trades)} trades")

# ─── Statistics ────────────────────────────────────────────────────────────────
tdf = pd.DataFrame(trades)


wins   = tdf[tdf["dollar_pnl"] > 0]
losses = tdf[tdf["dollar_pnl"] <= 0]
total  = len(tdf)

wr      = len(wins) / total * 100
gp      = wins["dollar_pnl"].sum()
gl      = losses["dollar_pnl"].abs().sum()
pf      = gp / gl if gl > 0 else float("inf")
net     = tdf["dollar_pnl"].sum()
net_pct = net / INITIAL_CAPITAL * 100

eq_arr  = np.array([e["equity"] for e in eqcurve])
peak    = np.maximum.accumulate(eq_arr)
dd_arr  = (eq_arr - peak) / peak * 100
max_dd  = dd_arr.min()
calmar  = net_pct / abs(max_dd) if max_dd < 0 else float("inf")

tp_exits = (tdf["result"] == "TP").sum()
sl_exits = (tdf["result"] == "SL").sum()
mb_exits = (tdf["result"] == "MB").sum()

avg_dur = (pd.to_datetime(tdf["exit_time"]) - pd.to_datetime(tdf["entry_time"])).mean()

print(f"""
╔══════════════════════════════════════════════════════╗
║   APM v1.0 · 5m  ·  CLM  ·  YTD {YTD_START.year} Backtest         ║
╠══════════════════════════════════════════════════════╣
║  Window  : {str(df_ytd.index[0].date()):>10} → {str(df_ytd.index[-1].date()):<10}             ║
║  Trades  : {total:<5}  (Longs: {tdf[tdf['direction']=='long'].shape[0]}  Shorts: {tdf[tdf['direction']=='short'].shape[0]})           ║
║  Win rate: {wr:>6.1f}%  ({len(wins)}W / {len(losses)}L)                    ║
║  Prof fac: {pf:>6.3f}                                     ║
║  Net P&L : {net:>+8.2f} USD  ({net_pct:>+.2f}%)             ║
║  Max DD  : {max_dd:>6.2f}%                                    ║
║  Calmar  : {calmar:>6.3f}                                     ║
║  TP exits: {tp_exits}  |  SL exits: {sl_exits}  |  MB exits: {mb_exits}            ║
║  Avg dur : {str(avg_dur).split('.')[0]:<15}                       ║
╚══════════════════════════════════════════════════════╝""")

# ─── Trade log ─────────────────────────────────────────────────────────────────
print("\n─── Trade Log ───")
print(f"{'#':>3}  {'Entry Time':<23}  {'Exit Time':<23}  {'Dir':>5}  "
      f"{'Entry':>7}  {'Exit':>7}  {'Result':>6}  {'P&L%':>7}  {'$P&L':>8}  {'Equity':>9}")
print("─" * 108)
for i, t in tdf.iterrows():
    print(f"{i+1:>3}  {str(t['entry_time'])[:22]:<23}  {str(t['exit_time'])[:22]:<23}  "
          f"{t['direction']:>5}  {t['entry']:>7.4f}  {t['exit']:>7.4f}  "
          f"{t['result']:>6}  {t['pnl_pct']:>+7.3f}%  {t['dollar_pnl']:>+8.2f}  {t['equity']:>9.2f}")

# ─── Save trade log CSV ────────────────────────────────────────────────────────
out_csv = "apm_v1_ytd_trades_clm_5m.csv"
tdf.to_csv(out_csv, index=False)
print(f"\nTrade log saved → {out_csv}")

# ─── Equity curve chart ────────────────────────────────────────────────────────
eq_df = pd.DataFrame(eqcurve).set_index("time")

fig, axes = plt.subplots(2, 1, figsize=(14, 8), gridspec_kw={"height_ratios": [3, 1]})
fig.suptitle(f"APM v1.0 · 5m  ·  CLM  ·  YTD {YTD_START.year}  |  "
             f"Net {net_pct:+.2f}%  |  WR {wr:.0f}%  |  PF {pf:.3f}  |  "
             f"MaxDD {max_dd:.2f}%  |  {total} trades",
             fontsize=11, fontweight="bold")

ax1, ax2 = axes
ax1.plot(eq_df.index, eq_df["equity"], color="#48bb78", linewidth=1.5, label="Equity")
ax1.axhline(INITIAL_CAPITAL, color="#718096", linewidth=0.8, linestyle="--", alpha=0.6)
ax1.fill_between(eq_df.index, INITIAL_CAPITAL, eq_df["equity"],
                 where=eq_df["equity"] >= INITIAL_CAPITAL,
                 alpha=0.15, color="#48bb78")
ax1.fill_between(eq_df.index, INITIAL_CAPITAL, eq_df["equity"],
                 where=eq_df["equity"] < INITIAL_CAPITAL,
                 alpha=0.15, color="#fc8181")
for _, t in tdf.iterrows():
    col = "#48bb78" if t["dollar_pnl"] > 0 else "#fc8181"
    ax1.axvline(pd.Timestamp(t["exit_time"]), color=col, linewidth=0.6, alpha=0.5)
ax1.set_ylabel("Equity (USD)")
ax1.set_facecolor("#0d0d1a"); fig.patch.set_facecolor("#0d0d1a")
ax1.tick_params(colors="white"); ax1.yaxis.label.set_color("white")
ax1.spines[["top","right","bottom","left"]].set_color("#444")
ax1.legend(loc="upper left", facecolor="#1a1a2e", edgecolor="#444",
           labelcolor="white", fontsize=9)

ax2.fill_between(eq_df.index, 0, dd_arr[:len(eq_df)], color="#fc8181", alpha=0.7)
ax2.axhline(0, color="#718096", linewidth=0.5)
ax2.set_ylabel("Drawdown %")
ax2.set_facecolor("#0d0d1a")
ax2.tick_params(colors="white"); ax2.yaxis.label.set_color("white")
ax2.spines[["top","right","bottom","left"]].set_color("#444")
for ax in axes:
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.tick_params(axis="x", colors="white", labelsize=8)

plt.tight_layout()
out_png = "apm_v1_ytd_equity_clm_5m.png"
plt.savefig(out_png, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
plt.close()
print(f"Equity chart saved → {out_png}")
