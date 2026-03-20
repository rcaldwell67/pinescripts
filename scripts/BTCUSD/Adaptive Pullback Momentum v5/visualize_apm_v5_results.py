import pandas as pd
import matplotlib.pyplot as plt

# Load trade log
csv_path = "scripts/BTCUSD/Adaptive Pullback Momentum v5/apm_v5_trades_btcusd_1h.csv"
df = pd.read_csv(csv_path, parse_dates=["entry_time", "exit_time"])

# Plot equity curve
plt.figure(figsize=(10, 6))
plt.plot(df["exit_time"], df["equity"], marker="o", label="Equity Curve")
plt.title("APM v5 BTCUSD 1h Paper Trading — Equity Curve")
plt.xlabel("Exit Time")
plt.ylabel("Equity ($)")
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.savefig("scripts/BTCUSD/Adaptive Pullback Momentum v5/apm_v5_equity_curve.png")
plt.show()

# Plot P&L per trade
plt.figure(figsize=(10, 4))
plt.bar(df["exit_time"], df["pnl"], color=["green" if x > 0 else "red" for x in df["pnl"]])
plt.title("APM v5 BTCUSD 1h Paper Trading — P&L per Trade")
plt.xlabel("Exit Time")
plt.ylabel("P&L ($)")
plt.grid(True)
plt.tight_layout()
plt.savefig("scripts/BTCUSD/Adaptive Pullback Momentum v5/apm_v5_pnl_per_trade.png")
plt.show()
