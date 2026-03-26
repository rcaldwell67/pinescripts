import pandas as pd

def standardize_dashboard_csv(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardize DataFrame columns for dashboard CSV export.
    Ensures canonical order and naming, fills missing columns with NA.
    """
    col_map = {
        'pnl': 'dollar_pnl',
        'dp': 'dollar_pnl',
        'exit_reason': 'result',
        'reason': 'result',
        'dir': 'direction',
        'ts': 'exit_time',
        'entry_price': 'entry',
        'exit_price': 'exit',
    }
    canonical = [
        'entry_time', 'exit_time', 'direction', 'entry', 'exit',
        'result', 'pnl_pct', 'dollar_pnl', 'equity'
    ]
    # Rename columns as needed
    df = df.rename(columns=col_map)
    # Insert missing columns as NA
    for col in canonical:
        if col not in df.columns:
            df[col] = pd.NA
    # Reorder
    return df[canonical]
