#!/usr/bin/env python3

"""Validate CLM dashboard feeds against the canonical generated backtest outputs."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
CLM_DIR = REPO_ROOT / "scripts" / "CLM"
DOCS_CLM_DIR = REPO_ROOT / "docs" / "data" / "clm"


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
    doc_df.insert(0, "entry_time", doc_df["exit_time"])
    return doc_df[
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
    ]


def canonicalise_v4_docs(df: pd.DataFrame) -> pd.DataFrame:
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


def canonicalise_v5(df: pd.DataFrame) -> pd.DataFrame:
    canon = df.rename(columns={"pnl": "dollar_pnl", "exit_reason": "result"}).copy()
    return canon[
        [
            "entry_time",
            "exit_time",
            "direction",
            "entry",
            "exit",
            "dollar_pnl",
            "equity",
            "result",
        ]
    ]


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
    return out


CONFIGS = {
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
    left = normalise(config["generated_to_docs"](source_df))
    right = normalise(config["docs_to_compare"](docs_df))

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
    for version in ("v4", "v5", "v6"):
        ok, message = compare_version(version, sync_first=args.sync)
        print(message)
        failed = failed or not ok

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())