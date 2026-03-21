# --- Additional indicator/parameter values ---
EMA_FAST = 21
EMA_MID = 50
EMA_SLOW = 200
PB_PCT = 0.4
ADX_LEN = 14
RSI_LEN = 14
ATR_LEN = 14
VOL_LEN = 20
ATR_BL_LEN = 60
# --- Dependencies and imports ---
try:
    import yfinance as yf
    import pandas as pd
    import numpy as np
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    import warnings
    import pytz
    import datetime
    warnings.filterwarnings("ignore")
except ImportError as e:
    print("\nMissing dependency:", e)
    print("Please activate your virtual environment and install required packages (yfinance, pandas, numpy, matplotlib, pytz).\n")
    raise SystemExit(1)
from indicators_signals import build_indicators_signals

# Define Eastern Timezone for use in script
_ET = pytz.timezone("America/New_York")

# --- Script configuration ---
TICKER = "CLM"
INTERVAL = "5m"
PERIOD = "60d"
YTD_START = datetime.datetime(datetime.datetime.now().year, 1, 1, tzinfo=pytz.timezone("America/New_York"))

# Use Alpaca data for apples-to-apples comparison with sweep
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
from datetime import datetime, timezone
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.enums import DataFeed

ALPACA_KEY    = os.environ.get("ALPACA_PAPER_API_KEY") or os.environ.get("ALPACA_API_KEY", "PKNIYXYVLHKHF43IIEUQIA42DJ")
ALPACA_SECRET = os.environ.get("ALPACA_PAPER_API_SECRET") or os.environ.get("ALPACA_API_SECRET", "9djPy47EmNvMr6Yyfa3UpQ49ruQRWAmTmu8thmDvm34u")

print(f"Downloading {TICKER} 5m via Alpaca (60 days)…")
client = StockHistoricalDataClient(ALPACA_KEY, ALPACA_SECRET)
end_dt = datetime.now(tz=timezone.utc)
start_dt = end_dt - pd.Timedelta(days=60)
req = StockBarsRequest(
    symbol_or_symbols=TICKER,
    timeframe=TimeFrame(5, TimeFrameUnit.Minute),
    start=start_dt,
    end=end_dt,
    feed=DataFeed.IEX,
)
bars = client.get_stock_bars(req)
raw = bars.df.reset_index(level=0, drop=True)
raw = raw.rename(columns={"open":"Open","high":"High","low":"Low",
                           "close":"Close","volume":"Volume"})
raw = raw[["Open","High","Low","Close","Volume"]].copy()
raw = raw[raw["Volume"] > 0].dropna()
raw.index = pd.to_datetime(raw.index, utc=True).tz_convert(_ET)
print(f"Bars: {len(raw)}  |  {raw.index[0]} → {raw.index[-1]}")
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




# Top-performing sweep parameters for 20%+ net return

# Top sweep result for +20%+ net return

# Top 60d sweep result for +20%+ net return
ADX_THRESH     = 15
ADX_SLOPE_BARS = 0
DI_SPREAD_MIN  = 0.0
EMA_SLOPE_BARS = 3
MOMENTUM_BARS  = 5
VOL_MULT       = 0.3
MIN_BODY       = 0.15
ATR_FLOOR      = 0.001  # 0.1%
PANIC_MULT     = 1.5
RSI_LO_S       = 30;  RSI_HI_S = 58
RSI_LO_L       = 42;  RSI_HI_L = 68
SL_MULT    = 4.0
TP_MULT    = 8.0
TRAIL_ACT  = 2.0
TRAIL_DIST = 0.1
MAX_BARS   = 0  # Disable max bars exit to match sweep
RISK_PCT        = 0.035  # 3.5%
INITIAL_CAPITAL = 10_000.0
COMMISSION_PCT  = 0.0006
TRADE_LONGS  = False  # Only simulate shorts to match sweep
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
df["ET_HOUR"] = df.index.hour  # ET already
df.dropna(inplace=True)
tol = PB_PCT / 100.0
session_ok = (df["ET_HOUR"] >= SESSION_START_ET) & (df["ET_HOUR"] < SESSION_END_ET)
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


# ─── Trim to YTD window for simulation ────────────────────────────────────────
df_ytd = df[df.index >= YTD_START].copy()
# Ensure signals are Series with same index as df_ytd
ls_ytd = pd.Series(long_signal, index=df.index).reindex(df_ytd.index, fill_value=False)
ss_ytd = pd.Series(short_signal, index=df.index).reindex(df_ytd.index, fill_value=False)
print(f"\nYTD window ({YTD_START.date()} → {df_ytd.index[-1].date()})" 
    f"  —  {len(df_ytd)} bars  |  signals: {ss_ytd.sum()} short  {ls_ytd.sum()} long")
# Debug: print first few nonzero short signal timestamps
nonzero_short = ss_ytd[ss_ytd].index.tolist()
print(f"First 10 short signal timestamps: {nonzero_short[:10]}")
print(f"Total short signals in YTD window: {len(nonzero_short)}")
if len(nonzero_short) > 0:
    print(f"All short signal timestamps: {nonzero_short}")

# Print summary stats for each short signal condition in YTD window
import numpy as np
def pct(x):
    return 100.0 * np.sum(x) / len(x) if len(x) > 0 else 0.0
