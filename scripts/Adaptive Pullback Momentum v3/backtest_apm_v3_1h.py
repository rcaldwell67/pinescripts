"""
Faithful Python backtest of Adaptive Pullback Momentum v3.1
Timeframe : 1h BTC-USD, period="max" (~730 days via yfinance)
Commission : 0.06 % per side   Risk : 1 % equity / trade

v3.1 optimal parameters (7-phase sweep over BTC-USD 1h max history):
  Longs only | ADX>35 | SL×1.5 | TP×1.5 | Trail act×2.5 | Trail dist×0.5
  Vol×1.5 | Body×0.20 | ATR floor 0.30% | EMA slope (3-bar) | RSI 42-72
  Result: +6.31%, PF=3.682, WR=83.3%, 12 trades, MaxDD=-1.18%
"""

import pandas as pd
import numpy as np
import yfinance as yf
import warnings
warnings.filterwarnings("ignore")

# ── Configuration ──────────────────────────────────────────────────────────────
TICKER     = "BTC-USD"
INTERVAL   = "1h"
PERIOD     = "max"          # ~730 days for 1h on yfinance
INIT_CAP   = 10_000.0
COMMISSION = 0.0006         # 0.06 % per side
RISK_PCT   = 0.01           # 1 % equity per trade

# ── Strategy defaults (v3.1 — sweep-optimised) ────────────────────────────────
EMA_FAST_LEN = 21
EMA_MID_LEN  = 50
EMA_SLOW_LEN = 200
ADX_LEN      = 14
ADX_THRESH   = 35.0
PB_PCT       = 0.10         # % pullback tolerance
VOL_MA_LEN   = 20
VOL_MULT     = 1.5
MIN_BODY     = 0.20         # minimum body in ATR units
PANIC_MULT   = 1.5
ATR_LEN      = 14
ATR_BL_LEN   = 50          # ATR baseline (SMA of ATR)
SL_MULT      = 1.5
TP_MULT      = 1.5
TRAIL_ACT    = 2.5
TRAIL_DIST   = 0.5
RSI_LEN      = 14
RSI_LO_L     = 42.0; RSI_HI_L = 72.0   # long RSI band
RSI_LO_S     = 32.0; RSI_HI_S = 58.0   # short RSI band (unused — shorts off)
TRADE_LONGS  = True
TRADE_SHORTS = False
ATR_FLOOR    = 0.0030       # 0.30% of price — floors ATR for sizing
USE_EMA_SLOPE = True        # require EMA-fast rising (3-bar)

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
    up = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    dn = (-d).clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))

def true_range(h, l, pc):
    return pd.concat([h - l,
                      (h - pc).abs(),
                      (l - pc).abs()], axis=1).max(axis=1)

def atr_series(h, l, c, n=14):
    tr = true_range(h, l, c.shift(1))
    return tr.ewm(alpha=1/n, adjust=False).mean()

def adx_series(h, l, c, n=14):
    up   = h.diff()
    dn   = -l.diff()
    pdm  = up.where((up > dn) & (up > 0), 0.0)
    ndm  = dn.where((dn > up) & (dn > 0), 0.0)
    tr14 = atr_series(h, l, c, n)
    pdi  = 100 * pdm.ewm(alpha=1/n, adjust=False).mean() / tr14.replace(0, np.nan)
    ndi  = 100 * ndm.ewm(alpha=1/n, adjust=False).mean() / tr14.replace(0, np.nan)
    dx   = (100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan))
    adx_ = dx.ewm(alpha=1/n, adjust=False).mean()
    return adx_

df["EMA_F"]  = ema(df["Close"], EMA_FAST_LEN)
df["EMA_M"]  = ema(df["Close"], EMA_MID_LEN)
df["EMA_S"]  = ema(df["Close"], EMA_SLOW_LEN)
df["ATR"]    = atr_series(df["High"], df["Low"], df["Close"], ATR_LEN)
df["ATR_BL"] = df["ATR"].rolling(ATR_BL_LEN).mean()
df["ADX"]    = adx_series(df["High"], df["Low"], df["Close"], ADX_LEN)
df["RSI"]    = rsi(df["Close"], RSI_LEN)
df["VOL_MA"] = df["Volume"].rolling(VOL_MA_LEN).mean()

