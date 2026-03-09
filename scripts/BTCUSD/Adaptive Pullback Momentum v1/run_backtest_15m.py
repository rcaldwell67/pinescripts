# Runner for APM backtest at 15m (non-notebook)
import subprocess, sys
# ensure deps
for pkg in ["yfinance", "pandas", "numpy", "matplotlib"]:
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])

import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import warnings
warnings.filterwarnings("ignore")

# Configuration (15m)
TICKER   = "BTC-USD"
PERIOD   = "max"  # request maximum available history (note: Yahoo may limit intraday to ~60 days)
INTERVAL = "15m"

EMA_FAST    = 21
EMA_MID     = 50
EMA_SLOW    = 200
ADX_THRESH  = 20
ADX_LEN     = 14
PB_PCT      = 0.30

RSI_LEN     = 14
RSI_LO_L    = 42;  RSI_HI_L = 68
RSI_LO_S    = 32;  RSI_HI_S = 58
VOL_LEN     = 20
VOL_MULT    = 1.0

ATR_LEN     = 14
PANIC_MULT  = 1.5

SL_MULT     = 1.5
TP_MULT     = 2.5
TRAIL_ACT   = 1.0
TRAIL_DIST  = 0.8
RISK_PCT    = 0.01

INITIAL_CAPITAL = 10_000.0
COMMISSION_PCT  = 0.0006
TRADE_LONGS  = True
TRADE_SHORTS = True

print(f"Running APM backtest: {TICKER} {INTERVAL} | {PERIOD}")

# Download data
df = yf.download(TICKER, period=PERIOD, interval=INTERVAL, auto_adjust=True, progress=False)
if df.empty:
    raise SystemExit(f"No data returned for {TICKER} {INTERVAL} with period={PERIOD}")
if isinstance(df.index, pd.DatetimeIndex):
    print(f"Downloaded rows: {len(df)}  Range: {df.index[0]} → {df.index[-1]}")
else:
    print(f"Downloaded rows: {len(df)}")
if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.droplevel(1)
df = df[["Open","High","Low","Close","Volume"]].copy()
df.dropna(inplace=True)

# Indicators
df["EMA_FAST"] = df["Close"].ewm(span=EMA_FAST, adjust=False).mean()
df["EMA_MID"]  = df["Close"].ewm(span=EMA_MID,  adjust=False).mean()
df["EMA_SLOW"] = df["Close"].ewm(span=EMA_SLOW, adjust=False).mean()

delta  = df["Close"].diff()
gain   = delta.clip(lower=0)
loss   = (-delta).clip(lower=0)
avg_g  = gain.ewm(alpha=1/RSI_LEN, adjust=False).mean()
avg_l  = loss.ewm(alpha=1/RSI_LEN, adjust=False).mean()
df["RSI"] = 100 - (100 / (1 + avg_g / avg_l.replace(0, 1e-10)))

hl   = df["High"] - df["Low"]
hpc  = (df["High"] - df["Close"].shift(1)).abs()
lpc  = (df["Low"]  - df["Close"].shift(1)).abs()
tr   = pd.concat([hl, hpc, lpc], axis=1).max(axis=1)
df["ATR"]    = tr.ewm(alpha=1/ATR_LEN, adjust=False).mean()
df["ATR_BL"] = df["ATR"].rolling(60).mean()

df["VOL_MA"] = df["Volume"].rolling(VOL_LEN).mean()

up_move  = df["High"] - df["High"].shift(1)
dn_move  = df["Low"].shift(1) - df["Low"]
plus_dm  = np.where((up_move > dn_move) & (up_move > 0), up_move, 0.0)
minus_dm = np.where((dn_move > up_move) & (dn_move > 0), dn_move, 0.0)
s_plus   = pd.Series(plus_dm,  index=df.index).ewm(alpha=1/ADX_LEN, adjust=False).mean()
s_minus  = pd.Series(minus_dm, index=df.index).ewm(alpha=1/ADX_LEN, adjust=False).mean()
df["DI_PLUS"]  = 100 * s_plus  / df["ATR"]
df["DI_MINUS"] = 100 * s_minus / df["ATR"]
dx             = 100 * (df["DI_PLUS"] - df["DI_MINUS"]).abs() / (df["DI_PLUS"] + df["DI_MINUS"])
df["ADX"]      = dx.ewm(alpha=1/ADX_LEN, adjust=False).mean()

df.dropna(inplace=True)
df["IS_TRENDING"] = df["ADX"] > ADX_THRESH
df["IS_PANIC"]    = df["ATR"] > df["ATR_BL"] * PANIC_MULT

