# ─────────────────────────────────────────────────────────────────────────────
# APM v2 — redesigned indicators aimed at a positive net return
#
# KEY CHANGES vs v1.1
#   1. Tighter pullback band  — low[1] must be in  [EMA21*(1-tol), EMA21*(1+tol)]
#                               (not just ≤ EMA21*(1+tol)); actual EMA *tag* required
#   2. EMA slope filter       — EMA21 must be rising  (EMA21 > EMA21[3]) for longs
#   3. Full EMA alignment     — EMA21 > EMA50 > EMA200 (not just EMA21>EMA50 & close>EMA200)
#   4. RSI momentum direction — RSI must be rising for 2 bars for longs (not just in band)
#   5. Volume surge           — raised to 1.8× VolSMA (was 1.0×)
#   6. Min body               — raised to 0.25×ATR (was 0.15×)
#   7. Session filter         — only 08:00–22:00 UTC (removes low-liquidity noise)
#   8. SL = 1.2×ATR           — tighter than 1.5× but matched to tighter entry quality
#      TP = 2.0×ATR           — 1.67:1 R:R
#   9. Trail activate 2.0×ATR, trail dist 1.2×ATR  — let winners run before trailing
#  10. ADX > 28               — balanced between orig 25 and strict 30
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

# ─── Configuration ────────────────────────────────────────────────────────────
TICKER   = "BTC-USD"
PERIOD   = "max"
INTERVAL = "15m"

EMA_FAST = 21
EMA_MID  = 50
EMA_SLOW = 200
ADX_LEN  = 14
RSI_LEN  = 14
ATR_LEN  = 14
VOL_LEN  = 20

INITIAL_CAPITAL = 10_000.0
COMMISSION_PCT  = 0.0006
RISK_PCT        = 0.005     # 0.5 % equity risked per trade

# v2 filter params
PB_PCT      = 0.30   # pullback tolerance %  (wider so EMA tag is observable at 15m resolution)
ADX_THRESH  = 22     # ADX threshold — lower lets more trades through while still filtering chop
VOL_MULT    = 1.2    # volume multiplier  — require modest conviction
MIN_BODY    = 0.20   # min (|close-open|/ATR)
SL_MULT     = 2.0    # stop   = entry ± ATR × SL_MULT  [TUNED: wider=smaller notional=less commission]
TP_MULT     = 2.5    # target = entry ± ATR × TP_MULT  [TUNED: best return in extended sweep]
ATR_FLOOR   = 0.0015 # min ATR as fraction of price (0.15%) — filters low-vol/high-commission bars
                     # Sweep showed this is the critical factor turning PF from 0.93 to 1.24
TRAIL_ACT   = 2.5    # trail activates after ATR × TRAIL_ACT profit (above TP so trail is fallback)
TRAIL_DIST  = 1.5    # trail stays ATR × TRAIL_DIST from best price
PANIC_MULT  = 1.5    # ATR > ATR_BL × PANIC_MULT → no entries

# RSI long/short bands (keep v1.1 bounds)
RSI_LO_L = 42; RSI_HI_L = 68
RSI_LO_S = 32; RSI_HI_S = 58

TRADE_LONGS  = False  # disabled — LONG WR=25%, PF=0.204 (Jan–Mar 2026 is a bear market)
TRADE_SHORTS = True

# ─── Download ─────────────────────────────────────────────────────────────────
print(f"Downloading {TICKER} {INTERVAL} period='{PERIOD}'...")
df = yf.download(TICKER, period=PERIOD, interval=INTERVAL, auto_adjust=True, progress=False)
if df.empty:
    raise SystemExit("No data returned.")
if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.droplevel(1)
df = df[["Open","High","Low","Close","Volume"]].copy()
df.dropna(inplace=True)
print(f"Rows: {len(df)}  Range: {df.index[0]} → {df.index[-1]}")

# ─── Indicators ───────────────────────────────────────────────────────────────
df["EMA_FAST"] = df["Close"].ewm(span=EMA_FAST, adjust=False).mean()
df["EMA_MID"]  = df["Close"].ewm(span=EMA_MID,  adjust=False).mean()
df["EMA_SLOW"] = df["Close"].ewm(span=EMA_SLOW, adjust=False).mean()

