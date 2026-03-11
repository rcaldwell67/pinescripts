# ─────────────────────────────────────────────────────────────────────────────
# APM v2.2  CLM 30m  —  parameter sweep
# Sweeps ADX_THRESH × VOL_MULT × TP_MULT × SL_MULT
# Fixed: PB_PCT=0.30, MIN_BODY=0.15, ATR_FLOOR=0.10%, PANIC_MULT=1.5
#        DI_SPREAD_MIN=3.0, ADX_SLOPE_BARS=1, MOMENTUM_BARS=5
#        RSI_LO_S=30, RSI_HI_S=62, TRADE_LONGS=False, TRADE_SHORTS=True
# ─────────────────────────────────────────────────────────────────────────────
import subprocess, sys
for pkg in ["yfinance", "pandas", "numpy"]:
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])

import yfinance as yf
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings("ignore")

TICKER   = "CLM"
PERIOD   = "60d"
INTERVAL = "30m"

EMA_FAST   = 21;  EMA_MID   = 50;  EMA_SLOW  = 200
ADX_LEN    = 14;  RSI_LEN   = 14;  ATR_LEN   = 14
VOL_LEN    = 20;  ATR_BL_LEN= 60

INITIAL_CAPITAL = 10_000.0
COMMISSION_PCT  = 0.0006
RISK_PCT        = 0.01

# Fixed
PB_PCT         = 0.30
MIN_BODY       = 0.15
ATR_FLOOR      = 0.0010
PANIC_MULT     = 1.5
RSI_LO_S       = 30;   RSI_HI_S      = 62
DI_SPREAD_MIN  = 3.0
ADX_SLOPE_BARS = 1
MOMENTUM_BARS  = 5
CONSEC_LOSS_LIMIT    = 2
CONSEC_LOSS_COOLDOWN = 1

# ── Sweep grid ─────────────────────────────────────────────────────────────
ADX_RANGE  = [12, 14, 16, 18]
VOL_RANGE  = [0.5, 0.6, 0.7, 0.8, 0.9]
TP_RANGE   = [2.0, 2.5, 3.0, 3.5]
SL_RANGE   = [1.5, 2.0]
TRAIL_ACT  = 99.0   # effectively disabled (hard TP only); simplifies sweep
TRAIL_DIST = 1.5

total = len(ADX_RANGE) * len(VOL_RANGE) * len(TP_RANGE) * len(SL_RANGE)
print(f"Combinations: {total}")

# ── Download once ────────────────────────────────────────────────────────────
print(f"Downloading {TICKER} {INTERVAL} period='{PERIOD}'...")
raw = yf.download(TICKER, period=PERIOD, interval=INTERVAL,
                  auto_adjust=True, progress=False)
if raw.empty:
    raise SystemExit("No data.")
if isinstance(raw.columns, pd.MultiIndex):
    raw.columns = raw.columns.droplevel(1)
raw = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
raw = raw[raw["Volume"] > 0]
raw.dropna(inplace=True)
print(f"Rows: {len(raw)}  {raw.index[0]} → {raw.index[-1]}")

# ── Compute indicators once ──────────────────────────────────────────────────
df = raw.copy()
df["EMA_FAST"] = df["Close"].ewm(span=EMA_FAST, adjust=False).mean()
df["EMA_MID"]  = df["Close"].ewm(span=EMA_MID,  adjust=False).mean()
df["EMA_SLOW"] = df["Close"].ewm(span=EMA_SLOW, adjust=False).mean()

δ      = df["Close"].diff()
avg_g  = δ.clip(lower=0).ewm(alpha=1/RSI_LEN, adjust=False).mean()
avg_l  = (-δ).clip(lower=0).ewm(alpha=1/RSI_LEN, adjust=False).mean()
df["RSI"] = 100 - (100 / (1 + avg_g / avg_l.replace(0, 1e-10)))

hl  = df["High"] - df["Low"]
hpc = (df["High"] - df["Close"].shift(1)).abs()
lpc = (df["Low"]  - df["Close"].shift(1)).abs()
tr  = pd.concat([hl, hpc, lpc], axis=1).max(axis=1)
df["ATR"]    = tr.ewm(alpha=1/ATR_LEN, adjust=False).mean()
df["ATR_BL"] = df["ATR"].rolling(ATR_BL_LEN).mean()

df["VOL_MA"] = df["Volume"].rolling(VOL_LEN).mean()