# Signals (v1.1 defaults later in script); initial v1.0 signals
tol = PB_PCT / 100.0
long_pb  = (
    (df["Low"].shift(1) <= df["EMA_FAST"].shift(1) * (1 + tol)) &
    (df["Close"] > df["EMA_FAST"]) &
    (df["Close"] > df["Open"])
)
short_pb = (
    (df["High"].shift(1) >= df["EMA_FAST"].shift(1) * (1 - tol)) &
    (df["Close"] < df["EMA_FAST"]) &
    (df["Close"] < df["Open"])
)

df["LongSignal"] = (
    long_pb &
    (df["Close"]    > df["EMA_SLOW"]) &
    (df["EMA_FAST"] > df["EMA_MID"]) &
    (df["RSI"] >= RSI_LO_L) & (df["RSI"] <= RSI_HI_L) &
    (df["Volume"] >= df["VOL_MA"] * VOL_MULT) &
    df["IS_TRENDING"] & ~df["IS_PANIC"]
) & TRADE_LONGS

df["ShortSignal"] = (
    short_pb &
    (df["Close"]    < df["EMA_SLOW"]) &
    (df["EMA_FAST"] < df["EMA_MID"]) &
    (df["RSI"] >= RSI_LO_S) & (df["RSI"] <= RSI_HI_S) &
    (df["Volume"] >= df["VOL_MA"] * VOL_MULT) &
    df["IS_TRENDING"] & ~df["IS_PANIC"]
) & TRADE_SHORTS

print(f"Signals — Long: {df['LongSignal'].sum()}  Short: {df['ShortSignal'].sum()}")

# Bar-by-bar backtest (v1.0 defaults)
equity       = INITIAL_CAPITAL
position     = None
trades       = []
equity_curve = []

for ts, row in df.iterrows():
    close = float(row["Close"])
    high  = float(row["High"])
    low   = float(row["Low"])
    atr   = float(row["ATR"])
    stop_dist = atr * SL_MULT

    hit_tp = hit_sl = False
    exit_px = None

    if position is not None:
        d = position["direction"]
        if d == "long":
            if high > position["best"]:
                position["best"] = high
            if position["best"] >= position["entry"] + atr * TRAIL_ACT:
                candidate = position["best"] - atr * TRAIL_DIST
                position["sl"] = max(position["sl"], candidate)
            hit_tp = high >= position["tp"]
            hit_sl = low  <= position["sl"]
            if hit_tp or hit_sl:
                exit_px = position["tp"] if hit_tp else position["sl"]
                pnl_pct = (exit_px - position["entry"]) / position["entry"]
        else:
            if low < position["best"]:
                position["best"] = low
            if position["best"] <= position["entry"] - atr * TRAIL_ACT:
                candidate = position["best"] + atr * TRAIL_DIST
                position["sl"] = min(position["sl"], candidate)
            hit_tp = low  <= position["tp"]
            hit_sl = high >= position["sl"]
            if hit_tp or hit_sl:
                exit_px = position["tp"] if hit_tp else position["sl"]
                pnl_pct = (position["entry"] - exit_px) / position["entry"]

        if hit_tp or hit_sl:
            dollar_pnl  = pnl_pct * position["notional"]
            commission  = position["notional"] * COMMISSION_PCT * 2
            dollar_pnl -= commission
            equity     += dollar_pnl
            trades.append({
                "entry_time" : position["entry_time"],
                "exit_time"  : ts,
                "direction"  : d,
                "entry"      : position["entry"],
                "exit"       : exit_px,
                "sl_initial" : position["sl_initial"],
                "tp"         : position["tp"],
                "result"     : "TP" if hit_tp else "SL",
                "pnl_pct"    : round(pnl_pct * 100, 3),
                "dollar_pnl" : round(dollar_pnl, 2),
                "equity"     : round(equity, 2),
            })
            position = None

    if position is None:
        sig = None
        if   bool(row["LongSignal"]):  sig = "long"
        elif bool(row["ShortSignal"]): sig = "short"

        if sig:
            risk_cap = equity * RISK_PCT
            qty      = risk_cap / stop_dist
            notional = qty * close
            sl = close - stop_dist if sig == "long" else close + stop_dist
            tp = close + atr * TP_MULT if sig == "long" else close - atr * TP_MULT
            position = {
                "direction"  : sig,
                "entry"      : close,
                "entry_time" : ts,
                "sl"         : sl,
                "sl_initial" : sl,
                "tp"         : tp,
                "best"       : close,
                "notional"   : notional,
            }

    equity_curve.append({"time": ts, "equity": equity})