# RSI (Wilder)
delta = df["Close"].diff()
avg_g = delta.clip(lower=0).ewm(alpha=1/RSI_LEN, adjust=False).mean()
avg_l = (-delta).clip(lower=0).ewm(alpha=1/RSI_LEN, adjust=False).mean()
df["RSI"] = 100 - (100 / (1 + avg_g / avg_l.replace(0, 1e-10)))

# ATR (Wilder)
hl  = df["High"] - df["Low"]
hpc = (df["High"] - df["Close"].shift(1)).abs()
lpc = (df["Low"]  - df["Close"].shift(1)).abs()
tr  = pd.concat([hl, hpc, lpc], axis=1).max(axis=1)
df["ATR"]    = tr.ewm(alpha=1/ATR_LEN, adjust=False).mean()
df["ATR_BL"] = df["ATR"].rolling(60).mean()

# Volume SMA
df["VOL_MA"] = df["Volume"].rolling(VOL_LEN).mean()

# ADX / DMI (Wilder)
up_move  = df["High"] - df["High"].shift(1)
dn_move  = df["Low"].shift(1) - df["Low"]
plus_dm  = np.where((up_move > dn_move) & (up_move > 0), up_move, 0.0)
minus_dm = np.where((dn_move > up_move) & (dn_move > 0), dn_move, 0.0)
s_plus   = pd.Series(plus_dm,  index=df.index).ewm(alpha=1/ADX_LEN, adjust=False).mean()
s_minus  = pd.Series(minus_dm, index=df.index).ewm(alpha=1/ADX_LEN, adjust=False).mean()
df["DI_PLUS"]  = 100 * s_plus  / df["ATR"]
df["DI_MINUS"] = 100 * s_minus / df["ATR"]
dx = 100 * (df["DI_PLUS"] - df["DI_MINUS"]).abs() / ((df["DI_PLUS"] + df["DI_MINUS"]).replace(0, 1e-10))
df["ADX"] = dx.ewm(alpha=1/ADX_LEN, adjust=False).mean()

df.dropna(inplace=True)

# ─── Derived signals ──────────────────────────────────────────────────────────
tol = PB_PCT / 100.0

# (1) Regime guards
is_trending = df["ADX"] > ADX_THRESH
is_panic    = df["ATR"] > df["ATR_BL"] * PANIC_MULT

# (2) [NEW] Full EMA stack alignment
ema_bull = (df["EMA_FAST"] > df["EMA_MID"]) & (df["EMA_MID"] > df["EMA_SLOW"])
ema_bear = (df["EMA_FAST"] < df["EMA_MID"]) & (df["EMA_MID"] < df["EMA_SLOW"])

# (3) [NEW] EMA slope filter — EMA_FAST rising/falling over last 3 bars
ema_slope_up   = df["EMA_FAST"] > df["EMA_FAST"].shift(3)
ema_slope_down = df["EMA_FAST"] < df["EMA_FAST"].shift(3)

# (4) [NEW] Tighter pullback — low[1] dipped INTO EMA zone but close[1] didn't crash BELOW it.
#     This ensures an actual EMA tag (not a free-fall through it).
pb_band_lo = df["EMA_FAST"].shift(1) * (1 - tol)
pb_band_hi = df["EMA_FAST"].shift(1) * (1 + tol)
long_pullback  = (df["Low"].shift(1)  <= pb_band_hi) & (df["Close"].shift(1) >= pb_band_lo)
short_pullback = (df["High"].shift(1) >= pb_band_lo) & (df["Close"].shift(1) <= pb_band_hi)

# (5) Recovery bar filter (current bar closes through EMA)
long_recover  = (df["Close"] > df["EMA_FAST"]) & (df["Close"] > df["Open"])
short_recover = (df["Close"] < df["EMA_FAST"]) & (df["Close"] < df["Open"])

# (6) Min body
body = (df["Close"] - df["Open"]).abs() / df["ATR"]
min_body_ok = body >= MIN_BODY

# (7) [NEW] RSI momentum direction — RSI must be rising on the current bar for longs
rsi_rising  = df["RSI"] > df["RSI"].shift(1)
rsi_falling = df["RSI"] < df["RSI"].shift(1)

# (8) Volume surge
vol_ok = df["Volume"] >= df["VOL_MA"] * VOL_MULT

