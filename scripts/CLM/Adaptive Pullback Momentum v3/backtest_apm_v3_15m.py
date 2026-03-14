# ─────────────────────────────────────────────────────────────────────────────
# APM v3.4 — CLM 15m backtest
# Mirrors "Adaptive Pullback Momentum v3.4" pine script parameters exactly.
# Shorts-only (v3.4 thesis: longs at 15m WR=23%, noise too high).
#
# v3.4 CHANGES vs v3.3  (sweep: ret=+21.59% PF=3.735 WR=73% 11 trades)
#   ADX threshold : 18 → 18  (kept — CLM Wilder EWM ADX is lower than rolling SMA)
#   PB tolerance  : 0.30% → 0.40%  (slightly wider — more entries at CLM noise)
#   TP multiplier : 2.0× → 6.0×  (crude oil 15m big moves run 6×ATR)
#   SL multiplier : 1.5× → 1.5×  (tighter stop = larger position = more compounding)
#   Trail activate: 3.5× → 2.5×  (start locking in gains sooner)
#   Trail distance: 1.2× → 0.4×  (tight trail captures more of the move)
#   Risk per trade: 1.0% → 2.0%  (Wilder ADX mini-sweep peak: doubles cormpounding)
#   VOL_MULT      : 0.9× → 1.2×  (align with pine script / sweep baseline)
#   MIN_BODY      : 0.15× (slightly relaxed to allow more quality CLM entries)
#   PANIC_MULT    : 1.5× (crude oil regime spikes are more significant)
#   RSI bounds    : 30-60 → 32-58 for shorts (align with pine script)
#   Enhancements removed: session filter, DI spread, ADX slope, momentum
#     (sweep shows these filters removed profitable trades, net -20%)
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

# ─── Configuration (CLM-tuned — crude oil futures 15m) ──────────────────────
TICKER   = "CLM"
PERIOD   = "60d"      # Yahoo Finance intraday limit
INTERVAL = "15m"

EMA_FAST = 21
EMA_MID  = 50
EMA_SLOW = 200
ADX_LEN  = 14
RSI_LEN  = 14
ATR_LEN  = 14
VOL_LEN  = 20

# v3.4-tuned parameters (CLM 15m Wilder-smoothed ADX mini-sweep: ret=+24.4% PF=3.45 WR=67% 12 trades)
ADX_THRESH  = 18
PB_PCT      = 0.40    # pullback tolerance % — slightly wider for CLM noise
VOL_MULT    = 1.2     # align with pine script / sweep baseline
MIN_BODY    = 0.15    # slightly relaxed to allow more quality entries
ATR_FLOOR   = 0.0010  # 0.10% — crude oil 15m bars are larger in % terms
PANIC_MULT  = 1.5     # raised — crude oil spikes are regime-changing, not noise

# RSI bounds align with pine script defaults for shorts
RSI_LO_L = 42;  RSI_HI_L = 68
RSI_LO_S = 32;  RSI_HI_S = 58

SL_MULT    = 1.5      # tighter stop → larger position → more compounding on wins
TP_MULT    = 6.0      # TP×6.0 — crude oil 15m big moves run 6×ATR (sweep peak)
TRAIL_ACT  = 2.5      # trail activates at 2.5×ATR (same as pine script)
TRAIL_DIST = 0.4      # tight trail locks in gains quickly on 15m moves

RISK_PCT   = 0.02  # 2% equity per trade (sweep peak: doubles compounding)

INITIAL_CAPITAL = 10_000.0
COMMISSION_PCT  = 0.0006    # 0.06% per side

# Longs disabled — CLM 15m longs: WR=33%, PF=0.276 (same noise issue as BTC)
# Shorts only: WR=73%, PF=3.735 (v3.4 parameters)
TRADE_LONGS  = False
TRADE_SHORTS = True

