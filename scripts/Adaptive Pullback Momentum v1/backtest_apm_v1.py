# APM v1.3  —  BTC-USD 15m  (shorts only, sweep-optimised params)
# Timeframe: 15m  |  Ticker: BTC-USD  |  Period: max

import subprocess, sys
for pkg in ["yfinance", "pandas", "numpy"]:
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])

import yfinance as yf
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings("ignore")

# ── Config (Pine Script defaults) ─────────────────────────────────────────────
TICKER      = "BTC-USD"
PERIOD      = "max"
INTERVAL    = "15m"
INITIAL_CAP = 10_000.0
COMM        = 0.0006      # 0.06% per side
RISK_PCT    = 0.01        # 1% equity per trade

EMA_FAST    = 21
EMA_MID     = 50
EMA_SLOW    = 200
ADX_THRESH  = 28          # v1.3: raised from 25 — higher trend quality, WR 60%→70%
ADX_LEN     = 14
PB_PCT      = 0.15        # %
RSI_LEN     = 14
RSI_LO_L    = 42;  RSI_HI_L = 68
RSI_LO_S    = 32;  RSI_HI_S = 58
VOL_LEN     = 20
VOL_MULT    = 1.2
ATR_LEN     = 14
ATR_FLOOR   = 0.0015      # v1.3: 0.15% (was 0.20% — too aggressive for 15m shorts)
PANIC_MULT  = 1.3
MIN_BODY    = 0.20        # fraction of ATR
SL_MULT     = 2.0
TP_MULT     = 2.5          # v1.3: 2.5× (was 3.5× — TP hit only 5/30 times at 15m)
TRAIL_ACT   = 2.5
TRAIL_DIST  = 0.6          # v1.3: 0.6× (was 1.5× — tighter lock-in on 15m)
TRADE_LONGS = False        # v1.3: longs disabled — WR=23% PF=0.189 at 15m

# ── Download ──────────────────────────────────────────────────────────────────
print(f"Downloading {TICKER} {INTERVAL} period='{PERIOD}'...")
df = yf.download(TICKER, period=PERIOD, interval=INTERVAL,
                 auto_adjust=True, progress=False)
df.columns = df.columns.get_level_values(0)
df.index   = pd.to_datetime(df.index, utc=True)
df.sort_index(inplace=True)
print(f"Rows: {len(df)}  Range: {df.index[0]} → {df.index[-1]}\n")

# ── Indicators ────────────────────────────────────────────────────────────────
def ema(s, n):  return s.ewm(span=n, adjust=False).mean()
def sma(s, n):  return s.rolling(n).mean()

def rsi_calc(s, n):
    d  = s.diff()
    g  = d.clip(lower=0).rolling(n).mean()
    ls = (-d).clip(lower=0).rolling(n).mean()
    return 100 - 100 / (1 + g / ls.replace(0, np.nan))