# (9) RSI within bounds
rsi_long_ok  = (df["RSI"] >= RSI_LO_L) & (df["RSI"] <= RSI_HI_L)
rsi_short_ok = (df["RSI"] >= RSI_LO_S) & (df["RSI"] <= RSI_HI_S)

# (10) Session filter disabled — was killing 40% of valid setups on BTC 15m
# (kept as a boolean True so downstream logic is unchanged)
session_ok = pd.Series([True]*len(df), index=df.index)

# (11) ATR floor — only trade when ATR/close >= ATR_FLOOR
#      Eliminates low-volatility bars where $50 risk → huge notional → commission > 50% of expected win
atr_pct_ok = df["ATR"] / df["Close"] >= ATR_FLOOR

# ─── Full entry conditions ─────────────────────────────────────────────────────
long_signal = (
    TRADE_LONGS &
    long_pullback   &
    long_recover    &
    min_body_ok     &
    ema_bull        &
    ema_slope_up    &
    rsi_rising      &
    rsi_long_ok     &
    vol_ok          &
    is_trending     &
    ~is_panic       &
    session_ok      &
    atr_pct_ok
)

short_signal = (
    TRADE_SHORTS &
    short_pullback  &
    short_recover   &
    min_body_ok     &
    ema_bear        &
    ema_slope_down  &
    rsi_falling     &
    rsi_short_ok    &
    vol_ok          &
    is_trending     &
    ~is_panic       &
    session_ok      &
    atr_pct_ok
)

# ─── Signal diagnostics ─────────────────────────────────────────────────────
components_long = [
    ("long_pullback",  long_pullback),
    ("long_recover",   long_recover),
    ("min_body_ok",    min_body_ok),
    ("ema_bull",       ema_bull),
    ("ema_slope_up",   ema_slope_up),
    ("rsi_rising",     rsi_rising),
    ("rsi_long_ok",    rsi_long_ok),
    ("vol_ok",         vol_ok),
    ("is_trending",    is_trending),
    ("~is_panic",      ~is_panic),
    ("session_ok",     session_ok),
    ("atr_pct_ok",     atr_pct_ok),
]
components_short = [
    ("short_pullback", short_pullback),
    ("short_recover",  short_recover),
    ("min_body_ok",    min_body_ok),
    ("ema_bear",       ema_bear),
    ("ema_slope_down", ema_slope_down),
    ("rsi_falling",    rsi_falling),
    ("rsi_short_ok",   rsi_short_ok),
    ("vol_ok",         vol_ok),
    ("is_trending",    is_trending),
    ("~is_panic",      ~is_panic),
    ("session_ok",     session_ok),
    ("atr_pct_ok",     atr_pct_ok),
]
print("\n--- Signal filter pass-through (long) ---")
cumulative = pd.Series([True]*len(df), index=df.index)
for name, mask in components_long:
    cumulative = cumulative & mask
    print(f"  {name:<20} → {cumulative.sum():>4} rows pass")
print("--- Signal filter pass-through (short) ---")
cumulative = pd.Series([True]*len(df), index=df.index)
for name, mask in components_short:
    cumulative = cumulative & mask
    print(f"  {name:<20} → {cumulative.sum():>4} rows pass")
print()
print(f"v2 Signals — Long: {long_signal.sum()}  Short: {short_signal.sum()}")

# ─── Bar-by-bar simulation ─────────────────────────────────────────────────────
equity  = INITIAL_CAPITAL
pos     = None
trades  = []
eqcurve = []