print(f"Simulation complete. Trades: {len(trades)}")

# Save equity chart
if equity_curve:
    ec_df = pd.DataFrame(equity_curve).set_index("time")
    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(12,4))
    ax.plot(ec_df.index, ec_df["equity"], color="#68d391")
    ax.axhline(INITIAL_CAPITAL, color="white", ls=":")
    ax.set_title(f"APM v1.0 Equity — {TICKER} {INTERVAL}")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    plt.tight_layout()
    out_png = f"backtest_apm_{TICKER.replace('-','').lower()}_{INTERVAL}.png"
    plt.savefig(out_png, dpi=150, bbox_inches="tight")
    print(f"Chart saved → {out_png}")

# Print basic stats
if trades:
    tdf = pd.DataFrame(trades)
    wins = tdf[tdf["dollar_pnl"]>0]
    losses = tdf[tdf["dollar_pnl"]<=0]
    total = tdf["dollar_pnl"].sum()
    final = tdf["equity"].iloc[-1]
    print(f"Final equity: ${final:.2f}  Net P&L: ${total:+.2f}  Trades: {len(tdf)}")
else:
    print("No trades executed.")

print("Done.")

# ------------------------- v1.1 simulation (updated defaults) -------------------------
print("\nRunning APM v1.1 simulation on same data...")

# v1.1 params
V11_PB   = 0.15
V11_TP   = 2.0
V11_ADX  = 25
V11_TACT = 1.5
V11_TDIST= 0.8
V11_BODY = 0.15

tol11 = V11_PB / 100.0
body_v11 = (df["Close"] - df["Open"]).abs() / df["ATR"] >= V11_BODY

long_pb11 = (
    (df["Low"].shift(1) <= df["EMA_FAST"].shift(1) * (1 + tol11)) &
    (df["Close"] > df["EMA_FAST"]) &
    (df["Close"] > df["Open"]) & body_v11
)
short_pb11 = (
    (df["High"].shift(1) >= df["EMA_FAST"].shift(1) * (1 - tol11)) &
    (df["Close"] < df["EMA_FAST"]) &
    (df["Close"] < df["Open"]) & body_v11
)

long_sig11 = (
    long_pb11 &
    (df["Close"]    > df["EMA_SLOW"]) &
    (df["EMA_FAST"] > df["EMA_MID"]) &
    (df["RSI"] >= RSI_LO_L) & (df["RSI"] <= RSI_HI_L) &
    (df["Volume"] >= df["VOL_MA"] * VOL_MULT) &
    (df["ADX"] > V11_ADX) & ~df["IS_PANIC"]
) & TRADE_LONGS

short_sig11 = (
    short_pb11 &
    (df["Close"]    < df["EMA_SLOW"]) &
    (df["EMA_FAST"] < df["EMA_MID"]) &
    (df["RSI"] >= RSI_LO_S) & (df["RSI"] <= RSI_HI_S) &
    (df["Volume"] >= df["VOL_MA"] * VOL_MULT) &
    (df["ADX"] > V11_ADX) & ~df["IS_PANIC"]
) & TRADE_SHORTS

print(f"v1.1 Signals — Long: {long_sig11.sum()}  Short: {short_sig11.sum()}")

# run simulation
eq11 = INITIAL_CAPITAL
pos11 = None
trades11 = []
eqcurve11 = []

