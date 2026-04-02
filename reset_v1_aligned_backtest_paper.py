"""Compatibility wrapper for regenerating aligned v1 backtest/paper datasets."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "reset_aligned_backtest_paper.py"


if __name__ == "__main__":
    cmd = [sys.executable, str(TARGET), "--version", "v1", *sys.argv[1:]]
    raise SystemExit(subprocess.call(cmd))