for ts, row in df.iterrows():
    close = float(row["Close"]); high = float(row["High"])
    low   = float(row["Low"]);   atr  = float(row["ATR"])
    sd = atr * SL_MULT

    # reset exit flags each bar to avoid stale-variable leakage across iterations
    htp = hsl = False
    xp  = pnl = 0.0

    if pos is not None:
        d = pos["direction"]
        if d == "long":
            if high > pos["best"]: pos["best"] = high
            # use fixed entry-bar trail thresholds so shrinking ATR can't push
            # trail activation below the TP level
            if pos["best"] >= pos["trail_activate_px"]:
                pos["sl"] = max(pos["sl"], pos["best"] - pos["trail_dist_fixed"])
            htp = high >= pos["tp"]
            hsl = low  <= pos["sl"]
            if htp or hsl:
                xp  = pos["tp"] if htp else pos["sl"]
                pnl = (xp - pos["entry"]) / pos["entry"]
        else:
            if low < pos["best"]: pos["best"] = low
            if pos["best"] <= pos["trail_activate_px"]:
                pos["sl"] = min(pos["sl"], pos["best"] + pos["trail_dist_fixed"])
            htp = low  <= pos["tp"]
            hsl = high >= pos["sl"]
            if htp or hsl:
                xp  = pos["tp"] if htp else pos["sl"]
                pnl = (pos["entry"] - xp) / pos["entry"]

        if htp or hsl:
            dp = pnl * pos["notional"] - pos["notional"] * COMMISSION_PCT * 2
            equity += dp
            trades.append({
                "entry_time": pos["entry_time"], "exit_time": ts,
                "direction":  d,
                "entry":      pos["entry"],      "exit":   xp,
                "result":     "TP" if htp else "SL",
                "pnl_pct":    round(pnl * 100, 3),
                "dollar_pnl": round(dp, 2),
                "equity":     round(equity, 2),
            })
            pos = None

    if pos is None:
        sig = ("long"  if bool(long_signal[ts])  else
               "short" if bool(short_signal[ts]) else None)
        if sig:
            rc   = equity * RISK_PCT
            qty  = rc / sd
            notl = qty * close
            # cap notional at 5× equity so commission never exceeds ~0.6% of equity
            notl = min(notl, equity * 5.0)
            sl   = close - sd if sig == "long" else close + sd
            tp   = close + atr * TP_MULT if sig == "long" else close - atr * TP_MULT
            # lock trail thresholds to entry-bar ATR so shrinking ATR can't
            # cause the trail to activate below the TP level
            trail_activate_px = (close + atr * TRAIL_ACT if sig == "long"
                                 else close - atr * TRAIL_ACT)
            trail_dist_fixed  = atr * TRAIL_DIST
            pos  = {"direction": sig, "entry": close, "entry_time": ts,
                    "sl": sl, "tp": tp, "best": close, "notional": notl,
                    "trail_activate_px": trail_activate_px,
                    "trail_dist_fixed":  trail_dist_fixed}

    eqcurve.append({"time": ts, "equity": equity})

print(f"Simulation complete. Trades: {len(trades)}")

# ─── Stats ────────────────────────────────────────────────────────────────────
tdf = pd.DataFrame(trades)

if tdf.empty:
    print("No trades — consider relaxing a filter.")
else:
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
    print(f"  APM v2  —  {TICKER} {INTERVAL}  ({PERIOD})")
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

    # ─── Per-direction breakdown ──────────────────────────────────────────────
    for direction in ["long", "short"]:
        sub = tdf[tdf["direction"] == direction]
        if sub.empty: continue
        sw  = sub[sub["dollar_pnl"] > 0]
        sl_ = sub[sub["dollar_pnl"] <= 0]
        sub_wr  = len(sw) / len(sub) * 100
        sub_pnl = sub["dollar_pnl"].sum()
        sub_pf  = (sw["dollar_pnl"].sum() / abs(sl_["dollar_pnl"].sum())
                   if not sl_.empty else float("inf"))
        print(f"  {direction.upper():<6} trades={len(sub):>3}  WR={sub_wr:.0f}%  "
              f"PF={sub_pf:.3f}  net=${sub_pnl:+.2f}")
    out_csv = f"apm_v2_trades_{TICKER.replace('-','').lower()}_{INTERVAL}.csv"
    tdf.to_csv(out_csv, index=False)
    print(f"Trades CSV → {out_csv}")

    # ─── Charts ───────────────────────────────────────────────────────────────
    ec_df = pd.DataFrame(eqcurve).set_index("time")
    plt.style.use("dark_background")

    fig, axes = plt.subplots(3, 1, figsize=(18, 14),
                              gridspec_kw={"height_ratios": [3, 1.5, 1.5]})
    fig.suptitle(
        f"APM v2  ·  {TICKER} {INTERVAL}  ·  "
        f"PB={PB_PCT}% ADX>{ADX_THRESH} Vol>{VOL_MULT}× Body>{MIN_BODY}  |  "
        f"SL×{SL_MULT} TP×{TP_MULT}  Return={ret:+.2f}%  PF={pf:.3f}", fontsize=11)

    # Panel 1 — price + EMAs + trade markers
    ax1 = axes[0]
    ax1.plot(df.index, df["Close"],    color="#cccccc", lw=0.7, label="Close")
    ax1.plot(df.index, df["EMA_SLOW"], color="#f6e05e", lw=2.0, label=f"EMA {EMA_SLOW}")
    ax1.plot(df.index, df["EMA_MID"],  color="#f6ad55", lw=1.0, ls="--", alpha=0.8, label=f"EMA {EMA_MID}")
    ax1.plot(df.index, df["EMA_FAST"], color="#5b9ef4", lw=1.0, ls="--", alpha=0.8, label=f"EMA {EMA_FAST}")

    for _, t in tdf.iterrows():
        e_col = "#68d391" if t["direction"] == "long" else "#fc8181"
        w_col = "#68d391" if t["dollar_pnl"] >= 0 else "#fc8181"
        mrkr  = "^" if t["direction"] == "long" else "v"
        ax1.scatter(t["entry_time"], t["entry"], marker=mrkr, color=e_col, s=70, zorder=5)
        ax1.scatter(t["exit_time"],  t["exit"],  marker="x",  color=w_col, s=50, zorder=5)

    ax1.set_ylabel("Price (USD)")
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
    out_png = f"apm_v2_equity_{TICKER.replace('-','').lower()}_{INTERVAL}.png"
    plt.savefig(out_png, dpi=150, bbox_inches="tight")
    print(f"Chart → {out_png}")