# ─── Download ─────────────────────────────────────────────────────────────────
print(f"Downloading {TICKER} {INTERVAL} period='{PERIOD}'...")
df = yf.download(TICKER, period=PERIOD, interval=INTERVAL, auto_adjust=True, progress=False)
if df.empty:
    raise SystemExit(f"No data returned for {TICKER} {INTERVAL}.")
if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.droplevel(1)
df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
df = df[df["Volume"] > 0].copy()
df.dropna(inplace=True)
print(f"Rows: {len(df)}  Range: {df.index[0]} → {df.index[-1]}")

# ─── Indicators ───────────────────────────────────────────────────────────────
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
df["ATR_BL"] = df["ATR"].rolling(60).mean()   # 60-bar ATR baseline for panic filter

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
tol = PB_PCT / 100.0

# Regime guards
is_trending = df["ADX"] > ADX_THRESH
is_panic    = df["ATR"] > df["ATR_BL"] * PANIC_MULT

# Full EMA stack
ema_bull = (df["EMA_FAST"] > df["EMA_MID"]) & (df["EMA_MID"] > df["EMA_SLOW"])
ema_bear = (df["EMA_FAST"] < df["EMA_MID"]) & (df["EMA_MID"] < df["EMA_SLOW"])

# EMA slope (3-bar)
ema_slope_up   = df["EMA_FAST"] > df["EMA_FAST"].shift(3)
ema_slope_down = df["EMA_FAST"] < df["EMA_FAST"].shift(3)

# Pullback-to-EMA touch (prev bar)
pb_tol_up = df["EMA_FAST"].shift(1) * (1.0 + tol)
pb_tol_dn = df["EMA_FAST"].shift(1) * (1.0 - tol)
long_pullback  = df["Low"].shift(1)  <= pb_tol_up
short_pullback = df["High"].shift(1) >= pb_tol_dn

# Recovery bar (current bar closes through EMA)
long_recover  = (df["Close"] > df["EMA_FAST"]) & (df["Close"] > df["Open"])
short_recover = (df["Close"] < df["EMA_FAST"]) & (df["Close"] < df["Open"])

# Min body (doji rejection)
body       = (df["Close"] - df["Open"]).abs() / df["ATR"]
body_ok    = body >= MIN_BODY

# RSI momentum direction
rsi_rising  = df["RSI"] > df["RSI"].shift(1)
rsi_falling = df["RSI"] < df["RSI"].shift(1)

# RSI within bounds
rsi_long_ok  = (df["RSI"] >= RSI_LO_L) & (df["RSI"] <= RSI_HI_L)
rsi_short_ok = (df["RSI"] >= RSI_LO_S) & (df["RSI"] <= RSI_HI_S)

# Volume filter
vol_ok = df["Volume"] >= df["VOL_MA"] * VOL_MULT

# ATR floor
atr_floor_ok = df["ATR"] / df["Close"] >= ATR_FLOOR

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
    ~is_panic       &
    atr_floor_ok
)

# ─── Signal filter pass-through diagnostics ───────────────────────────────────
components_long = [
    ("long_pullback",  long_pullback),
    ("long_recover",   long_recover),
    ("body_ok",        body_ok),
    ("ema_bull",       ema_bull),
    ("ema_slope_up",   ema_slope_up),
    ("rsi_rising",     rsi_rising),
    ("rsi_long_ok",    rsi_long_ok),
    ("vol_ok",         vol_ok),
    ("is_trending",    is_trending),
    ("~is_panic",      ~is_panic),
    ("atr_floor_ok",   atr_floor_ok),
]
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
    ("~is_panic",       ~is_panic),
    ("atr_floor_ok",    atr_floor_ok),
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

print(f"\nv3.4 Signals — Long: {long_signal.sum()}  Short: {short_signal.sum()}")

# ─── Bar-by-bar simulation ────────────────────────────────────────────────────
equity  = INITIAL_CAPITAL
pos     = None
trades  = []
eqcurve = []

