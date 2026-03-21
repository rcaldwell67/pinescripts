#!/usr/bin/env python3
from __future__ import annotations

# --- BTCUSD CANONICALISATION FUNCTIONS ---
def canonicalise_btcusd_v3(df: pd.DataFrame) -> pd.DataFrame:
    # Map entry_price/exit_price to entry/exit for schema compatibility
    canon = df.rename(columns={"entry_price": "entry", "exit_price": "exit"}).copy()
    # Map pnl to dollar_pnl if present
    if "pnl" in canon.columns and "dollar_pnl" not in canon.columns:
        canon = canon.rename(columns={"pnl": "dollar_pnl"})
    # Map exit_reason to result if present
    if "exit_reason" in canon.columns and "result" not in canon.columns:
        canon = canon.rename(columns={"exit_reason": "result"})
    # Ensure all columns exist
    for col in ["result", "dollar_pnl", "pnl_pct"]:
        if col not in canon.columns:
            canon[col] = ""
    return canon[[
        "entry_time",
        "exit_time",
        "direction",
        "entry",
        "exit",
        "result",
        "pnl_pct",
        "dollar_pnl",
        "equity",
    ]].copy()

def canonicalise_btcusd_v4_v5(df: pd.DataFrame) -> pd.DataFrame:
    # Map pnl to dollar_pnl, exit_reason to result
    canon = df.rename(columns={"pnl": "dollar_pnl", "exit_reason": "result"}).copy()
    # Always output all 9 columns, filling missing with empty string
    required_cols = [
        "entry_time",
        "exit_time",
        "direction",
        "entry",
        "exit",
        "result",
        "pnl_pct",
        "dollar_pnl",
        "equity",
    ]
    for col in required_cols:
        if col not in canon.columns:
            canon[col] = ""
    # Reorder and ensure all columns are present
    canon = canon[required_cols].copy()
    return canon

import argparse
import shutil
import sys
from pathlib import Path
import pandas as pd
def compare_version(version: str, sync_first: bool) -> tuple[bool, str]:
    config = CONFIGS[version]
    source_path = pick_existing_path(config["generated_paths"])
    docs_path = config["docs_path"]

    if source_path is None:
        return False, f"{version}: missing canonical generated output"
    if sync_first:
        sync_docs(version, source_path, docs_path)
    if not docs_path.exists():
        return False, f"{version}: missing dashboard file {docs_path.relative_to(REPO_ROOT)}"

    source_df = pd.read_csv(source_path)
    docs_df = pd.read_csv(docs_path)
    # Force canonicalization for BTCUSD v4 regardless of input columns
    if version == "v4" and 'BTCUSD_CONFIGS' in globals():
        canon_left = canonicalise_btcusd_v4_v5(source_df)
        canon_right = canonicalise_btcusd_v4_v5(docs_df)
        print(f"\n--- DEBUG: BTCUSD v4 canonicalized (pre-normalize) ---")
        print("LEFT (first 3 rows):")
        print(canon_left.head(3))
        print("RIGHT (first 3 rows):")
        print(canon_right.head(3))
        left = normalise(canon_left)
        right = normalise(canon_right)
    elif version == "v4":
        canon_left = config["generated_to_docs"](source_df)
        canon_right = config["docs_to_compare"](docs_df)
        print(f"\n--- DEBUG: CLM v4 canonicalized (pre-normalize) ---")
        print("LEFT (first 3 rows):")
        print(canon_left.head(3))
        print("RIGHT (first 3 rows):")
        print(canon_right.head(3))
        left = normalise(canon_left)
        right = normalise(canon_right)
    else:
        left = normalise(config["generated_to_docs"](source_df))
        right = normalise(config["docs_to_compare"](docs_df))

    print(f"\n--- DEBUG: {version} DataFrame shapes and columns ---")
    print(f"left shape: {left.shape}, columns: {list(left.columns)}")
    print(f"right shape: {right.shape}, columns: {list(right.columns)}")
    if version == 'v4':
        print('LEFT (first 3 rows):')
        print(left.head(3))
        print('RIGHT (first 3 rows):')
        print(right.head(3))
    import sys; sys.stdout.flush()
    if left.equals(right):
        return True, (
            f"{version}: OK  source={source_path.relative_to(REPO_ROOT)}  "
            f"dashboard={docs_path.relative_to(REPO_ROOT)}"
        )

    details = []
    if len(left) != len(right):
        details.append(f"rows {len(left)} != {len(right)}")
    if list(left.columns) != list(right.columns):
        details.append("column mismatch")
    if not details:
        mismatch_row = (left != right).any(axis=1)
        first_bad = int(mismatch_row.idxmax()) if mismatch_row.any() else 0
        details.append(f"first mismatch at row {first_bad + 1}")
        # Print detailed debug info for the first mismatch
        print(f"\n--- DEBUG: First mismatch details for {version} ---")
        print(f"Row: {first_bad}")
        for col in left.columns:
            lval = left.iloc[first_bad][col]
            rval = right.iloc[first_bad][col]
            if lval != rval:
                print(f"Col: {col} | left: {lval!r} | right: {rval!r}")
        print(f"--- END DEBUG ---\n")
        sys.stdout.flush()
    return False, (
        f"{version}: MISMATCH ({', '.join(details)})  "
        f"source={source_path.relative_to(REPO_ROOT)}  dashboard={docs_path.relative_to(REPO_ROOT)}"
    )