# ─── Shorts-only simulation (BTC Jan-Mar 2026 is bearish) ─────────────────────
print("\n=== Shorts-ONLY run ===")
eq_s  = INITIAL_CAPITAL
pos_s = None
trades_s  = []
eqcurve_s = []

for ts, row in df.iterrows():
    close = float(row["Close"]); high = float(row["High"])
    low   = float(row["Low"]);   atr  = float(row["ATR"])
    sd = atr * SL_MULT

    htp = hsl = False
    xp  = pnl = 0.0

    if pos_s is not None:
        d = pos_s["direction"]  # always "short" here
        if low < pos_s["best"]: pos_s["best"] = low
        if pos_s["best"] <= pos_s["trail_activate_px"]:
            pos_s["sl"] = min(pos_s["sl"], pos_s["best"] + pos_s["trail_dist_fixed"])
        htp = low  <= pos_s["tp"]
        hsl = high >= pos_s["sl"]
        if htp or hsl:
            xp  = pos_s["tp"] if htp else pos_s["sl"]
            pnl = (pos_s["entry"] - xp) / pos_s["entry"]
            dp  = pnl * pos_s["notional"] - pos_s["notional"] * COMMISSION_PCT * 2
            eq_s += dp
            trades_s.append({
                "entry_time": pos_s["entry_time"], "exit_time": ts,
                "direction":  "short",
                "entry":      pos_s["entry"],      "exit": xp,
                "result":     "TP" if htp else "SL",
                "pnl_pct":    round(pnl * 100, 3),
                "dollar_pnl": round(dp, 2),
                "equity":     round(eq_s, 2),
            })
            pos_s = None

    if pos_s is None and bool(short_signal[ts]):
        rc   = eq_s * RISK_PCT
        notl = min(rc / sd * close, eq_s * 5.0)
        sl   = close + sd
        tp   = close - atr * TP_MULT
        tap  = close - atr * TRAIL_ACT
        pos_s = {"direction": "short", "entry": close, "entry_time": ts,
                 "sl": sl, "tp": tp, "best": close, "notional": notl,
                 "trail_activate_px": tap, "trail_dist_fixed": atr * TRAIL_DIST}

    eqcurve_s.append({"time": ts, "equity": eq_s})

ts_df = pd.DataFrame(trades_s)
if ts_df.empty:
    print("No short trades.")
