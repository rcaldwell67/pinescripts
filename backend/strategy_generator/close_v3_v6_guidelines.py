from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SYMBOLS = ["BTC/USD", "CLM", "CRF", "ETH/USD", "BTC/USDC", "BTC/USDT"]
DEFAULT_VERSIONS = ["v3", "v4", "v5", "v6"]


def run_step(command: list[str]) -> None:
    print(f"\n>>> {' '.join(command)}")
    completed = subprocess.run(command, cwd=REPO_ROOT)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def safe_symbol(symbol: str) -> str:
    return "".join(ch for ch in symbol.lower() if ch.isalnum())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Tune selected v3-v6 symbols and optionally apply passing guideline candidates."
    )
    parser.add_argument("--symbols", nargs="*", default=DEFAULT_SYMBOLS, help="Symbols to retune")
    parser.add_argument("--versions", nargs="*", default=DEFAULT_VERSIONS, help="Versions to retune (v3-v6)")
    parser.add_argument("--max-evals", type=int, default=300, help="Per-symbol tuning budget")
    parser.add_argument("--seed-base", type=int, default=211, help="Base seed; each symbol/version gets an incremented seed")
    args = parser.parse_args()

    python_exe = sys.executable

    valid_versions = {"v3", "v4", "v5", "v6"}
    versions = [v.strip().lower() for v in args.versions if v and v.strip()]
    invalid = [v for v in versions if v not in valid_versions]
    if invalid:
        raise SystemExit(f"Unsupported versions: {invalid}; expected subset of {sorted(valid_versions)}")

    seed = args.seed_base
    for version in versions:
        for symbol in args.symbols:
            out_path = f"docs/data/{version}_profile_tuning_result_{safe_symbol(symbol)}_guideline.json"
            command = [
                python_exe,
                "backend/strategy_generator/tune_v3_v6_profile.py",
                "--version",
                version,
                "--symbol",
                symbol,
                "--max-evals",
                str(args.max_evals),
                "--seed",
                str(seed),
                "--min-win-rate",
                "70",
                "--min-net-return",
                "20",
                "--max-drawdown",
                "4.5",
                "--out",
                out_path,
                "--apply",
            ]
            run_step(command)
            seed += 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