def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sync",
        action="store_true",
        help="refresh docs/data/clm/v4_trades.csv through v6_trades.csv from the canonical generated outputs before validating",
    )
    return parser.parse_args()




REPO_ROOT = Path(__file__).resolve().parent.parent
CLM_DIR = REPO_ROOT / "scripts" / "CLM"
DOCS_CLM_DIR = REPO_ROOT / "docs" / "data" / "clm"

# --- BTCUSD CONFIGS ---
BTCUSD_DIR = REPO_ROOT / "scripts" / "BTCUSD"
DOCS_BTCUSD_DIR = REPO_ROOT / "docs" / "data" / "btcusd"


def pick_existing_path(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def canonicalise_v4_generated(df: pd.DataFrame) -> pd.DataFrame:
    doc_df = df.rename(
        columns={
            "ts": "exit_time",
            "dir": "direction",
            "reason": "result",
            "dp": "dollar_pnl",
        }
    ).copy()
    if "entry_time" not in doc_df.columns:
        doc_df.insert(0, "entry_time", doc_df["exit_time"])
    required_cols = [
        "entry_time",
        "exit_time",
        "direction",
        "entry",
        "exit",
        "result",
        "pnl_pct",
        "dollar_pnl",
        "equity",
    ]
    for col in required_cols:
        if col not in doc_df.columns:
            doc_df[col] = ""
    return doc_df[required_cols].copy()


def canonicalise_v4_docs(df: pd.DataFrame) -> pd.DataFrame:
    return df[
        [
            "entry_time",
            "exit_time",
            "direction",
            "entry",
            "equity",
        ]
    ].copy()


def canonicalise_v5(df: pd.DataFrame) -> pd.DataFrame:
    canon = df.rename(columns={"pnl": "dollar_pnl", "exit_reason": "result"}).copy()
    # Ensure all columns exist
    for col in ["result", "dollar_pnl", "pnl_pct"]:
        if col not in canon.columns:
            canon[col] = ""
    return canon[[
        "entry_time",
        "exit_time",
        "direction",
        "entry",
        "exit",
        "result",
        "pnl_pct",
        "dollar_pnl",
        "equity",
    ]].copy()



def canonicalise_v1(df: pd.DataFrame) -> pd.DataFrame:
    return df[
        [
            "entry_time",
            "exit_time",
            "direction",
            "entry",
            "exit",
            "result",
            "pnl_pct",
            "dollar_pnl",
            "equity",
        ]
    ].copy()

def canonicalise_v2(df: pd.DataFrame) -> pd.DataFrame:
    return df[
        [
            "entry_time",
            "exit_time",
            "direction",
            "entry",
            "exit",
            "result",
            "pnl_pct",
            "dollar_pnl",
            "equity",
        ]
    ].copy()

def canonicalise_v3(df: pd.DataFrame) -> pd.DataFrame:
    # Map entry_price/exit_price to entry/exit if present
    canon = df.rename(columns={"entry_price": "entry", "exit_price": "exit"}).copy()
    # Map pnl to dollar_pnl if present
    if "pnl" in canon.columns and "dollar_pnl" not in canon.columns:
        canon = canon.rename(columns={"pnl": "dollar_pnl"})
    # Map exit_reason to result if present
    if "exit_reason" in canon.columns and "result" not in canon.columns:
        canon = canon.rename(columns={"exit_reason": "result"})
    # Ensure all columns exist
    for col in ["result", "dollar_pnl", "pnl_pct"]:
        if col not in canon.columns:
            canon[col] = ""
    return canon[[
        "entry_time",
        "exit_time",
        "direction",
        "entry",
        "exit",
        "result",
        "pnl_pct",
        "dollar_pnl",
        "equity",
    ]].copy()

def canonicalise_v6(df: pd.DataFrame) -> pd.DataFrame:
    return df[
        [
            "entry_time",
            "exit_time",
            "direction",
            "entry",
            "exit",
            "dollar_pnl",
            "equity",
            "result",
            "max_runup",
            "bars",
            "pnl_pct",
            "year",
        ]
    ].copy()

# --- BTCUSD CONFIGS ---
BTCUSD_DIR = REPO_ROOT / "scripts" / "BTCUSD"
DOCS_BTCUSD_DIR = REPO_ROOT / "docs" / "data" / "btcusd"
BTCUSD_CONFIGS = {
    "v1": {
        "generated_paths": [
            REPO_ROOT / "apm_v1_ytd_trades_btcusd_5m.csv",
            BTCUSD_DIR / "Adaptive Pullback Momentum v1" / "apm_v1_ytd_trades_btcusd_5m.csv",
        ],
        "docs_path": DOCS_BTCUSD_DIR / "v1_trades.csv",
        "generated_to_docs": canonicalise_v1,
        "docs_to_compare": canonicalise_v1,
        "sync_mode": "copy",
    },
    "v2": {
        "generated_paths": [
            REPO_ROOT / "apm_v2_trades_btc-usd_10m.csv",
            BTCUSD_DIR / "Adaptive Pullback Momentum v2" / "apm_v2_trades_btc-usd_10m.csv",
        ],
        "docs_path": DOCS_BTCUSD_DIR / "v2_trades.csv",
        "generated_to_docs": canonicalise_v2,
        "docs_to_compare": canonicalise_v2,
        "sync_mode": "copy",
    },
    "v3": {
        "generated_paths": [
            REPO_ROOT / "apm_v3_trades_btcusd_15m.csv",
            BTCUSD_DIR / "Adaptive Pullback Momentum v3" / "apm_v3_trades_btcusd_15m.csv",
        ],
        "docs_path": DOCS_BTCUSD_DIR / "v3_trades.csv",
        "generated_to_docs": canonicalise_btcusd_v3,
        "docs_to_compare": canonicalise_btcusd_v3,
        "sync_mode": "copy",
    },
    "v4": {
        "generated_paths": [
            REPO_ROOT / "apm_v4_trades_btcusd_30m.csv",
            BTCUSD_DIR / "Adaptive Pullback Momentum v4" / "apm_v4_trades_btcusd_30m.csv",
        ],
        "docs_path": DOCS_BTCUSD_DIR / "v4_trades.csv",
        "generated_to_docs": canonicalise_btcusd_v4_v5,
        "docs_to_compare": canonicalise_btcusd_v4_v5,
        "sync_mode": "rewrite",
    },
    "v5": {
        "generated_paths": [
            REPO_ROOT / "apm_v5_trades_btcusd_1h.csv",
            BTCUSD_DIR / "Adaptive Pullback Momentum v5" / "apm_v5_trades_btcusd_1h.csv",
        ],
        "docs_path": DOCS_BTCUSD_DIR / "v5_trades.csv",
        "generated_to_docs": canonicalise_btcusd_v4_v5,
        "docs_to_compare": canonicalise_btcusd_v4_v5,
        "sync_mode": "copy",
    },
    "v6": {
        "generated_paths": [
            REPO_ROOT / "scripts" / "BTCUSD" / "Adaptive Pullback Momentum v6" / "apm_v6_trades_btcusd_1d.csv",
            REPO_ROOT / "apm_v6_trades_btcusd_1d.csv",
        ],
        "docs_path": DOCS_BTCUSD_DIR / "v6_trades.csv",
        "generated_to_docs": canonicalise_v6,
        "docs_to_compare": canonicalise_v6,
        "sync_mode": "copy",
    },
}

def canonicalise_v6(df: pd.DataFrame) -> pd.DataFrame:
    return df[
        [
            "entry_time",
            "exit_time",
            "direction",
            "entry",
            "exit",
            "dollar_pnl",
            "equity",
            "result",
            "max_runup",
            "bars",
            "pnl_pct",
            "year",
        ]
    ].copy()


def normalise(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy().reset_index(drop=True)
    for column in out.columns:
        if pd.api.types.is_numeric_dtype(out[column]):
            out[column] = pd.to_numeric(out[column], errors="coerce").round(10)
        else:
            out[column] = out[column].fillna("").astype(str).str.strip()
            if column == "direction":
                out[column] = out[column].str.lower()
            elif column == "result":
                out[column] = out[column].str.upper()
    # Drop fully empty rows
    out = out[~(out == "").all(axis=1)].reset_index(drop=True)
    return out


CONFIGS = {
    "v1": {
        "generated_paths": [
            CLM_DIR / "Adaptive Pullback Momentum v1" / "apm_v1_ytd_trades_clm_5m.csv",
            REPO_ROOT / "apm_v1_ytd_trades_clm_5m.csv",
        ],
        "docs_path": DOCS_CLM_DIR / "v1_trades.csv",
        "generated_to_docs": canonicalise_v1,
        "docs_to_compare": canonicalise_v1,
        "sync_mode": "copy",
    },
    "v2": {
        "generated_paths": [
            CLM_DIR / "Adaptive Pullback Momentum v2" / "apm_v2_trades_clm_10m.csv",
            REPO_ROOT / "apm_v2_trades_clm_10m.csv",
        ],
        "docs_path": DOCS_CLM_DIR / "v2_trades.csv",
        "generated_to_docs": canonicalise_v2,
        "docs_to_compare": canonicalise_v2,
        "sync_mode": "copy",
    },
    "v3": {
        "generated_paths": [
            CLM_DIR / "Adaptive Pullback Momentum v3" / "apm_v3_trades_clm_15m.csv",
            REPO_ROOT / "apm_v3_trades_clm_15m.csv",
        ],
        "docs_path": DOCS_CLM_DIR / "v3_trades.csv",
        "generated_to_docs": canonicalise_v3,
        "docs_to_compare": canonicalise_v3,
        "sync_mode": "copy",
    },
    "v4": {
        "generated_paths": [
            CLM_DIR / "Adaptive Pullback Momentum v4" / "outputs" / "apm_v4_v46_trades_clm_30m.csv",
            CLM_DIR / "Adaptive Pullback Momentum v4" / "apm_v4_v46_trades_clm_30m.csv",
        ],
        "docs_path": DOCS_CLM_DIR / "v4_trades.csv",
        "generated_to_docs": canonicalise_v4_generated,
        "docs_to_compare": canonicalise_v4_docs,
        "sync_mode": "rewrite",
    },
    "v5": {
        "generated_paths": [
            CLM_DIR / "Adaptive Pullback Momentum v5" / "outputs" / "apm_v5_trades_clm_1h.csv",
            REPO_ROOT / "apm_v5_trades_clm_1h.csv",
            CLM_DIR / "Adaptive Pullback Momentum v5" / "apm_v5_trades_clm_1h.csv",
        ],
        "docs_path": DOCS_CLM_DIR / "v5_trades.csv",
        "generated_to_docs": canonicalise_v5,
        "docs_to_compare": canonicalise_v5,
        "sync_mode": "copy",
    },
    "v6": {
        "generated_paths": [
            CLM_DIR / "Adaptive Pullback Momentum v6" / "outputs" / "apm_v6_trades_clm_1d.csv",
            REPO_ROOT / "apm_v6_trades_clm_1d.csv",
            CLM_DIR / "Adaptive Pullback Momentum v6" / "apm_v6_trades_clm_1d.csv",
        ],
        "docs_path": DOCS_CLM_DIR / "v6_trades.csv",
        "generated_to_docs": canonicalise_v6,
        "docs_to_compare": canonicalise_v6,
        "sync_mode": "copy",
    },
}


def sync_docs(version: str, source_path: Path, docs_path: Path) -> None:
    config = CONFIGS[version]
    docs_path.parent.mkdir(parents=True, exist_ok=True)
    if config["sync_mode"] == "copy":
        shutil.copy2(source_path, docs_path)
        return

    source_df = pd.read_csv(source_path)
    config["generated_to_docs"](source_df).to_csv(docs_path, index=False)




def main() -> int:
    args = parse_args()
    print("Validating CLM dashboard sync")
    print(f"Repo root: {REPO_ROOT}")
    if args.sync:
        print("Mode: sync then validate")
    else:
        print("Mode: validate only")
    print()

    failed = False
    # CLM validation
    for version in ("v1", "v2", "v3", "v4", "v5", "v6"):
        ok, message = compare_version(version, sync_first=args.sync)
        print(message)
        failed = failed or not ok

    # BTCUSD validation
    for version in ("v1", "v2", "v3", "v4", "v5", "v6"):
        config = BTCUSD_CONFIGS[version]
        source_path = pick_existing_path(config["generated_paths"])
        docs_path = config["docs_path"]
        if source_path is None:
            print(f"BTCUSD {version}: missing canonical generated output")
            failed = True
            continue
        if args.sync:
            sync_docs(version, source_path, docs_path)
        if not docs_path.exists():
            print(f"BTCUSD {version}: missing dashboard file {docs_path.relative_to(REPO_ROOT)}")
            failed = True
            continue
        source_df = pd.read_csv(source_path)
        docs_df = pd.read_csv(docs_path)
        if version == "v4":
            canon_left = config["generated_to_docs"](source_df)
            canon_right = config["docs_to_compare"](docs_df)
            print(f"\n--- DEBUG: BTCUSD v4 canonicalized (pre-normalize, BTCUSD loop) ---")
            print("LEFT (first 3 rows):")
            print(canon_left.head(3))
            print("RIGHT (first 3 rows):")
            print(canon_right.head(3))
            left = normalise(canon_left)
            right = normalise(canon_right)
        else:
            left = normalise(config["generated_to_docs"](source_df))
            right = normalise(config["docs_to_compare"](docs_df))
        if left.equals(right):
            print(f"BTCUSD {version}: OK  source={source_path.relative_to(REPO_ROOT)}  dashboard={docs_path.relative_to(REPO_ROOT)}")
        else:
            print(f"BTCUSD {version}: MISMATCH  source={source_path.relative_to(REPO_ROOT)}  dashboard={docs_path.relative_to(REPO_ROOT)}")
            failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())