# Body size in ATR units
df["BODY"] = (df["Close"] - df["Open"]).abs() / df["ATR"].replace(0, np.nan)
# EMA slope (3-bar)
df["EMA_F_SLOPE"] = df["EMA_F"] - df["EMA_F"].shift(3)
# Pullback conditions (use previous bar's low/high vs previous bar's EMA_F)
pb_tol_up = df["EMA_F"].shift(1) * (1.0 + PB_PCT / 100.0)
pb_tol_dn = df["EMA_F"].shift(1) * (1.0 - PB_PCT / 100.0)

long_pb  = (df["Low"].shift(1) <= pb_tol_up) & (df["Close"] > df["EMA_F"]) & \
           (df["Close"] > df["Open"]) & (df["BODY"] >= MIN_BODY)
short_pb = (df["High"].shift(1) >= pb_tol_dn) & (df["Close"] < df["EMA_F"]) & \
           (df["Close"] < df["Open"]) & (df["BODY"] >= MIN_BODY)

is_trending = df["ADX"] > ADX_THRESH
is_panic    = df["ATR"] > df["ATR_BL"] * PANIC_MULT

long_entry = (
    TRADE_LONGS &
    long_pb &
    (df["Close"] > df["EMA_S"]) &
    (df["EMA_F"] > df["EMA_M"]) &
    (~USE_EMA_SLOPE | (df["EMA_F_SLOPE"] > 0)) &
    (df["RSI"] >= RSI_LO_L) & (df["RSI"] <= RSI_HI_L) &
    (df["Volume"] >= df["VOL_MA"] * VOL_MULT) &
    is_trending & ~is_panic
)
short_entry = (
    TRADE_SHORTS &
    short_pb &
    (df["Close"] < df["EMA_S"]) &
    (df["EMA_F"] < df["EMA_M"]) &
    (~USE_EMA_SLOPE | (df["EMA_F_SLOPE"] < 0)) &
    (df["RSI"] >= RSI_LO_S) & (df["RSI"] <= RSI_HI_S) &
    (df["Volume"] >= df["VOL_MA"] * VOL_MULT) &
    is_trending & ~is_panic
)

# ── Bar-by-bar simulation ───────────────────────────────────────────────────────
equity     = INIT_CAP
in_trade   = False
direction  = None   # "long" | "short"
entry_px   = 0.0
sl_price   = 0.0
tp_price   = 0.0
best_price = 0.0
entry_atr  = 0.0

trades = []
equity_curve = [equity]

l_entry  = long_entry.values
s_entry  = short_entry.values
o        = df["Open"].values
h        = df["High"].values
l_       = df["Low"].values
c        = df["Close"].values
atr_v    = df["ATR"].values
idx      = df.index

COMM = COMMISSION