for ts, row in df.iterrows():
    close = float(row["Close"]) ; high = float(row["High"]) ; low = float(row["Low"]) ; atr = float(row["ATR"])
    sd = atr * SL_MULT

    if pos11 is not None:
        d = pos11["direction"]
        if d == "long":
            if high > pos11["best"]: pos11["best"] = high
            if pos11["best"] >= pos11["entry"] + atr * V11_TACT:
                pos11["sl"] = max(pos11["sl"], pos11["best"] - atr * V11_TDIST)
            htp = high >= pos11["tp"]; hsl = low <= pos11["sl"]
            if htp or hsl:
                xp = pos11["tp"] if htp else pos11["sl"]
                pnl = (xp - pos11["entry"]) / pos11["entry"]
        else:
            if low < pos11["best"]: pos11["best"] = low
            if pos11["best"] <= pos11["entry"] - atr * V11_TACT:
                pos11["sl"] = min(pos11["sl"], pos11["best"] + atr * V11_TDIST)
            htp = low <= pos11["tp"]; hsl = high >= pos11["sl"]
            if htp or hsl:
                xp = pos11["tp"] if htp else pos11["sl"]
                pnl = (pos11["entry"] - xp) / pos11["entry"]

        if (('htp' in locals() and htp) or ('hsl' in locals() and hsl)):
            dp = pnl * pos11["notional"] - pos11["notional"] * COMMISSION_PCT * 2
            eq11 += dp
            trades11.append({"entry_time": pos11.get("entry_time"), "exit_time": ts,
                             "direction": d, "entry": pos11["entry"], "exit": xp,
                             "result": "TP" if htp else "SL", "pnl_pct": round(pnl*100,3),
                             "dollar_pnl": round(dp,2), "equity": round(eq11,2)})
            pos11 = None

    if pos11 is None:
        sig11 = "long" if bool(long_sig11[ts]) else ("short" if bool(short_sig11[ts]) else None)
        if sig11:
            rc = eq11 * RISK_PCT; qty = rc / sd; notl = qty * close
            sl = close - sd if sig11 == "long" else close + sd
            tp = close + atr * V11_TP if sig11 == "long" else close - atr * V11_TP
            pos11 = {"direction": sig11, "entry": close, "entry_time": ts,
                     "sl": sl, "tp": tp, "best": close, "notional": notl}

    eqcurve11.append({"time": ts, "equity": eq11})

# results
t11df = pd.DataFrame(trades11)
print(f"v1.1 trades executed: {len(t11df)}")
if not t11df.empty:
    wins = t11df[t11df["dollar_pnl"]>0]
    losses = t11df[t11df["dollar_pnl"]<=0]
    final = t11df["equity"].iloc[-1]
    total = t11df["dollar_pnl"].sum()
    print(f"v1.1 Final equity: ${final:.2f}  Net P&L: ${total:+.2f}  Trades: {len(t11df)}")
    # save chart
    ec11 = pd.DataFrame(eqcurve11).set_index("time")
    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(12,4))
    ax.plot(ec11.index, ec11["equity"], color="#68d391")
    ax.axhline(INITIAL_CAPITAL, color="white", ls=":")
    ax.set_title(f"APM v1.1 Equity — {TICKER} {INTERVAL}")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    plt.tight_layout()
    out_png = f"backtest_apm_v11_{TICKER.replace('-','').lower()}_{INTERVAL}.png"
    plt.savefig(out_png, dpi=150, bbox_inches="tight")
    print(f"v1.1 Chart saved → {out_png}")
    # save trades
    out_csv = f"backtest_apm_v11_trades_{TICKER.replace('-','').lower()}_{INTERVAL}.csv"
    t11df.to_csv(out_csv, index=False)
    print(f"v1.1 Trades CSV saved → {out_csv}")
else:
    print("v1.1 produced no trades.")

# ------------------------- Parameter sweep (PB% × TP mult) -------------------------
print("\nRunning parameter sweep (PB% × TP mult)...")
pb_vals = [0.10, 0.15, 0.20, 0.30, 0.40]
tp_vals = [1.0, 1.5, 2.0, 2.5, 3.0]