def atr_calc(df, n):
    h, l, c = df["High"], df["Low"], df["Close"]
    tr = pd.concat([h - l,
                    (h - c.shift()).abs(),
                    (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def adx_calc(df, n):
    h, l, c = df["High"], df["Low"], df["Close"]
    up = h.diff(); dn = -l.diff()
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr  = pd.concat([h - l,
                     (h - c.shift()).abs(),
                     (l - c.shift()).abs()], axis=1).max(axis=1)
    at  = tr.rolling(n).mean()
    pdi = pd.Series(pdm, index=h.index).rolling(n).mean() / at * 100
    ndi = pd.Series(ndm, index=h.index).rolling(n).mean() / at * 100
    dx  = ((pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan) * 100)
    return pdi, ndi, dx.rolling(n).mean()

df["EMA_FAST"] = ema(df["Close"], EMA_FAST)
df["EMA_MID"]  = ema(df["Close"], EMA_MID)
df["EMA_SLOW"] = ema(df["Close"], EMA_SLOW)
df["RSI"]      = rsi_calc(df["Close"], RSI_LEN)
df["ATR"]      = atr_calc(df, ATR_LEN)
df["ATR_BL"]   = sma(df["ATR"], 60)
df["VOL_MA"]   = sma(df["Volume"], VOL_LEN)
df["DI_PLUS"], df["DI_MINUS"], df["ADX"] = adx_calc(df, ADX_LEN)
df.dropna(inplace=True)

# ── Signals (v1.2 — full v2 filter set) ─────────────────────────────────────────
full_bull   = (df["EMA_FAST"] > df["EMA_MID"]) & (df["EMA_MID"] > df["EMA_SLOW"])
full_bear   = (df["EMA_FAST"] < df["EMA_MID"]) & (df["EMA_MID"] < df["EMA_SLOW"])
slope_up    = df["EMA_FAST"] > df["EMA_FAST"].shift(3)
slope_down  = df["EMA_FAST"] < df["EMA_FAST"].shift(3)
rsi_rising  = df["RSI"] > df["RSI"].shift(1)
rsi_falling = df["RSI"] < df["RSI"].shift(1)
atr_ok      = df["ATR"] / df["Close"] >= ATR_FLOOR
pb_tol_up  = df["EMA_FAST"].shift(1) * (1.0 + PB_PCT / 100.0)
pb_tol_dn  = df["EMA_FAST"].shift(1) * (1.0 - PB_PCT / 100.0)
body_size  = (df["Close"] - df["Open"]).abs() / df["ATR"]

long_pb  = (df["Low"].shift(1)  <= pb_tol_up) & \
           (df["Close"] > df["EMA_FAST"]) & \
           (df["Close"] > df["Open"]) & \
           (body_size >= MIN_BODY)

short_pb = (df["High"].shift(1) >= pb_tol_dn) & \
           (df["Close"] < df["EMA_FAST"]) & \
           (df["Close"] < df["Open"]) & \
           (body_size >= MIN_BODY)

is_trending = df["ADX"]  > ADX_THRESH
is_panic    = df["ATR"]  > df["ATR_BL"] * PANIC_MULT
vol_ok      = df["Volume"] >= df["VOL_MA"] * VOL_MULT
rsi_long_ok = (df["RSI"] >= RSI_LO_L) & (df["RSI"] <= RSI_HI_L)
rsi_short_ok= (df["RSI"] >= RSI_LO_S) & (df["RSI"] <= RSI_HI_S)

long_sig  = (pd.Series(False, index=df.index) if not TRADE_LONGS else
             (~is_panic & is_trending & long_pb & full_bull & slope_up &
              rsi_rising & rsi_long_ok & vol_ok & atr_ok))
short_sig = (~is_panic & is_trending & short_pb & full_bear  & slope_down &
             rsi_falling & rsi_short_ok & vol_ok & atr_ok)

# ── Simulation ────────────────────────────────────────────────────────────────
equity = INITIAL_CAP
pos    = None
trades = []

for ts, row in df.iterrows():
    cl = float(row["Close"]); hi = float(row["High"])
    lo = float(row["Low"]);   av = float(row["ATR"])

    hit_tp = hit_sl = False
    exit_price = pnl = 0.0

    if pos is not None:
        d = pos["direction"]
        if d == "long":
            if hi > pos["best"]: pos["best"] = hi
            if pos["best"] >= pos["entry"] + av * TRAIL_ACT:
                trail_sl = pos["best"] - av * TRAIL_DIST
                pos["sl"] = max(pos["sl"], trail_sl)
            hit_tp = hi >= pos["tp"]
            hit_sl = lo <= pos["sl"]
        else:
            if lo < pos["best"]: pos["best"] = lo
            if pos["best"] <= pos["entry"] - av * TRAIL_ACT:
                trail_sl = pos["best"] + av * TRAIL_DIST
                pos["sl"] = min(pos["sl"], trail_sl)
            hit_tp = lo <= pos["tp"]
            hit_sl = hi >= pos["sl"]

        if hit_tp or hit_sl:
            exit_price = pos["tp"] if hit_tp else pos["sl"]
            if d == "long":
                pnl = (exit_price - pos["entry"]) / pos["entry"]
            else:
                pnl = (pos["entry"] - exit_price) / pos["entry"]

    if hit_tp or hit_sl:
        dollar_pnl = pnl * pos["notional"] - pos["notional"] * COMM * 2
        equity += dollar_pnl
        trades.append({
            "entry_time":  pos["entry_time"],
            "exit_time":   ts,
            "direction":   pos["direction"],
            "entry_price": round(pos["entry"], 2),
            "exit_price":  round(exit_price, 2),
            "result":      "TP" if hit_tp else "SL",
            "pnl_pct":     round(pnl * 100, 3),
            "dollar_pnl":  round(dollar_pnl, 2),
            "equity":      round(equity, 2),
        })
        pos = None

    if pos is None:
        sig = ("long" if bool(long_sig[ts]) else
               "short" if bool(short_sig[ts]) else None)
        if sig:
            sd       = av * SL_MULT
            notional = min(equity * RISK_PCT / sd * cl, equity * 5.0)
            sl       = cl - sd if sig == "long" else cl + sd
            tp       = cl + av * TP_MULT if sig == "long" else cl - av * TP_MULT
            pos = {
                "direction":  sig,
                "entry":      cl,
                "entry_time": ts,
                "sl":         sl,
                "tp":         tp,
                "best":       cl,
                "notional":   notional,
            }

# ── Stats ─────────────────────────────────────────────────────────────────────
tdf = pd.DataFrame(trades)
if tdf.empty:
    print("No trades generated.")
else:
    wins   = tdf[tdf["dollar_pnl"] > 0]
    losses = tdf[tdf["dollar_pnl"] <= 0]
    wr     = len(wins) / len(tdf) * 100
    ret    = (equity / INITIAL_CAP - 1) * 100
    pf     = (wins["dollar_pnl"].sum() / abs(losses["dollar_pnl"].sum())
              if not losses.empty and losses["dollar_pnl"].sum() != 0 else float("inf"))

    pk = INITIAL_CAP; mdd = 0.0
    for e in tdf["equity"]:
        if e > pk: pk = e
        dd = (e - pk) / pk * 100
        if dd < mdd: mdd = dd

    print("=" * 55)
    print(f"  APM v1.3  |  {TICKER} {INTERVAL}  (shorts only)")
    print("=" * 55)
    print(f"  Initial capital :  ${INITIAL_CAP:>10,.2f}")
    print(f"  Final equity    :  ${equity:>10,.2f}")
    print(f"  Net P&L         : ${equity-INITIAL_CAP:>+10,.2f}")
    print(f"  Return          :  {ret:>10.2f} %")
    print(f"  Max drawdown    :  {mdd:>10.2f} %")
    print(f"  Profit factor   :  {pf:>10.3f}")
    print("-" * 55)
    print(f"  Total trades    : {len(tdf):>6}")
    print(f"    Long  trades  : {(tdf['direction']=='long').sum():>6}")
    print(f"    Short trades  : {(tdf['direction']=='short').sum():>6}")
    print(f"  TP exits        : {(tdf['result']=='TP').sum():>6}")
    print(f"  SL exits        : {(tdf['result']=='SL').sum():>6}")
    print(f"  Win rate        :  {wr:>10.1f} %")
    print("=" * 55)
    for d in ["long", "short"]:
        sub  = tdf[tdf["direction"] == d]
        if sub.empty: continue
        sw   = sub[sub["dollar_pnl"] > 0]
        sl   = sub[sub["dollar_pnl"] <= 0]
        swr  = len(sw) / len(sub) * 100
        spf  = (sw["dollar_pnl"].sum() / abs(sl["dollar_pnl"].sum())
                if not sl.empty and sl["dollar_pnl"].sum() != 0 else float("inf"))
        print(f"  {d.upper():<6} trades={len(sub):>3}  WR={swr:.0f}%  "
              f"PF={spf:.3f}  net=${sub['dollar_pnl'].sum():+.2f}")

    out = f"apm_v1_trades_{TICKER.replace('-','').lower()}_{INTERVAL}.csv"
    tdf.to_csv(out, index=False)
    print(f"\nTrades saved → {out}")
