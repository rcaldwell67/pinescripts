import csv
import json
import os

# Map CSV file(s) to symbol/version
TRADE_FILES = [
    {
        'csv': 'apm_v1_trades.csv',
        'symbol': 'BTC_USD',
        'version': 'v1',
    },
    # Add more trade files here if needed
]

output = {}

for entry in TRADE_FILES:
    csv_path = entry['csv']
    symbol = entry['symbol']
    version = entry['version']
    if not os.path.exists(csv_path):
        print(f"Warning: {csv_path} not found, skipping.")
        continue
    with open(csv_path, newline='') as f:
        reader = csv.DictReader(f)
        trades = []
        for row in reader:
            # Convert numeric fields
            for k in row:
                try:
                    if row[k] == '':
                        row[k] = None
                    elif '.' in row[k] or 'e' in row[k].lower():
                        row[k] = float(row[k])
                    else:
                        row[k] = int(row[k])
                except Exception:
                    pass
            trades.append(row)
        if symbol not in output:
            output[symbol] = {}
        output[symbol][version] = trades

with open('docs/data/backtest_results.json', 'w') as f:
    json.dump(output, f, indent=2)

print('Exported backtest_results.json with full trade arrays.')
