# Copy the latest snapshot to the dashboard location
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LATEST_SNAPSHOT = REPO_ROOT / "db_snapshots" / "tradingcopilot_20260414_204125.db"
DASHBOARD_DB = REPO_ROOT / "frontend-react" / "public" / "data" / "tradingcopilot.db"

if not LATEST_SNAPSHOT.exists():
    raise FileNotFoundError(f"Snapshot not found: {LATEST_SNAPSHOT}")

DASHBOARD_DB.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(LATEST_SNAPSHOT, DASHBOARD_DB)
print(f"Copied {LATEST_SNAPSHOT} to {DASHBOARD_DB}")