def run_sim(df_, pb_pct_, tp_mult_, adx_thresh=V11_ADX, min_body=V11_BODY, trail_act=V11_TACT, trail_dist=V11_TDIST):
    tol_ = pb_pct_ / 100.0
    bb_  = (df_["Close"] - df_["Open"]).abs() / df_["ATR"] > min_body
    lp_  = ((df_["Low"].shift(1) <= df_["EMA_FAST"].shift(1) * (1 + tol_)) & (df_["Close"] > df_["EMA_FAST"]) & (df_["Close"] > df_["Open"]) & bb_)
    sp_  = ((df_["High"].shift(1) >= df_["EMA_FAST"].shift(1) * (1 - tol_)) & (df_["Close"] < df_["EMA_FAST"]) & (df_["Close"] < df_["Open"]) & bb_)
    long_sig  = (lp_ & (df_["Close"] > df_["EMA_SLOW"]) & (df_["EMA_FAST"] > df_["EMA_MID"]) & (df_["RSI"] >= RSI_LO_L) & (df_["RSI"] <= RSI_HI_L) & (df_["Volume"] >= df_["VOL_MA"] * VOL_MULT) & (df_["ADX"] > adx_thresh) & ~df_["IS_PANIC"]) & TRADE_LONGS
    short_sig = (sp_ & (df_["Close"] < df_["EMA_SLOW"]) & (df_["EMA_FAST"] < df_["EMA_MID"]) & (df_["RSI"] >= RSI_LO_S) & (df_["RSI"] <= RSI_HI_S) & (df_["Volume"] >= df_["VOL_MA"] * VOL_MULT) & (df_["ADX"] > adx_thresh) & ~df_["IS_PANIC"]) & TRADE_SHORTS

    eq_ = INITIAL_CAPITAL
    pos_ = None
    trades_ = []

    for ts_, row_ in df_.iterrows():
        cl_ = float(row_["Close"]); hi_ = float(row_["High"]); lo_ = float(row_["Low"]); at_ = float(row_["ATR"])
        sd_ = at_ * SL_MULT
        if pos_ is not None:
            d_ = pos_["direction"]
            if d_ == "long":
                if hi_ > pos_["best"]: pos_["best"] = hi_
                if pos_["best"] >= pos_["entry"] + at_ * trail_act:
                    pos_["sl"] = max(pos_["sl"], pos_["best"] - at_ * trail_dist)
                htp_ = hi_ >= pos_["tp"]; hsl_ = lo_ <= pos_["sl"]
                if htp_ or hsl_:
                    xp_ = pos_["tp"] if htp_ else pos_["sl"]
                    pnl_ = (xp_ - pos_["entry"]) / pos_["entry"]
            else:
                if lo_ < pos_["best"]: pos_["best"] = lo_
                if pos_["best"] <= pos_["entry"] - at_ * trail_act:
                    pos_["sl"] = min(pos_["sl"], pos_["best"] + at_ * trail_dist)
                htp_ = lo_ <= pos_["tp"]; hsl_ = hi_ >= pos_["sl"]
                if htp_ or hsl_:
                    xp_ = pos_["tp"] if htp_ else pos_["sl"]
                    pnl_ = (pos_["entry"] - xp_) / pos_["entry"]
            if (('htp_' in locals() and htp_) or ('hsl_' in locals() and hsl_)):
                dp_ = pnl_ * pos_["notional"] - pos_["notional"] * COMMISSION_PCT * 2
                eq_ += dp_
                trades_.append({"dollar_pnl": dp_, "result": "TP" if htp_ else "SL"})
                pos_ = None

        if pos_ is None:
            sig_ = "long" if bool(long_sig[ts_]) else ("short" if bool(short_sig[ts_]) else None)
            if sig_:
                rc_ = eq_ * RISK_PCT; qty_ = rc_ / sd_; not_ = qty_ * cl_
                sl_ = cl_ - sd_ if sig_ == "long" else cl_ + sd_
                tp_ = cl_ + at_ * tp_mult_ if sig_ == "long" else cl_ - at_ * tp_mult_
                pos_ = {"direction": sig_, "entry": cl_, "sl": sl_, "tp": tp_, "best": cl_, "notional": not_}

    if not trades_: return {"ret": float('nan'), "pf": float('nan'), "wr": float('nan'), "n": 0}
    tdf_ = pd.DataFrame(trades_)
    w_ = tdf_[tdf_["dollar_pnl"]>0]; l_ = tdf_[tdf_["dollar_pnl"]<=0]
    ret_ = (eq_ / INITIAL_CAPITAL - 1) * 100
    gp_ = w_["dollar_pnl"].sum() if not w_.empty else 0
    gl_ = l_["dollar_pnl"].sum() if not l_.empty else 0
    pf_ = gp_ / abs(gl_) if gl_ != 0 else float('inf')
    wr_ = len(w_) / len(tdf_) * 100
    return {"ret": round(ret_,2), "pf": round(pf_,3), "wr": round(wr_,1), "n": len(tdf_)}

import itertools
ret_grid = pd.DataFrame(index=pb_vals, columns=tp_vals, dtype=float)
pf_grid  = pd.DataFrame(index=pb_vals, columns=tp_vals, dtype=float)
n_grid   = pd.DataFrame(index=pb_vals, columns=tp_vals, dtype=float)

for pb in pb_vals:
    for tp in tp_vals:
        r = run_sim(df, pb, tp)
        ret_grid.loc[pb, tp] = r["ret"]
        pf_grid.loc[pb, tp]  = r["pf"]
        n_grid.loc[pb, tp]   = r["n"]

ret_grid.index.name = "PB%"
ret_grid.to_csv("sweep_return_grid.csv")
pf_grid.to_csv("sweep_pf_grid.csv")
n_grid.to_csv("sweep_count_grid.csv")
print("Sweep complete. Grids saved: sweep_return_grid.csv, sweep_pf_grid.csv, sweep_count_grid.csv")