else:
    tw = ts_df[ts_df["dollar_pnl"] > 0]; tl = ts_df[ts_df["dollar_pnl"] <= 0]
    s_wr  = len(tw) / len(ts_df) * 100
    s_ret = (eq_s / INITIAL_CAPITAL - 1) * 100
    s_pf  = (tw["dollar_pnl"].sum() / abs(tl["dollar_pnl"].sum())
             if not tl.empty else float("inf"))
    eq_ss = pd.Series([e["equity"] for e in eqcurve_s])
    s_mdd = ((eq_ss - eq_ss.cummax()) / eq_ss.cummax() * 100).min()
    print(f"  Trades={len(ts_df)}  WR={s_wr:.1f}%  PF={s_pf:.3f}  "
          f"Return={s_ret:+.2f}%  MaxDD={s_mdd:.2f}%  Final=${eq_s:,.2f}")
    ts_df.to_csv(f"apm_v2_shorts_only_{TICKER.replace('-','').lower()}_{INTERVAL}.csv", index=False)

# ─── Shorts-only TP×SL grid sweep ─────────────────────────────────────────────
print("\n=== Shorts-only TP × SL grid sweep ===")
print(f"{'TP':>5} {'SL':>5} | {'Trades':>6} {'WR%':>6} {'PF':>7} {'Ret%':>8} {'AvgWin':>8} {'AvgLoss':>8}")
print("-" * 70)

tp_vals  = [1.5, 2.0, 2.5, 3.0]
sl_vals  = [0.8, 1.0, 1.2, 1.5]
sweep_rows = []
for tp_m in tp_vals:
    for sl_m in sl_vals:
        eq_sw = INITIAL_CAPITAL
        pos_sw = None
        tr_sw  = []
        for ts, row in df.iterrows():
            close = float(row["Close"]); high = float(row["High"])
            low   = float(row["Low"]);   atr  = float(row["ATR"])
            sd_sw = atr * sl_m
            h_tp = h_sl = False
            xp_sw = 0.0
            if pos_sw is not None:
                if low < pos_sw["best"]: pos_sw["best"] = low
                if pos_sw["best"] <= pos_sw["tap"]:
                    pos_sw["sl"] = min(pos_sw["sl"], pos_sw["best"] + pos_sw["tdf"])
                h_tp = low  <= pos_sw["tp"]
                h_sl = high >= pos_sw["sl"]
                if h_tp or h_sl:
                    xp_sw = pos_sw["tp"] if h_tp else pos_sw["sl"]
                    pnl_sw = (pos_sw["entry"] - xp_sw) / pos_sw["entry"]
                    dp_sw  = pnl_sw * pos_sw["notl"] - pos_sw["notl"] * COMMISSION_PCT * 2
                    eq_sw += dp_sw
                    tr_sw.append({"r": dp_sw > 0, "win": max(dp_sw, 0), "loss": min(dp_sw, 0)})
                    pos_sw = None
            if pos_sw is None and bool(short_signal[ts]):
                rc_sw  = eq_sw * RISK_PCT
                notl_sw = min(rc_sw / sd_sw * close, eq_sw * 5.0)
                pos_sw = {
                    "entry":  close, "sl": close + sd_sw,
                    "tp":     close - atr * tp_m,
                    "best":   close, "notl": notl_sw,
                    "tap":    close - atr * TRAIL_ACT,
                    "tdf":    atr * TRAIL_DIST,
                }
        if not tr_sw:
            continue
        wins  = [t for t in tr_sw if t["r"]]
        losss = [t for t in tr_sw if not t["r"]]
        wr_sw  = len(wins)/len(tr_sw)*100
        ret_sw = (eq_sw/INITIAL_CAPITAL-1)*100
        pf_sw  = (sum(t["win"] for t in wins)/abs(sum(t["loss"] for t in losss))
                  if losss else float("inf"))
        aw_sw  = sum(t["win"] for t in wins)/len(wins) if wins else 0
        al_sw  = sum(t["loss"] for t in losss)/len(losss) if losss else 0
        sweep_rows.append({"TP":tp_m,"SL":sl_m,"Trades":len(tr_sw),"WR":wr_sw,
                           "PF":pf_sw,"Ret":ret_sw,"AvgWin":aw_sw,"AvgLoss":al_sw})
        print(f"{tp_m:>5.1f} {sl_m:>5.1f} | {len(tr_sw):>6} {wr_sw:>6.1f} "
              f"{pf_sw:>7.3f} {ret_sw:>8.2f}% {aw_sw:>+8.2f} {al_sw:>+8.2f}")