up_m  = df["High"] - df["High"].shift(1)
dn_m  = df["Low"].shift(1) - df["Low"]
pdm   = pd.Series(np.where((up_m > dn_m) & (up_m > 0), up_m, 0.0), index=df.index)
mdm   = pd.Series(np.where((dn_m > up_m) & (dn_m > 0), dn_m, 0.0), index=df.index)
sp    = pdm.ewm(alpha=1/ADX_LEN, adjust=False).mean()
sm    = mdm.ewm(alpha=1/ADX_LEN, adjust=False).mean()
df["DI_PLUS"]  = 100 * sp / df["ATR"]
df["DI_MINUS"] = 100 * sm / df["ATR"]
dx = 100 * (df["DI_PLUS"] - df["DI_MINUS"]).abs() / (
    (df["DI_PLUS"] + df["DI_MINUS"]).replace(0, 1e-10))
df["ADX"] = dx.ewm(alpha=1/ADX_LEN, adjust=False).mean()
df.dropna(inplace=True)

tol       = PB_PCT / 100.0
body_size = (df["Close"] - df["Open"]).abs() / df["ATR"]

# ── Static signal components (param-independent) ─────────────────────────────
ema_bear       = (df["EMA_FAST"] < df["EMA_MID"]) & (df["EMA_MID"] < df["EMA_SLOW"])
ema_slope_down = df["EMA_FAST"] < df["EMA_FAST"].shift(3)
rsi_falling    = df["RSI"] < df["RSI"].shift(1)
rsi_short_ok   = (df["RSI"] >= RSI_LO_S) & (df["RSI"] <= RSI_HI_S)
atr_floor_ok   = df["ATR"] / df["Close"] >= ATR_FLOOR
di_spread_ok_s = (df["DI_MINUS"] - df["DI_PLUS"]) >= DI_SPREAD_MIN
adx_rising     = df["ADX"] > df["ADX"].shift(ADX_SLOPE_BARS)
momentum_ok_s  = df["Close"] < df["Close"].shift(MOMENTUM_BARS)

pb_tol_dn  = df["EMA_FAST"].shift(1) * (1.0 - tol)
short_pb   = ((df["High"].shift(1) >= pb_tol_dn) &
              (df["Close"] < df["EMA_FAST"])       &
              (df["Close"] < df["Open"])             &
              (body_size >= MIN_BODY))

bar_idx = {t: i for i, t in enumerate(df.index)}

# ── Simulation function ───────────────────────────────────────────────────────
def run(adx_thresh, vol_mult, tp_mult, sl_mult):
    is_panic   = df["ATR"] > df["ATR_BL"] * PANIC_MULT
    is_trend   = df["ADX"] > adx_thresh
    vol_ok     = df["Volume"] >= df["VOL_MA"] * vol_mult

    sig = (short_pb & ema_bear & ema_slope_down & rsi_falling & rsi_short_ok &
           vol_ok & atr_floor_ok & is_trend & adx_rising & di_spread_ok_s &
           momentum_ok_s & ~is_panic)

    equity = INITIAL_CAPITAL
    pos    = None
    trades = []
    consec = 0
    cool   = 0

    for ts, row in df.iterrows():
        close = float(row["Close"]); high = float(row["High"])
        low   = float(row["Low"]);   atr  = float(row["ATR"])
        sd    = atr * sl_mult

        htp = hsl = False
        if pos is not None:
            if low  < pos["best"]: pos["best"] = low
            if pos["best"] <= pos["tap"]:
                pos["sl"] = min(pos["sl"], pos["best"] + pos["td"])
            htp = low  <= pos["tp"]
            hsl = high >= pos["sl"]

        if htp or hsl:
            xp  = pos["tp"] if htp else pos["sl"]
            pnl = (pos["entry"] - xp) / pos["entry"]
            dp  = pnl * pos["notl"] - pos["notl"] * COMMISSION_PCT * 2
            equity += dp
            trades.append(dp)
            consec = 0 if dp > 0 else consec + 1
            if consec >= CONSEC_LOSS_LIMIT:
                cool   = CONSEC_LOSS_COOLDOWN
                consec = 0
            pos = None

        if pos is None:
            if cool > 0:
                cool -= 1
            elif bool(sig[ts]):
                notl = min(equity * RISK_PCT / sd * close, equity * 5.0)
                pos  = {
                    "entry":  close,
                    "sl":     close + sd,
                    "tp":     close - atr * tp_mult,
                    "best":   close,
                    "notl":   notl,
                    "tap":    close - atr * TRAIL_ACT,
                    "td":     atr * TRAIL_DIST,
                }

    if not trades:
        return None
    wins  = [p for p in trades if p > 0]
    losss = [p for p in trades if p <= 0]
    gp    = sum(wins)   if wins  else 0.0
    gl    = sum(losss)  if losss else 0.0
    pf    = gp / abs(gl) if gl != 0 else float("inf")
    wr    = len(wins) / len(trades) * 100
    ret   = (equity / INITIAL_CAPITAL - 1) * 100
    return {
        "adx": adx_thresh, "vol": vol_mult, "tp": tp_mult, "sl": sl_mult,
        "n": len(trades), "wr": round(wr, 1), "pf": round(pf, 3),
        "ret": round(ret, 2), "sig": int(sig.sum()),
    }