# identify best by return
best_idx = ret_grid.stack().idxmax()
best_pb, best_tp = best_idx[0], best_idx[1]
print(f"Best return found: PB={best_pb}% TP×{best_tp} → {ret_grid.loc[best_pb, best_tp]:+.2f}% (Trades={int(n_grid.loc[best_pb,best_tp])})")

# run simulation at best config and save trades + chart
print("Running final simulation at best config...")
best_res = run_sim(df, best_pb, best_tp)
print("Best config metrics:", best_res)

# ------------------------- Profit-factor sweep -------------------------
print("\nRunning profit-factor sweep (PB × TP × ADX × TrailAct)...")
pb_vals_pf = [0.10, 0.12, 0.15, 0.18, 0.20, 0.25]
tp_vals_pf = [1.0, 1.25, 1.5, 1.75, 2.0, 2.5]
adx_vals    = [20, 25, 30]
tact_vals   = [1.0, 1.5, 2.0]

pf_results = []
best_pf = -1.0
best_cfg = None

for pb in pb_vals_pf:
    for tp in tp_vals_pf:
        for adx_v in adx_vals:
            for tact_v in tact_vals:
                r = run_sim(df, pb, tp, adx_thresh=adx_v, min_body=V11_BODY, trail_act=tact_v, trail_dist=V11_TDIST)
                pf_results.append({"PB": pb, "TP": tp, "ADX": adx_v, "TrailAct": tact_v,
                                   "pf": float(r["pf"]), "ret": float(r["ret"]), "wr": float(r["wr"]), "n": int(r["n"])})
                # require at least 5 trades to consider
                if not np.isnan(r["pf"]) and r["n"] >= 5 and float(r["pf"]) > best_pf:
                    best_pf = float(r["pf"])
                    best_cfg = {"PB": pb, "TP": tp, "ADX": adx_v, "TrailAct": tact_v, **r}

pf_df = pd.DataFrame(pf_results)
pf_df.to_csv("pf_sweep_results.csv", index=False)
print(f"PF sweep complete. Results saved → pf_sweep_results.csv (rows: {len(pf_df)})")

if best_cfg is None:
    print("No viable best config found (insufficient trades).")