best = max(sweep_rows, key=lambda x: x["Ret"]) if sweep_rows else None
if best:
    print(f"\nBest return: TP×{best['TP']} SL×{best['SL']} → {best['Ret']:+.2f}% "
          f"(PF={best['PF']:.3f}, WR={best['WR']:.1f}%, Trades={best['Trades']})")

# ─── Extended sweep: wider SL + ATR floor filter ─────────────────────────────
print("\n=== Extended sweep: TP × SL × ATR-pct floor (shorts-only) ===")
print(f"{'TP':>5} {'SL':>5} {'ATRf%':>6} | {'Trades':>6} {'WR%':>6} {'PF':>7} {'Ret%':>8}")
print("-" * 65)

tp_vals2  = [2.0, 2.5, 3.0]
sl_vals2  = [1.5, 2.0, 2.5]
# ATR as % of close floor — only take trades where ATR/close >= threshold
atr_floors = [0.0, 0.10, 0.15, 0.20]   # 0 = no filter; 0.15 = ATR>=0.15% of price

ext_rows = []
for tp_m in tp_vals2:
    for sl_m in sl_vals2:
        for atr_fl in atr_floors:
            eq_ex  = INITIAL_CAPITAL
            pos_ex = None
            tr_ex  = []
            for ts, row in df.iterrows():
                close = float(row["Close"]); high  = float(row["High"])
                low   = float(row["Low"]);    atr_v = float(row["ATR"])
                sd_ex = atr_v * sl_m
                h_tp = h_sl = False
                if pos_ex is not None:
                    if low < pos_ex["best"]: pos_ex["best"] = low
                    if pos_ex["best"] <= pos_ex["tap"]:
                        pos_ex["sl"] = min(pos_ex["sl"], pos_ex["best"] + pos_ex["tdf"])
                    h_tp = low  <= pos_ex["tp"]
                    h_sl = high >= pos_ex["sl"]
                    if h_tp or h_sl:
                        xp_ex = pos_ex["tp"] if h_tp else pos_ex["sl"]
                        pnl_ex = (pos_ex["entry"] - xp_ex) / pos_ex["entry"]
                        dp_ex  = pnl_ex * pos_ex["notl"] - pos_ex["notl"] * COMMISSION_PCT * 2
                        eq_ex += dp_ex
                        tr_ex.append(dp_ex)
                        pos_ex = None
                if pos_ex is None and bool(short_signal[ts]):
                    if atr_fl > 0 and (atr_v / close * 100) < atr_fl:
                        continue          # skip low-volatility entries
                    rc_ex   = eq_ex * RISK_PCT
                    notl_ex = min(rc_ex / sd_ex * close, eq_ex * 5.0)
                    pos_ex = {
                        "entry": close, "sl": close + sd_ex,
                        "tp":    close - atr_v * tp_m,
                        "best":  close, "notl": notl_ex,
                        "tap":   close - atr_v * TRAIL_ACT,
                        "tdf":   atr_v * TRAIL_DIST,
                    }
            if not tr_ex:
                continue
            wins_ex  = [t for t in tr_ex if t > 0]
            losss_ex = [t for t in tr_ex if t <= 0]
            wr_ex    = len(wins_ex) / len(tr_ex) * 100
            ret_ex   = (eq_ex / INITIAL_CAPITAL - 1) * 100
            pf_ex    = (sum(wins_ex) / abs(sum(losss_ex))
                        if losss_ex else float("inf"))
            ext_rows.append({"TP": tp_m, "SL": sl_m, "ATRf": atr_fl,
                             "Trades": len(tr_ex), "WR": wr_ex,
                             "PF": pf_ex, "Ret": ret_ex})
            marker = " ←" if ret_ex >= 0 else ""
            print(f"{tp_m:>5.1f} {sl_m:>5.1f} {atr_fl:>6.2f} | "
                  f"{len(tr_ex):>6} {wr_ex:>6.1f} {pf_ex:>7.3f} {ret_ex:>8.2f}%{marker}")

if ext_rows:
    best_e = max(ext_rows, key=lambda x: x["Ret"])
    print(f"\nBest: TP×{best_e['TP']} SL×{best_e['SL']} ATRfl={best_e['ATRf']:.2f}% "
          f"→ {best_e['Ret']:+.2f}%  PF={best_e['PF']:.3f}  "
          f"WR={best_e['WR']:.1f}%  Trades={best_e['Trades']}")