# ── Run sweep ─────────────────────────────────────────────────────────────────
results = []
done    = 0
for adx in ADX_RANGE:
    for vol in VOL_RANGE:
        for tp in TP_RANGE:
            for sl in SL_RANGE:
                r = run(adx, vol, tp, sl)
                if r:
                    results.append(r)
                done += 1

rdf = pd.DataFrame(results)
rdf.sort_values("pf", ascending=False, inplace=True)

print(f"\nCompleted {done} combos, {len(rdf)} with trades.\n")
print("─" * 78)
print(f"{'ADX':>4} {'VOL':>5} {'TP':>5} {'SL':>5} {'Sigs':>5} "
      f"{'N':>4} {'WR%':>6} {'PF':>8} {'Ret%':>8}")
print("─" * 78)
for _, row in rdf.head(20).iterrows():
    print(f"{row['adx']:>4.0f} {row['vol']:>5.2f} {row['tp']:>5.1f} {row['sl']:>5.1f} "
          f"{row['sig']:>5} {row['n']:>4.0f} {row['wr']:>6.1f} "
          f"{row['pf']:>8.3f} {row['ret']:>7.2f}%")
print("─" * 78)

out_csv = "sweep_apm_v2_clm_30m.csv"
rdf.to_csv(out_csv, index=False)
print(f"\nFull results → {out_csv}")

# ── Summary: best by each metric ──────────────────────────────────────────────
print("\n── Best PF (min 3 trades): ")
sub = rdf[rdf["n"] >= 3]
if not sub.empty:
    r = sub.iloc[0]
    print(f"   ADX={r['adx']:.0f} VOL={r['vol']:.2f} TP={r['tp']:.1f} SL={r['sl']:.1f} "
          f"→ n={r['n']:.0f} WR={r['wr']:.1f}% PF={r['pf']:.3f} Ret={r['ret']:.2f}%")

print("── Best Return (min 3 trades):")
sub2 = rdf[rdf["n"] >= 3].sort_values("ret", ascending=False)
if not sub2.empty:
    r = sub2.iloc[0]
    print(f"   ADX={r['adx']:.0f} VOL={r['vol']:.2f} TP={r['tp']:.1f} SL={r['sl']:.1f} "
          f"→ n={r['n']:.0f} WR={r['wr']:.1f}% PF={r['pf']:.3f} Ret={r['ret']:.2f}%")

print("── Balanced (PF≥1.5 + Ret≥2.5 + n≥4):")
sub3 = rdf[(rdf["pf"] >= 1.5) & (rdf["ret"] >= 2.5) & (rdf["n"] >= 4)]
if not sub3.empty:
    sub3 = sub3.sort_values(["pf", "ret"], ascending=False)
    r = sub3.iloc[0]
    print(f"   ADX={r['adx']:.0f} VOL={r['vol']:.2f} TP={r['tp']:.1f} SL={r['sl']:.1f} "
          f"→ n={r['n']:.0f} WR={r['wr']:.1f}% PF={r['pf']:.3f} Ret={r['ret']:.2f}%")
else:
    print("   No combo met all 3 criteria — relaxing to n≥3:")
    sub3b = rdf[(rdf["pf"] >= 1.5) & (rdf["ret"] >= 2.0) & (rdf["n"] >= 3)]
    if not sub3b.empty:
        sub3b = sub3b.sort_values(["pf", "ret"], ascending=False)
        r = sub3b.iloc[0]
        print(f"   ADX={r['adx']:.0f} VOL={r['vol']:.2f} TP={r['tp']:.1f} SL={r['sl']:.1f} "
              f"→ n={r['n']:.0f} WR={r['wr']:.1f}% PF={r['pf']:.3f} Ret={r['ret']:.2f}%")
    else:
        print("   None found.")