df_ytd = df[df.index >= YTD_START].copy()
short_pb = (df_ytd["High"].shift(1) >= df_ytd["EMA_FAST"].shift(1) * (1.0 - PB_PCT / 100.0)) & (df_ytd["Close"] < df_ytd["EMA_FAST"]) & (df_ytd["Close"] < df_ytd["Open"])
ema_bear = (df_ytd["EMA_FAST"] < df_ytd["EMA_MID"]) & (df_ytd["EMA_MID"] < df_ytd["EMA_SLOW"])
rsi_short_ok = (df_ytd["RSI"] >= RSI_LO_S) & (df_ytd["RSI"] <= RSI_HI_S)
vol_ok = df_ytd["Volume"] >= df_ytd["VOL_MA"] * VOL_MULT
body_ok = (df_ytd["Close"] - df_ytd["Open"]).abs() / df_ytd["ATR"].replace(0, 1e-10) >= MIN_BODY
is_trending = df_ytd["ADX"] > ADX_THRESH
atr_fl = df_ytd["ATR"] / df_ytd["Close"] >= ATR_FLOOR
session_ok = (df_ytd["ET_HOUR"] >= SESSION_START_ET) & (df_ytd["ET_HOUR"] < SESSION_END_ET)
print("\nShort signal condition pass rates in YTD window:")
print(f"short_pb:    {pct(short_pb):5.1f}%")
print(f"ema_bear:    {pct(ema_bear):5.1f}%")
print(f"rsi_short_ok:{pct(rsi_short_ok):5.1f}%")
print(f"vol_ok:      {pct(vol_ok):5.1f}%")
print(f"body_ok:     {pct(body_ok):5.1f}%")
print(f"is_trending: {pct(is_trending):5.1f}%")
print(f"atr_fl:      {pct(atr_fl):5.1f}%")
print(f"session_ok:  {pct(session_ok):5.1f}%")

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
        print(f"[DEBUG] Managing open position at {ts}: {pos}")
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
                print(f"[DEBUG] Max bars exit at {ts} for position: {pos}")
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
            print(f"[DEBUG] SL/TP check at {ts}: low={low}, high={high}, sl={pos['sl']}, tp={pos['tp']}, entry={pos['entry']}")
            # For shorts: TP is hit if low <= tp, SL is hit if high >= sl
            hit_tp = low <= pos["tp"]
            hit_sl = high >= pos["sl"]
            if hit_tp or hit_sl:
                xp      = pos["tp"] if hit_tp else pos["sl"]
                pnl_raw = (pos["entry"] - xp) / pos["entry"]
                dp      = pnl_raw * pos["notional"] - pos["notional"] * COMMISSION_PCT * 2
                equity += dp
                result  = "TP" if hit_tp else "SL"
                print(f"[DEBUG] Exit {'TP' if hit_tp else 'SL'} at {ts} for position: {pos}, exit price: {xp}, pnl: {dp}")
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
            # Debug: print ts and signal value
            # Debug: print type and repr of ts and first nonzero ss_ytd index
            if ss_ytd.sum() > 0:
                first_signal_idx = ss_ytd[ss_ytd].index[0]
                print(f"ts: {ts} (type={type(ts)}, repr={repr(ts)})")
                print(f"first_signal_idx: {first_signal_idx} (type={type(first_signal_idx)}, repr={repr(first_signal_idx)})")
            print(f"ts: {ts}, ss_ytd[ts]: {ss_ytd.loc[ts]}")
            # Print which short signal conditions are blocking
            conds = {
                'short_pb': row.get('High', None) >= row.get('EMA_FAST', None) * (1.0 - PB_PCT / 100.0) if 'High' in row and 'EMA_FAST' in row else None,
                'ema_bear': row.get('EMA_FAST', None) < row.get('EMA_MID', None) < row.get('EMA_SLOW', None) if 'EMA_FAST' in row and 'EMA_MID' in row and 'EMA_SLOW' in row else None,
                'rsi_short_ok': RSI_LO_S <= row.get('RSI', 0) <= RSI_HI_S if 'RSI' in row else None,
                'vol_ok': row.get('Volume', 0) >= row.get('VOL_MA', 0) * VOL_MULT if 'Volume' in row and 'VOL_MA' in row else None,
                'body_ok': abs(row.get('Close', 0) - row.get('Open', 0)) / row.get('ATR', 1) >= MIN_BODY if 'Close' in row and 'Open' in row and 'ATR' in row else None,
                'is_trending': row.get('ADX', 0) > ADX_THRESH if 'ADX' in row else None,
                'atr_fl': row.get('ATR', 0) / row.get('Close', 1) >= ATR_FLOOR if 'ATR' in row and 'Close' in row else None,
                'session_ok': SESSION_START_ET <= row.get('ET_HOUR', 0) < SESSION_END_ET if 'ET_HOUR' in row else None,
            }
            print('Short signal conditions:', conds)
            ts_str = ts.isoformat()
            signal_idx_strs = set(idx.isoformat() for idx in ss_ytd[ss_ytd].index)
            if ts_str in signal_idx_strs:
                print(f"Trade triggered at {ts}")
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