else:
    print("Best PF config:", best_cfg)
    # run a full simulation at best config and save trades+chart
    def run_and_save(df_, cfg):
        pb_ = cfg["PB"]; tp_ = cfg["TP"]; adx_ = cfg["ADX"]; tact_ = cfg["TrailAct"]
        tol_ = pb_ / 100.0
        min_body_ = V11_BODY
        long_sig_ = (
            (df_["Low"].shift(1) <= df_["EMA_FAST"].shift(1) * (1 + tol_)) &
            (df_["Close"] > df_["EMA_FAST"]) &
            (df_["Close"] > df_["Open"]) &
            ((df_["Close"] - df_["Open"]).abs() / df_["ATR"] >= min_body_) &
            (df_["Close"] > df_["EMA_SLOW"]) &
            (df_["EMA_FAST"] > df_["EMA_MID"]) &
            (df_["RSI"] >= RSI_LO_L) & (df_["RSI"] <= RSI_HI_L) &
            (df_["Volume"] >= df_["VOL_MA"] * VOL_MULT) &
            (df_["ADX"] > adx_) & ~df_["IS_PANIC"]
        ) & TRADE_LONGS

        short_sig_ = (
            (df_["High"].shift(1) >= df_["EMA_FAST"].shift(1) * (1 - tol_)) &
            (df_["Close"] < df_["EMA_FAST"]) &
            (df_["Close"] < df_["Open"]) &
            ((df_["Close"] - df_["Open"]).abs() / df_["ATR"] >= min_body_) &
            (df_["Close"] < df_["EMA_SLOW"]) &
            (df_["EMA_FAST"] < df_["EMA_MID"]) &
            (df_["RSI"] >= RSI_LO_S) & (df_["RSI"] <= RSI_HI_S) &
            (df_["Volume"] >= df_["VOL_MA"] * VOL_MULT) &
            (df_["ADX"] > adx_) & ~df_["IS_PANIC"]
        ) & TRADE_SHORTS

        eq = INITIAL_CAPITAL
        pos = None
        trades_out = []
        eqcurve_out = []

        for ts_, row_ in df_.iterrows():
            close = float(row_["Close"]); high = float(row_["High"]); low = float(row_["Low"]); atr = float(row_["ATR"])
            sd = atr * SL_MULT
            if pos is not None:
                d = pos["direction"]
                if d == "long":
                    if high > pos["best"]: pos["best"] = high
                    if pos["best"] >= pos["entry"] + atr * tact_:
                        pos["sl"] = max(pos["sl"], pos["best"] - atr * V11_TDIST)
                    htp = high >= pos["tp"]; hsl = low <= pos["sl"]
                    if htp or hsl:
                        xp = pos["tp"] if htp else pos["sl"]
                        pnl = (xp - pos["entry"]) / pos["entry"]
                else:
                    if low < pos["best"]: pos["best"] = low
                    if pos["best"] <= pos["entry"] - atr * tact_:
                        pos["sl"] = min(pos["sl"], pos["best"] + atr * V11_TDIST)
                    htp = low <= pos["tp"]; hsl = high >= pos["sl"]
                    if htp or hsl:
                        xp = pos["tp"] if htp else pos["sl"]
                        pnl = (pos["entry"] - xp) / pos["entry"]

                if (('htp' in locals() and htp) or ('hsl' in locals() and hsl)):
                    dp = pnl * pos["notional"] - pos["notional"] * COMMISSION_PCT * 2
                    eq += dp
                    trades_out.append({"entry_time": pos.get("entry_time"), "exit_time": ts_,
                                       "direction": d, "entry": pos["entry"], "exit": xp,
                                       "result": "TP" if htp else "SL", "pnl_pct": round(pnl*100,3),
                                       "dollar_pnl": round(dp,2), "equity": round(eq,2)})
                    pos = None

            if pos is None:
                sig = "long" if bool(long_sig_[ts_]) else ("short" if bool(short_sig_[ts_]) else None)
                if sig:
                    rc = eq * RISK_PCT; qty = rc / sd; notl = qty * close
                    sl = close - sd if sig == "long" else close + sd
                    tp = close + atr * tp_ if sig == "long" else close - atr * tp_
                    pos = {"direction": sig, "entry": close, "entry_time": ts_, "sl": sl, "tp": tp, "best": close, "notional": notl}

            eqcurve_out.append({"time": ts_, "equity": eq})

        # save outputs
        out_csv = f"pf_best_trades_pb{pb_}_tp{tp_}_adx{adx_}_tact{tact_}_{TICKER.replace('-','').lower()}_{INTERVAL}.csv"
        pd.DataFrame(trades_out).to_csv(out_csv, index=False)
        out_png = f"pf_best_equity_pb{pb_}_tp{tp_}_adx{adx_}_tact{tact_}_{TICKER.replace('-','').lower()}_{INTERVAL}.png"
        ecdf = pd.DataFrame(eqcurve_out).set_index("time")
        plt.style.use("dark_background")
        fig, ax = plt.subplots(figsize=(12,4))
        ax.plot(ecdf.index, ecdf["equity"], color="#68d391")
        ax.axhline(INITIAL_CAPITAL, color="white", ls=":")
        ax.set_title(f"PF Best Equity PB={pb_}% TP×{tp_} ADX>{adx_} Tact={tact_}")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
        plt.tight_layout(); plt.savefig(out_png, dpi=150, bbox_inches="tight")
        return {"csv": out_csv, "png": out_png, "trades": len(trades_out)}

    saved = run_and_save(df, best_cfg)
    print("Saved best-config outputs:", saved)

# ------------------------- Proposed modifiers (aim for winning return) -------------------------
print("\nRunning proposed improved config (stricter filters + smaller risk)...")
proposed_cfg = {
    "PB": 0.20,        # pullback tolerance
    "TP": 1.5,         # take profit × ATR
    "ADX": 30,         # stricter ADX
    "TrailAct": 2.0,   # trail activates later
    "TrailDist": 1.0,  # trail distance (looser than v11)
    "MinBody": 0.20,   # require stronger momentum bar
    "VolMult": 1.5,    # require higher-than-normal volume
    "RiskPct": 0.003   # risk 0.3% equity per trade (smaller sizing)
}