for ts, row in df.iterrows():
    close = float(row["Close"]); high = float(row["High"])
    low   = float(row["Low"]);   atr  = float(row["ATR"])
    sd    = atr * SL_MULT

    if pos is not None:
        # Track most favourable price for the short
        if low < pos["best"]:
            pos["best"] = low

        # Trailing stop update
        if pos["best"] <= pos["trail_activate_px"]:
            pos["sl"] = min(pos["sl"], pos["best"] + pos["trail_dist_fixed"])

        htp = low  <= pos["tp"]
        hsl = high >= pos["sl"]

        if htp or hsl:
            xp       = pos["tp"] if htp else pos["sl"]
            pnl      = (pos["entry"] - xp) / pos["entry"]
            dp       = pnl * pos["notional"] - pos["notional"] * COMMISSION_PCT * 2
            equity  += dp
            result   = "TP" if htp else "SL"

            trades.append({
                "entry_time": pos["entry_time"],
                "exit_time":  ts,
                "direction":  pos["direction"],
                "entry":      pos["entry"],
                "exit":       xp,
                "result":     result,
                "pnl_pct":    round(pnl * 100, 3),
                "dollar_pnl": round(dp, 2),
                "equity":     round(equity, 2),
            })
            pos = None

    if pos is None and bool(short_signal[ts]):
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
tp_cnt  = (tdf["result"] == "TP").sum()
sl_cnt  = (tdf["result"] == "SL").sum()
long_c = (tdf["direction"] == "long").sum()
shrt_c = (tdf["direction"] == "short").sum()
aw     = wins["dollar_pnl"].mean()   if not wins.empty   else 0.0
al     = losses["dollar_pnl"].mean() if not losses.empty else 0.0
rr     = aw / abs(al) if al != 0 else float("inf")
ret    = (final / INITIAL_CAPITAL - 1) * 100

eq_s = pd.Series([e["equity"] for e in eqcurve])
mdd  = ((eq_s - eq_s.cummax()) / eq_s.cummax() * 100).min()

print("=" * 60)
print(f"  APM v3.4  —  {TICKER} {INTERVAL}  ({PERIOD})")
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

out_csv = f"apm_v3_trades_{TICKER.lower()}_{INTERVAL}.csv"
tdf.to_csv(out_csv, index=False)
print(f"\nTrades CSV → {out_csv}")

# ─── Charts ───────────────────────────────────────────────────────────────────
ec_df = pd.DataFrame(eqcurve).set_index("time")
plt.style.use("dark_background")

fig, axes = plt.subplots(3, 1, figsize=(18, 14),
                         gridspec_kw={"height_ratios": [3, 1.5, 1.5]})
fig.suptitle(
    f"APM v3.4  ·  {TICKER} {INTERVAL}  ·  "
    f"ADX>{ADX_THRESH}  SL×{SL_MULT}  TP×{TP_MULT}  Trail×{TRAIL_DIST}  Risk={RISK_PCT*100:.0f}%  "
    f"Return={ret:+.2f}%  PF={pf:.3f}",
    fontsize=11)

# Panel 1 — price + EMAs + trade markers
ax1 = axes[0]
ax1.plot(df.index, df["Close"],    color="#cccccc", lw=0.7, label="Close")
ax1.plot(df.index, df["EMA_SLOW"], color="#f6e05e", lw=2.0, label=f"EMA {EMA_SLOW}")
ax1.plot(df.index, df["EMA_MID"],  color="#f6ad55", lw=1.0, ls="--", alpha=0.8, label=f"EMA {EMA_MID}")
ax1.plot(df.index, df["EMA_FAST"], color="#5b9ef4", lw=1.0, ls="--", alpha=0.8, label=f"EMA {EMA_FAST}")

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
out_png = f"apm_v3_equity_{TICKER.lower()}_{INTERVAL}.png"
plt.savefig(out_png, dpi=150, bbox_inches="tight")
print(f"Chart → {out_png}")
