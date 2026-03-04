"""
Faithful Python backtest of Adaptive Pullback Momentum v4.0 (v1.1 defaults)
Timeframe : 1D BTC-USD, period="max" (~11 years via yfinance, back to 2014)
Commission : 0.06 % per side   Risk : 1 % equity / trade
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

# ── Strategy defaults (v1.1 / v4.0) ───────────────────────────────────────────
EMA_FAST_LEN = 21
EMA_MID_LEN  = 50
EMA_SLOW_LEN = 200
ADX_LEN      = 14
ADX_THRESH   = 25.0
PB_PCT       = 0.15
VOL_MA_LEN   = 20
VOL_MULT     = 1.0
MIN_BODY     = 0.15
PANIC_MULT   = 1.5
ATR_LEN      = 14
ATR_BL_LEN   = 60
SL_MULT      = 1.5
TP_MULT      = 2.0
TRAIL_ACT    = 1.5
TRAIL_DIST   = 0.8
RSI_LEN      = 14
RSI_LO_L     = 42.0; RSI_HI_L = 68.0
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

df["EMA_F"]  = ema(df["Close"], EMA_FAST_LEN)
df["EMA_M"]  = ema(df["Close"], EMA_MID_LEN)
df["EMA_S"]  = ema(df["Close"], EMA_SLOW_LEN)
df["ATR"]    = atr_series(df["High"], df["Low"], df["Close"], ATR_LEN)
df["ATR_BL"] = df["ATR"].rolling(ATR_BL_LEN).mean()
df["ADX"]    = adx_series(df["High"], df["Low"], df["Close"], ADX_LEN)
df["RSI"]    = rsi(df["Close"], RSI_LEN)
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

# ── Bar-by-bar simulation ──────────────────────────────────────────────────────
equity     = INIT_CAP
in_trade   = False
direction  = None
entry_px   = sl_price = tp_price = best_price = entry_atr = qty = 0.0
entry_time = None

trades = []
equity_curve = [equity]

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

    eff = max(ca, c[i] * ATR_FLOOR)
    exited = False

    if in_trade:
        if direction == "long":
            if h[i] > best_price: best_price = h[i]
            if best_price >= entry_px + entry_atr * TRAIL_ACT:
                t = best_price - entry_atr * TRAIL_DIST
                if t > sl_price: sl_price = t
            if l_[i] <= sl_price:
                ep = min(o[i], sl_price); pnl = (ep - entry_px) * qty
                comm = (entry_px + ep) * qty * COMMISSION
                equity += pnl - comm
                trades.append({"entry_time": entry_time, "exit_time": idx[i],
                                "direction": "long", "entry": entry_px, "exit": ep,
                                "pnl": pnl - comm, "equity": equity, "exit_reason": "SL/TR"})
                in_trade = False; exited = True
            elif h[i] >= tp_price:
                ep = max(o[i], tp_price); pnl = (ep - entry_px) * qty
                comm = (entry_px + ep) * qty * COMMISSION
                equity += pnl - comm
                trades.append({"entry_time": entry_time, "exit_time": idx[i],
                                "direction": "long", "entry": entry_px, "exit": ep,
                                "pnl": pnl - comm, "equity": equity, "exit_reason": "TP"})
                in_trade = False; exited = True

        else:  # short
            if l_[i] < best_price: best_price = l_[i]
            if best_price <= entry_px - entry_atr * TRAIL_ACT:
                t = best_price + entry_atr * TRAIL_DIST
                if t < sl_price: sl_price = t
            if h[i] >= sl_price:
                ep = max(o[i], sl_price); pnl = (entry_px - ep) * qty
                comm = (entry_px + ep) * qty * COMMISSION
                equity += pnl - comm
                trades.append({"entry_time": entry_time, "exit_time": idx[i],
                                "direction": "short", "entry": entry_px, "exit": ep,
                                "pnl": pnl - comm, "equity": equity, "exit_reason": "SL/TR"})
                in_trade = False; exited = True
            elif l_[i] <= tp_price:
                ep = min(o[i], tp_price); pnl = (entry_px - ep) * qty
                comm = (entry_px + ep) * qty * COMMISSION
                equity += pnl - comm
                trades.append({"entry_time": entry_time, "exit_time": idx[i],
                                "direction": "short", "entry": entry_px, "exit": ep,
                                "pnl": pnl - comm, "equity": equity, "exit_reason": "TP"})
                in_trade = False; exited = True

    if not in_trade:
        if l_e[i]:
            sd = eff * SL_MULT; entry_px = c[i]; sl_price = entry_px - sd
            tp_price = entry_px + eff * TP_MULT; entry_atr = eff
            best_price = entry_px; qty = equity * RISK_PCT / sd
            entry_time = idx[i]; direction = "long"; in_trade = True
        elif s_e[i]:
            sd = eff * SL_MULT; entry_px = c[i]; sl_price = entry_px + sd
            tp_price = entry_px - eff * TP_MULT; entry_atr = eff
            best_price = entry_px; qty = equity * RISK_PCT / sd
            entry_time = idx[i]; direction = "short"; in_trade = True

    equity_curve.append(equity)

# ── Results ────────────────────────────────────────────────────────────────────
tdf = pd.DataFrame(trades)
print(f"\n{'='*58}")
print(f"  APM v4.0 (v1.1 defaults)  |  {TICKER} {INTERVAL}  |  Baseline")
print(f"{'='*58}")

if tdf.empty:
    print("  No trades generated.")
else:
    wins   = tdf[tdf["pnl"] > 0]; losses = tdf[tdf["pnl"] <= 0]
    total  = len(tdf); wr = len(wins) / total * 100
    net    = tdf["pnl"].sum(); net_pct = net / INIT_CAP * 100
    gp     = wins["pnl"].sum(); gl = abs(losses["pnl"].sum())
    pf     = gp / gl if gl > 0 else float("inf")
    avg_w  = wins["pnl"].mean() if not wins.empty else 0
    avg_l  = losses["pnl"].mean() if not losses.empty else 0

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
        lw = (longs_df["pnl"] > 0).sum()
        print(f"\n  Longs : {len(longs_df)} trades  WR={lw/len(longs_df)*100:.1f}%  "
              f"Net=${longs_df['pnl'].sum():+.2f}")
    if not shorts_df.empty:
        sw = (shorts_df["pnl"] > 0).sum()
        print(f"  Shorts: {len(shorts_df)} trades  WR={sw/len(shorts_df)*100:.1f}%  "
              f"Net=${shorts_df['pnl'].sum():+.2f}")

    print(f"\n  Exit breakdown:")
    print(tdf["exit_reason"].value_counts().to_string())

    # Year-by-year breakdown
    tdf["year"] = pd.to_datetime(tdf["entry_time"]).dt.year
    print(f"\n  Year-by-year:")
    for yr, grp in tdf.groupby("year"):
        yw = (grp["pnl"] > 0).sum(); yn = len(grp)
        print(f"    {yr}  n={yn:2d}  WR={yw/yn*100:.0f}%  Net=${grp['pnl'].sum():+.2f}")

    tdf.to_csv("apm_v4_trades_btcusd_1d.csv", index=False)
    print(f"\n  Saved → apm_v4_trades_btcusd_1d.csv")

print(f"{'='*58}")