def run_proposed(df_, cfg):
    pb = cfg["PB"]; tp = cfg["TP"]; adx = cfg["ADX"]; tact = cfg["TrailAct"]
    trail_dist = cfg.get("TrailDist", V11_TDIST)
    min_body = cfg.get("MinBody", V11_BODY)
    vol_mult = cfg.get("VolMult", VOL_MULT)
    risk_pct = cfg.get("RiskPct", RISK_PCT)

    tol = pb / 100.0
    long_sig_p = (
        (df_["Low"].shift(1) <= df_["EMA_FAST"].shift(1) * (1 + tol)) &
        (df_["Close"] > df_["EMA_FAST"]) &
        (df_["Close"] > df_["Open"]) &
        ((df_["Close"] - df_["Open"]).abs() / df_["ATR"] >= min_body) &
        (df_["Volume"] >= df_["VOL_MA"] * vol_mult) &
        (df_["Close"] > df_["EMA_SLOW"]) &
        (df_["EMA_FAST"] > df_["EMA_MID"]) &
        (df_["ADX"] > adx) & ~df_["IS_PANIC"]
    ) & TRADE_LONGS

    short_sig_p = (
        (df_["High"].shift(1) >= df_["EMA_FAST"].shift(1) * (1 - tol)) &
        (df_["Close"] < df_["EMA_FAST"]) &
        (df_["Close"] < df_["Open"]) &
        ((df_["Close"] - df_["Open"]).abs() / df_["ATR"] >= min_body) &
        (df_["Volume"] >= df_["VOL_MA"] * vol_mult) &
        (df_["Close"] < df_["EMA_SLOW"]) &
        (df_["EMA_FAST"] < df_["EMA_MID"]) &
        (df_["ADX"] > adx) & ~df_["IS_PANIC"]
    ) & TRADE_SHORTS

    eq = INITIAL_CAPITAL
    pos = None
    trades_p = []
    eqcurve_p = []

    for ts, row in df_.iterrows():
        close = float(row["Close"]) ; high = float(row["High"]) ; low = float(row["Low"]) ; atr = float(row["ATR"])
        sd = atr * SL_MULT

        if pos is not None:
            d = pos["direction"]
            if d == "long":
                if high > pos["best"]: pos["best"] = high
                if pos["best"] >= pos["entry"] + atr * tact:
                    pos["sl"] = max(pos["sl"], pos["best"] - atr * trail_dist)
                htp = high >= pos["tp"]; hsl = low <= pos["sl"]
                if htp or hsl:
                    xp = pos["tp"] if htp else pos["sl"]
                    pnl = (xp - pos["entry"]) / pos["entry"]
            else:
                if low < pos["best"]: pos["best"] = low
                if pos["best"] <= pos["entry"] - atr * tact:
                    pos["sl"] = min(pos["sl"], pos["best"] + atr * trail_dist)
                htp = low <= pos["tp"]; hsl = high >= pos["sl"]
                if htp or hsl:
                    xp = pos["tp"] if htp else pos["sl"]
                    pnl = (pos["entry"] - xp) / pos["entry"]

            if (('htp' in locals() and htp) or ('hsl' in locals() and hsl)):
                dp = pnl * pos["notional"] - pos["notional"] * COMMISSION_PCT * 2
                eq += dp
                trades_p.append({"entry_time": pos.get("entry_time"), "exit_time": ts,
                                 "direction": d, "entry": pos["entry"], "exit": xp,
                                 "result": "TP" if htp else "SL", "pnl_pct": round(pnl*100,3),
                                 "dollar_pnl": round(dp,2), "equity": round(eq,2)})
                pos = None

        if pos is None:
            sig = "long" if bool(long_sig_p[ts]) else ("short" if bool(short_sig_p[ts]) else None)
            if sig:
                rc = eq * risk_pct; qty = rc / sd; notl = qty * close
                sl = close - sd if sig == "long" else close + sd
                tp_px = close + atr * tp if sig == "long" else close - atr * tp
                pos = {"direction": sig, "entry": close, "entry_time": ts, "sl": sl, "tp": tp_px, "best": close, "notional": notl}

        eqcurve_p.append({"time": ts, "equity": eq})

    # save outputs
    out_csv = f"proposed_trades_pb{pb}_tp{tp}_adx{adx}_tact{tact}_{TICKER.replace('-','').lower()}_{INTERVAL}.csv"
    pd.DataFrame(trades_p).to_csv(out_csv, index=False)
    out_png = f"proposed_equity_pb{pb}_tp{tp}_adx{adx}_tact{tact}_{TICKER.replace('-','').lower()}_{INTERVAL}.png"
    pd.DataFrame(eqcurve_p).set_index("time").plot(title=f"Proposed Equity PB={pb}% TP×{tp} ADX>{adx} Tact={tact}")
    plt.savefig(out_png, dpi=150, bbox_inches="tight")
    return {"csv": out_csv, "png": out_png, "trades": len(trades_p), "final_equity": eq}

res_prop = run_proposed(df, proposed_cfg)
print("Proposed config outputs:", res_prop)

if res_prop["trades"] == 0:
    print("Proposed config produced no trades — consider relaxing filters.")
else:
    print(f"Proposed final equity: ${res_prop['final_equity']:.2f}  Trades: {res_prop['trades']}")




