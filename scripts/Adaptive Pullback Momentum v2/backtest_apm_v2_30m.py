# ─────────────────────────────────────────────────────────────────────────────
# APM v2.0 — Python backtest (faithful translation of the Pine Script)
#
# Pine Script entry logic (verbatim):
#   Long  : close > EMA200  | EMA21 > EMA50  | prev-bar low ≤ EMA21*(1+pb%)
#            current bar: close > EMA21 & close > open & body ≥ 0.15×ATR
#            + RSI 42–68  | Volume ≥ 1×VolSMA  | ADX > 25  | no panic
#   Short : mirror (close < EMA200, EMA21 < EMA50, prev-bar high ≥ EMA21*(1-pb%))
#
# Exits:
#   Hard SL  : entry ± ATR×1.5
#   Hard TP  : entry ± ATR×2.0
#   Trail    : activates after ATR×1.5 profit, then trails ATR×0.8 from best
#
# Sizing: 1% equity risked per trade  |  Commission: 0.06% per side
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

# ── Pine Script defaults ───────────────────────────────────────────────────────
PB_PCT     = 0.15    # pullback tolerance %
ADX_THRESH = 25      # ADX threshold
VOL_MULT   = 1.0     # volume multiplier
MIN_BODY   = 0.15    # min |close-open|/ATR
SL_MULT    = 1.5     # stop   = entry ± ATR×SL_MULT
TP_MULT    = 2.0     # target = entry ± ATR×TP_MULT
TRAIL_ACT  = 1.5     # trail activates at ATR×TRAIL_ACT profit
TRAIL_DIST = 0.8     # trail stays ATR×TRAIL_DIST from best price
PANIC_MULT = 1.5     # ATR > ATR_BL × PANIC_MULT → no entries

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

# ─── Signal construction (mirrors Pine Script exactly) ─────────────────────────
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

is_trending = df["ADX"] > ADX_THRESH
is_panic    = df["ATR"]  > df["ATR_BL"] * PANIC_MULT
vol_ok      = df["Volume"] >= df["VOL_MA"] * VOL_MULT
rsi_long_ok  = (df["RSI"] >= RSI_LO_L) & (df["RSI"] <= RSI_HI_L)
rsi_short_ok = (df["RSI"] >= RSI_LO_S) & (df["RSI"] <= RSI_HI_S)

ema_bull = (df["Close"]    > df["EMA_SLOW"]) & (df["EMA_FAST"] > df["EMA_MID"])
ema_bear = (df["Close"]    < df["EMA_SLOW"]) & (df["EMA_FAST"] < df["EMA_MID"])

long_signal = (
    TRADE_LONGS &
    long_pb      &
    ema_bull     &
    rsi_long_ok  &
    vol_ok       &
    is_trending  &
    ~is_panic
)

short_signal = (
    TRADE_SHORTS &
    short_pb     &
    ema_bear     &
    rsi_short_ok &
    vol_ok       &
    is_trending  &
    ~is_panic
)

# ─── Signal diagnostics ─────────────────────────────────────────────────────────
components_long = [
    ("long_pb",      long_pb),
    ("ema_bull",     ema_bull),
    ("rsi_long_ok",  rsi_long_ok),
    ("vol_ok",       vol_ok),
    ("is_trending",  is_trending),
    ("~is_panic",    ~is_panic),
]
components_short = [
    ("short_pb",     short_pb),
    ("ema_bear",     ema_bear),
    ("rsi_short_ok", rsi_short_ok),
    ("vol_ok",       vol_ok),
    ("is_trending",  is_trending),
    ("~is_panic",    ~is_panic),
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

# ─── Bar-by-bar simulation ──────────────────────────────────────────────────────
equity   = INITIAL_CAPITAL
pos      = None
trades   = []
eqcurve  = []

for ts, row in df.iterrows():
    close = float(row["Close"]); high = float(row["High"])
    low   = float(row["Low"]);   atr  = float(row["ATR"])

    # reset per-bar exit flags
    htp = hsl = False
    xp  = pnl = 0.0
    d   = None

    # ── manage open position ──────────────────────────────────────────────────
    if pos is not None:
        d = pos["direction"]
        if d == "long":
            if high > pos["best"]: pos["best"] = high
            # trail: use entry-bar ATR (locked) to avoid ATR-shrink bug
            if pos["best"] >= pos["trail_activate_px"]:
                new_sl = pos["best"] - pos["trail_dist_fixed"]
                pos["sl"] = max(pos["sl"], new_sl)
            htp = high >= pos["tp"]
            hsl = low  <= pos["sl"]
        else:  # short
            if low < pos["best"]: pos["best"] = low
            if pos["best"] <= pos["trail_activate_px"]:
                new_sl = pos["best"] + pos["trail_dist_fixed"]
                pos["sl"] = min(pos["sl"], new_sl)
            htp = low  <= pos["tp"]
            hsl = high >= pos["sl"]

        if htp or hsl:
            xp  = pos["tp"] if htp else pos["sl"]
            if d == "long":
                pnl = (xp - pos["entry"]) / pos["entry"]
            else:
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

    # ── new entry ─────────────────────────────────────────────────────────────
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
            # lock trail thresholds to entry-bar ATR
            tap   = (close + atr * TRAIL_ACT if sig == "long"
                     else close - atr * TRAIL_ACT)
            tdf   = atr * TRAIL_DIST
            pos   = {"direction": sig, "entry": close, "entry_time": ts,
                     "sl": sl, "tp": tp, "best": close, "notional": notl,
                     "trail_activate_px": tap, "trail_dist_fixed": tdf}

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
    print(f"  APM v2.0  —  {TICKER} {INTERVAL}  (max)")
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

    # ── Equity chart ─────────────────────────────────────────────────────────
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
    ax1.set_title(f"APM v2.0  |  {TICKER} {INTERVAL}  |  "
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
