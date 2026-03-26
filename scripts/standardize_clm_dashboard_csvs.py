import os
import pandas as pd

# Directory containing CLM dashboard CSVs
CLM_DIR = os.path.join('docs', 'data', 'clm')
# List of CLM v1–v6 CSV filenames
CLM_CSVS = [f'v{i}_trades.csv' for i in range(1, 7)]

# Canonical header (from BTCUSD/dashboard standard)
CANONICAL_HEADER = [
    'entry_time', 'exit_time', 'direction', 'entry', 'exit',
    'result', 'pnl_pct', 'dollar_pnl', 'equity'
]

def standardize_csv(filepath):
    try:
        df = pd.read_csv(filepath)
        # Map possible alternative column names to canonical
        col_map = {
            'pnl': 'dollar_pnl',
            'pnl_pct': 'pnl_pct',
            'dollar_pnl': 'dollar_pnl',
            'result': 'result',
            'exit_reason': 'result',
            'max_runup': None, 'bars': None, 'year': None  # drop extra cols
        }
        # Build new columns in canonical order, fill missing with empty/NaN
        new_cols = {}
        for col in CANONICAL_HEADER:
            if col in df.columns:
                new_cols[col] = df[col]
            else:
                # Try to map alternative names
                alt = [k for k, v in col_map.items() if v == col and k in df.columns]
                if alt:
                    new_cols[col] = df[alt[0]]
                else:
                    new_cols[col] = pd.NA
        new_df = pd.DataFrame(new_cols)
        new_df.to_csv(filepath, index=False)
        print(f'Standardized: {filepath}')
    except Exception as e:
        print(f'Error processing {filepath}: {e}')

if __name__ == '__main__':
    for fname in CLM_CSVS:
        fpath = os.path.join(CLM_DIR, fname)
        if os.path.exists(fpath):
            standardize_csv(fpath)
        else:
            print(f'Skipped missing: {fpath}')
