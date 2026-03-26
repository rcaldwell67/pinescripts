#!/usr/bin/env python3
"""
Standardize BTCUSD dashboard CSV headers for v1-v6.
- All output: entry_time,exit_time,direction,entry,exit,result,pnl_pct,dollar_pnl,equity
- Adds empty columns if missing, renames as needed.
"""
import pandas as pd
from pathlib import Path

STANDARD_COLS = [
    "entry_time","exit_time","direction","entry","exit",
    "result","pnl_pct","dollar_pnl","equity"
]

# Map of version to file
files = {
    "v1": "docs/data/btcusd/v1_trades.csv",
    "v2": "docs/data/btcusd/v2_trades.csv",
    "v3": "docs/data/btcusd/v3_trades.csv",
    "v4": "docs/data/btcusd/v4_trades.csv",
    "v5": "docs/data/btcusd/v5_trades.csv",
    "v6": "docs/data/btcusd/v6_trades.csv",
}

def canonicalize(df, version):
    df = df.copy()
    # v3: entry_price/exit_price → entry/exit
    if version == "v3":
        df = df.rename(columns={"entry_price": "entry", "exit_price": "exit"})
    # v5: pnl → dollar_pnl, exit_reason → result
    if version == "v5":
        df = df.rename(columns={"pnl": "dollar_pnl", "exit_reason": "result"})
    # v6: add missing columns, reorder, fill blanks
    if version == "v6":
        if "result" not in df.columns:
            df["result"] = ""
        if "pnl_pct" not in df.columns:
            df["pnl_pct"] = ""
        if "dollar_pnl" not in df.columns and "pnl" in df.columns:
            df = df.rename(columns={"pnl": "dollar_pnl"})
        for col in STANDARD_COLS:
            if col not in df.columns:
                df[col] = ""
        df = df[STANDARD_COLS]
        return df
    # All others: add missing columns, reorder
    for col in STANDARD_COLS:
        if col not in df.columns:
            df[col] = ""
    df = df[STANDARD_COLS]
    return df

for version, path in files.items():
    p = Path(path)
    if not p.exists():
        print(f"{path} not found, skipping.")
        continue
    df = pd.read_csv(p)
    canon = canonicalize(df, version)
    canon.to_csv(p, index=False)
    print(f"Standardized: {path}")