for i in range(EMA_SLOW_LEN + 50, len(df)):
    curr_atr = atr_v[i]
    if np.isnan(curr_atr) or curr_atr == 0:
        equity_curve.append(equity)
        continue

    # Apply ATR floor (0 in baseline — no effect)
    eff_atr = max(curr_atr, c[i] * ATR_FLOOR)

    exited = False

    if in_trade:
        # Update best price
        if direction == "long":
            if h[i] > best_price:
                best_price = h[i]
            # Activate trailing stop
            if best_price >= entry_px + entry_atr * TRAIL_ACT:
                trail_sl = best_price - entry_atr * TRAIL_DIST
                if trail_sl > sl_price:
                    sl_price = trail_sl

            # Check SL (low touches or crosses sl_price)
            if l_[i] <= sl_price:
                exit_px  = min(o[i], sl_price)   # gap-down fills at open
                pnl      = (exit_px - entry_px) * qty
                comm     = (entry_px + exit_px) * qty * COMM
                equity  += pnl - comm
                trades.append({"entry_time": entry_time, "exit_time": idx[i],
                                "direction": "long", "entry": entry_px,
                                "exit": exit_px, "pnl": pnl - comm, "equity": equity,
                                "exit_reason": "SL"})
                in_trade = False; exited = True

            elif not exited and h[i] >= tp_price:
                exit_px  = max(o[i], tp_price)
                pnl      = (exit_px - entry_px) * qty
                comm     = (entry_px + exit_px) * qty * COMM
                equity  += pnl - comm
                trades.append({"entry_time": entry_time, "exit_time": idx[i],
                                "direction": "long", "entry": entry_px,
                                "exit": exit_px, "pnl": pnl - comm, "equity": equity,
                                "exit_reason": "TP"})
                in_trade = False; exited = True

        else:  # short
            if l_[i] < best_price:
                best_price = l_[i]
            if best_price <= entry_px - entry_atr * TRAIL_ACT:
                trail_sl = best_price + entry_atr * TRAIL_DIST
                if trail_sl < sl_price:
                    sl_price = trail_sl

            if h[i] >= sl_price:
                exit_px  = max(o[i], sl_price)
                pnl      = (entry_px - exit_px) * qty
                comm     = (entry_px + exit_px) * qty * COMM
                equity  += pnl - comm
                trades.append({"entry_time": entry_time, "exit_time": idx[i],
                                "direction": "short", "entry": entry_px,
                                "exit": exit_px, "pnl": pnl - comm, "equity": equity,
                                "exit_reason": "SL"})
                in_trade = False; exited = True

            elif not exited and l_[i] <= tp_price:
                exit_px  = min(o[i], tp_price)
                pnl      = (entry_px - exit_px) * qty
                comm     = (entry_px + exit_px) * qty * COMM
                equity  += pnl - comm
                trades.append({"entry_time": entry_time, "exit_time": idx[i],
                                "direction": "short", "entry": entry_px,
                                "exit": exit_px, "pnl": pnl - comm, "equity": equity,
                                "exit_reason": "TP"})
                in_trade = False; exited = True

    if not in_trade:
        if l_entry[i]:
            stop_dist  = eff_atr * SL_MULT
            entry_px   = c[i]
            sl_price   = entry_px - stop_dist
            tp_price   = entry_px + eff_atr * TP_MULT
            entry_atr  = eff_atr
            best_price = entry_px
            qty        = equity * RISK_PCT / stop_dist
            entry_time = idx[i]
            direction  = "long"; in_trade = True
        elif s_entry[i]:
            stop_dist  = eff_atr * SL_MULT
            entry_px   = c[i]
            sl_price   = entry_px + stop_dist
            tp_price   = entry_px - eff_atr * TP_MULT
            entry_atr  = eff_atr
            best_price = entry_px
            qty        = equity * RISK_PCT / stop_dist
            entry_time = idx[i]
            direction  = "short"; in_trade = True

    equity_curve.append(equity)

# ── Results ────────────────────────────────────────────────────────────────────
tdf = pd.DataFrame(trades)
print(f"\n{'='*55}")
print(f"  APM v3.1 (sweep-optimised)  |  {TICKER} {INTERVAL}  |  Longs Only")
print(f"{'='*55}")

if tdf.empty:
    print("  No trades generated.")
else:
    wins    = tdf[tdf["pnl"] > 0]
    losses  = tdf[tdf["pnl"] <= 0]
    total   = len(tdf)
    wr      = len(wins) / total * 100
    net_pnl = tdf["pnl"].sum()
    net_pct = net_pnl / INIT_CAP * 100
    gp      = wins["pnl"].sum()
    gl      = abs(losses["pnl"].sum())
    pf      = gp / gl if gl > 0 else float("inf")
    avg_w   = wins["pnl"].mean() if not wins.empty else 0
    avg_l   = losses["pnl"].mean() if not losses.empty else 0

    eq_arr  = np.array(equity_curve)
    roll_max = np.maximum.accumulate(eq_arr)
    dd       = (eq_arr - roll_max) / roll_max * 100
    max_dd   = dd.min()

    longs_df  = tdf[tdf["direction"] == "long"]
    shorts_df = tdf[tdf["direction"] == "short"]

    print(f"  Period   : {df.index[0].date()} → {df.index[-1].date()}")
    print(f"  Trades   : {total}  (L={len(longs_df)}, S={len(shorts_df)})")
    print(f"  Win rate : {wr:.1f}%  ({len(wins)}W / {len(losses)}L)")
    print(f"  Net P&L  : ${net_pnl:+.2f}  ({net_pct:+.2f}%)")
    print(f"  Prof Fac : {pf:.3f}")
    print(f"  Avg Win  : ${avg_w:+.2f}   Avg Loss: ${avg_l:+.2f}")
    print(f"  Max DD   : {max_dd:.2f}%")
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

    tdf.to_csv("apm_v3_trades_btcusd_1h.csv", index=False)
    print(f"\n  Saved → apm_v3_trades_btcusd_1h.csv")

print(f"{'='*55}")
