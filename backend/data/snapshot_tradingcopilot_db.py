import shutil
import os
from datetime import datetime

def snapshot_db():
    src = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../frontend-react/public/data/tradingcopilot.db'))
    backup_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../db_snapshots'))
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    dst = os.path.join(backup_dir, f'tradingcopilot_{timestamp}.db')
    shutil.copy2(src, dst)
    print(f"Snapshot created: {dst}")

if __name__ == '__main__':
    snapshot_db()
