#!/usr/bin/env python3
"""
docs/paper_trader_v3.py — wrapper for
scripts/CLM/Adaptive Pullback Momentum v3/paper_trader_clm_v3.py

Run as: python docs/paper_trader_v3.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TARGET = (
    Path(__file__).resolve().parent.parent
    / "scripts" / "CLM" / "Adaptive Pullback Momentum v3"
    / "paper_trader_clm_v3.py"
)


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not TARGET.exists():
        print(f"Target script not found: {TARGET}", file=sys.stderr)
        return 2
    cmd = [sys.executable, str(TARGET)] + list(argv)
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
