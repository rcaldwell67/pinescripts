from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SYMBOLS = ["BTC/USD", "ETH/USD"]


def run_step(command: list[str]) -> None:
    print(f"\n>>> {' '.join(command)}")
    completed = subprocess.run(command, cwd=REPO_ROOT)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main() -> int:
    parser = argparse.ArgumentParser(description="Tune selected v2 symbols, validate config usage, and enforce the v2 guideline matrix.")
    parser.add_argument("--symbols", nargs="*", default=DEFAULT_SYMBOLS, help="Symbols to retune before enforcement")
    parser.add_argument("--profile", default="guideline_closed", help="Optional v2 profile name to write/apply during closure")
    parser.add_argument("--max-evals", type=int, default=900, help="Per-symbol tuning budget")
    parser.add_argument("--seed-base", type=int, default=111, help="Base seed; each symbol gets an incremented seed")
    parser.add_argument(
        "--report-out",
        default="docs/data/v2_guideline_report_default_all.json",
        help="Output path for the final enforced report",
    )
    parser.add_argument("--skip-tune", action="store_true", help="Skip tuning and only validate/report with the selected profile")
    args = parser.parse_args()

    python_exe = sys.executable

    if not args.skip_tune:
        for index, symbol in enumerate(args.symbols):
            safe_symbol = "".join(ch for ch in symbol.lower() if ch.isalnum())
            out_path = f"docs/data/v2_profile_tuning_result_{safe_symbol}_guideline.json"
            command = [
                python_exe,
                "backend/strategy_generator/tune_v2_profile.py",
                "--symbol",
                symbol,
                "--max-evals",
                str(args.max_evals),
                "--seed",
                str(args.seed_base + index),
                "--profile",
                args.profile,
                "--out",
                out_path,
                "--apply",
            ]
            run_step(command)

    run_step([python_exe, "backend/strategy_generator/validate_v2_config_usage.py"])
    run_step(
        [
            python_exe,
            "backend/strategy_generator/report_v2_guidelines.py",
            "--version",
            "v2",
            "--profile",
            args.profile,
            "--asset-class",
            "all",
            "--json-out",
            args.report_out,
            "--enforce",
        ]
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())