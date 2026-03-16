"""
APM v3.3  — Push backtest results to Google Sheets
====================================================
Sheet: https://docs.google.com/spreadsheets/d/19wjt8sWl1PddkwYbk8NgXEzoZSo6dVbec3pUdAk3-n8

SETUP (one-time):
  1. Go to https://console.cloud.google.com → New Project
  2. Enable "Google Sheets API" for the project
  3. Create a Service Account → generate JSON key → save as:
       scripts/Adaptive Pullback Momentum v3/service_account.json
  4. Copy the service account email (e.g. apm-bot@your-project.iam.gserviceaccount.com)
  5. Open the Google Sheet → Share → paste the service account email → Editor
  6. pip install gspread
"""

import subprocess, sys
for pkg in ["gspread", "google-auth"]:
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])

import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone

# ── Config ─────────────────────────────────────────────────────────────────────
SPREADSHEET_ID  = "19wjt8sWl1PddkwYbk8NgXEzoZSo6dVbec3pUdAk3-n8"
TRADES_SHEET    = "Trades"        # tab name for trade-level data
ALERTS_SHEET    = "Alerts"        # tab name for all alert events
SUMMARY_SHEET   = "Summary"       # tab name for run-level summary

# Path to service account JSON key (relative to this script)
SA_KEY = Path(__file__).parent / "service_account.json"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

# ── Auth ───────────────────────────────────────────────────────────────────────
def connect():
    if not SA_KEY.exists():
        raise FileNotFoundError(
            f"Service account key not found at {SA_KEY}\n"
            "See SETUP instructions at top of this file."
        )
    creds = Credentials.from_service_account_file(str(SA_KEY), scopes=SCOPES)
    gc    = gspread.authorize(creds)
    return gc.open_by_key(SPREADSHEET_ID)


def get_or_create_sheet(wb, name, headers):
    """Return worksheet, creating it with a header row if it doesn't exist."""
    try:
        ws = wb.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = wb.add_worksheet(title=name, rows=5000, cols=len(headers))
        ws.append_row(headers, value_input_option="USER_ENTERED")
        # Freeze header row
        ws.freeze(rows=1)
    return ws


def ensure_header(ws, headers):
    """If sheet is empty or header is missing, write it."""
    existing = ws.row_values(1)
    if existing != headers:
        ws.clear()
        ws.append_row(headers, value_input_option="USER_ENTERED")
        ws.freeze(rows=1)


# ── Sheet definitions ──────────────────────────────────────────────────────────
TRADES_HEADERS = [
    "Run Timestamp", "Symbol", "Timeframe",
    "Entry Time", "Exit Time", "Direction",
    "Entry Price", "Exit Price", "Result",
    "P&L ($)", "Commission ($)", "Max Runup",
    "Bars Held", "PnL %", "Equity After",
]

ALERTS_HEADERS = [
    "Run Timestamp", "Symbol", "Timeframe",
    "Alert Time", "Alert Type", "Direction",
    "Entry", "Stop", "Target", "R:R",
    "Risk ($)", "Qty",
    "ATR", "ATR %", "ATR Floor",
    "RSI", "RSI Range", "RSI Dir",
    "ADX", "DI+", "DI-",
    "Vol/MA", "Body (x ATR)",
    "EMA Fast", "EMA Mid", "EMA Slow",
    "Trail Activate ($)", "Trail Dist ($)",
    "Best Price", "New SL", "Previous SL", "Runup ($)", "Runup %",
    "Exit Entry", "Exit Price", "Move %", "P&L ($)", "Comm ($)",
    "Max Runup", "Bars", "Equity", "Closed Trades", "Win Rate",
    "ATR Value", "ATR Baseline", "ATR Ratio",
    "Raw Message",
]

SUMMARY_HEADERS = [
    "Run Timestamp", "Symbol", "Timeframe", "Period",
    "Initial Capital ($)", "Final Equity ($)", "Net P&L ($)", "Return %",
    "Max Drawdown %", "Profit Factor",
    "Total Trades", "Long Trades", "Short Trades",
    "TP Exits", "SL Exits", "Win Rate %",
    "Total Alerts", "Entry Alerts", "Trail Alerts",
    "Exit Alerts", "Panic Start", "Panic Clear",
]


# ── Parsers for the structured alert list produced by backtest_apm_v3.py ───────
def parse_alerts(alerts, run_ts, symbol, interval):
    """
    `alerts` is the list of (ts, atype, msg) tuples from the backtest loop.
    Returns a list of rows matching ALERTS_HEADERS.
    """
    rows = []
    for ts, atype, msg in alerts:
        lines = {l.split(":")[0].strip(): ":".join(l.split(":")[1:]).strip()
                 for l in msg.splitlines() if ":" in l}

        base = [str(run_ts), symbol, interval, str(ts), atype]

        if atype == "ENTRY":
            direction = "LONG" if "LONG ENTRY" in msg else "SHORT"
            entry_v   = lines.get("Entry", "").split("|")[0].strip()
            equity_v  = lines.get("Entry", "").split("Equity: $")[-1].strip() if "Equity" in lines.get("Entry","") else ""
            stop_v    = lines.get("Stop", "").split("(")[0].strip()
            target_v  = lines.get("Target", "").split("(")[0].strip()
            rr_v      = lines.get("R:R", "").split("|")[0].strip()
            risk_v    = lines.get("R:R", "").split("Risk: $")[-1].split(" ")[0] if "Risk" in lines.get("R:R","") else ""
            qty_v     = lines.get("Qty", "")
            atr_raw   = lines.get("ATR", "")
            atr_v     = atr_raw.split(" ")[0] if atr_raw else ""
            atr_pct   = atr_raw.split("(")[-1].split("%")[0] if "(" in atr_raw else ""
            atr_floor = "OK" if "Floor: OK" in atr_raw else "FAIL"
            rsi_raw   = lines.get("RSI", "")
            rsi_v     = rsi_raw.split(" ")[0] if rsi_raw else ""
            rsi_range = rsi_raw.split("[")[-1].split("]")[0] if "[" in rsi_raw else ""
            rsi_dir   = rsi_raw.split("Dir:")[-1].strip() if "Dir:" in rsi_raw else ""
            adx_raw   = lines.get("ADX", "")
            adx_v     = adx_raw.split(" ")[0] if adx_raw else ""
            dip       = adx_raw.split("DI+:")[-1].split(" ")[0].strip() if "DI+" in adx_raw else ""
            dim       = adx_raw.split("DI-:")[-1].split(" ")[0].strip() if "DI-" in adx_raw else ""
            vol_raw   = lines.get("Vol/MA", "")
            vol_v     = vol_raw.split("x")[0].strip() if vol_raw else ""
            body_raw  = lines.get("Body", "")
            body_v    = body_raw.split("x")[0].strip() if body_raw else ""
            ema_raw   = [l for l in msg.splitlines() if "Stack:" in l]
            ema_f = ema_m = ema_s = ""
            if ema_raw:
                ema_part = ema_raw[0].split(": ")[-1].split("  ")[0]
                parts = ema_part.split("/")
                if len(parts) == 3:
                    ema_f, ema_m, ema_s = parts
            trail_raw = lines.get("Trail on", "")
            trail_act_v  = trail_raw.split("(")[0].replace("-","").replace("+","").strip() if trail_raw else ""
            trail_dist_v = trail_raw.split("Dist:")[-1].split("(")[0].strip() if "Dist:" in trail_raw else ""
            rows.append(base + [
                direction, entry_v, stop_v, target_v, rr_v,
                risk_v, qty_v,
                atr_v, atr_pct, atr_floor,
                rsi_v, rsi_range, rsi_dir,
                adx_v, dip, dim,
                vol_v, body_v,
                ema_f, ema_m, ema_s,
                trail_act_v, trail_dist_v,
                "", "", "", "", "",        # trail fields
                "", "", "", "", "", "", "", "", "", "", "",  # exit fields
                "", "", "",                 # panic fields
                msg,
            ])

        elif atype == "TRAIL":
            direction = "LONG" if "Direction : LONG" in msg else "SHORT"
            best_raw  = lines.get("Best price", "")
            best_v    = best_raw.split("|")[0].strip() if best_raw else ""
            entry_v   = best_raw.split("Entry:")[-1].strip() if "Entry:" in best_raw else ""
            trail_sl  = lines.get("Trail SL", "").split("(")[0].strip()
            prev_sl   = lines.get("Prev SL", "").split("|")[0].strip()
            target_v  = lines.get("Prev SL", "").split("Target:")[-1].strip() if "Target:" in lines.get("Prev SL","") else ""
            runup_raw = lines.get("Runup", "")
            runup_v   = runup_raw.split(" ")[0].replace("-","").replace("+","") if runup_raw else ""
            runup_pct = runup_raw.split("(")[-1].replace("%","").replace(")","").strip() if "(" in runup_raw else ""
            rows.append(base + [
                direction, entry_v, "", target_v, "", "", "",
                "", "", "",
                "", "", "",
                "", "", "",
                "", "",
                "", "", "",
                "", "",
                best_v, trail_sl, prev_sl, runup_v, runup_pct,
                "", "", "", "", "", "", "", "", "", "",
                "", "", "",
                msg,
            ])

        elif atype == "EXIT":
            direction = "LONG" if "LONG EXIT" in msg else "SHORT"
            ep_xp     = lines.get("Entry", "")
            ep_v      = ep_xp.split("->")[0].strip() if "->" in ep_xp else ep_xp
            xp_v      = ep_xp.split("->")[-1].strip() if "->" in ep_xp else ""
            move_v    = lines.get("Move", "").replace("%","").strip()
            pnl_v     = lines.get("P&L", "").replace(" USD","").strip()
            comm_v    = lines.get("Comm", "").replace(" USD","").replace("-","").strip()
            runup_v   = lines.get("Max runup", "")
            bars_v    = lines.get("Bars", "")
            eq_v      = lines.get("Equity", "").replace("$","").strip()
            tr_raw    = lines.get("Trades", "")
            tr_v      = tr_raw.split("|")[0].strip() if tr_raw else ""
            wr_v      = tr_raw.split("Win rate:")[-1].strip() if "Win rate:" in tr_raw else ""
            rows.append(base + [
                direction, ep_v, "", "", "", "", "",
                "", "", "",
                "", "", "",
                "", "", "",
                "", "",
                "", "", "",
                "", "",
                "", "", "", "", "",
                ep_v, xp_v, move_v, pnl_v, comm_v, runup_v, bars_v, eq_v, tr_v, wr_v,
                "", "", "",
                msg,
            ])

        elif atype in ("PANIC_START", "PANIC_CLEAR"):
            atr_raw = lines.get("ATR", "")
            atr_v   = atr_raw.split("|")[0].strip() if atr_raw else ""
            atr_bl  = atr_raw.split("ATR baseline:")[-1].strip() if "ATR baseline:" in atr_raw else ""
            ratio   = lines.get("Ratio", "").split("x")[0].strip()
            rows.append(base + [
                "", "", "", "", "", "", "",
                "", "", "",
                "", "", "",
                "", "", "",
                "", "",
                "", "", "",
                "", "",
                "", "", "", "", "",
                "", "", "", "", "", "", "", "", "", "",
                atr_v, atr_bl, ratio,
                msg,
            ])

    return rows


def parse_trades(trades, run_ts, symbol, interval):
    rows = []
    for t in trades:
        rows.append([
            str(run_ts), symbol, interval,
            str(t.get("entry_time", "")),
            str(t.get("exit_time", "")),
            t.get("direction", "").upper(),
            t.get("entry_price", ""),
            t.get("exit_price", ""),
            t.get("result", ""),
            t.get("dollar_pnl", ""),
            "",                              # commission not stored in original trades dict
            "",                              # max runup not stored in original trades dict
            "",                              # bars not stored in original trades dict
            t.get("pnl_pct", ""),
            t.get("equity", ""),
        ])
    return rows


def build_summary_row(run_ts, symbol, interval, period, initial_cap, equity,
                      tdf, alerts):
    if tdf.empty:
        ret = pf = wr = 0.0
        mdd = 0.0
        n_longs = n_shorts = n_tp = n_sl = 0
    else:
        wins   = tdf[tdf["dollar_pnl"] > 0]
        losses = tdf[tdf["dollar_pnl"] <= 0]
        wr     = len(wins) / len(tdf) * 100
        ret    = (equity / initial_cap - 1) * 100
        pf     = (wins["dollar_pnl"].sum() / abs(losses["dollar_pnl"].sum())
                  if not losses.empty and losses["dollar_pnl"].sum() != 0 else 0)
        pk = initial_cap; mdd = 0.0
        for e in tdf["equity"]:
            if e > pk: pk = e
            dd = (e - pk) / pk * 100
            if dd < mdd: mdd = dd
        n_longs  = (tdf["direction"] == "long").sum()
        n_shorts = (tdf["direction"] == "short").sum()
        n_tp     = (tdf["result"] == "TP").sum()
        n_sl     = (tdf["result"] == "SL").sum()

    type_counts = {}
    for _, atype, _ in alerts:
        type_counts[atype] = type_counts.get(atype, 0) + 1

    return [[
        str(run_ts), symbol, interval, period,
        round(initial_cap, 2), round(equity, 2),
        round(equity - initial_cap, 2), round(ret, 2),
        round(mdd, 2), round(pf, 3),
        len(tdf), int(n_longs), int(n_shorts),
        int(n_tp), int(n_sl), round(wr, 1),
        len(alerts),
        type_counts.get("ENTRY", 0),
        type_counts.get("TRAIL", 0),
        type_counts.get("EXIT", 0),
        type_counts.get("PANIC_START", 0),
        type_counts.get("PANIC_CLEAR", 0),
    ]]


# ── Main push function ─────────────────────────────────────────────────────────
def push_results(trades, alerts, symbol, interval, period,
                 initial_cap, final_equity):
    """
    Call this from backtest_apm_v3.py after the simulation loop.

    trades  : list of trade dicts (same structure backtest already builds)
    alerts  : list of (ts, atype, msg) tuples
    """
    import pandas as pd
    tdf     = pd.DataFrame(trades)
    run_ts  = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    print("\nConnecting to Google Sheets...")
    wb = connect()

    # ── Trades sheet ──────────────────────────────────────────────────────────
    ws_trades = get_or_create_sheet(wb, TRADES_SHEET, TRADES_HEADERS)
    ensure_header(ws_trades, TRADES_HEADERS)
    trade_rows = parse_trades(trades, run_ts, symbol, interval)
    if trade_rows:
        ws_trades.append_rows(trade_rows, value_input_option="USER_ENTERED")
        print(f"  Trades   → {len(trade_rows)} rows appended to '{TRADES_SHEET}'")

    # ── Alerts sheet ──────────────────────────────────────────────────────────
    ws_alerts = get_or_create_sheet(wb, ALERTS_SHEET, ALERTS_HEADERS)
    ensure_header(ws_alerts, ALERTS_HEADERS)
    alert_rows = parse_alerts(alerts, run_ts, symbol, interval)
    if alert_rows:
        ws_alerts.append_rows(alert_rows, value_input_option="USER_ENTERED")
        print(f"  Alerts   → {len(alert_rows)} rows appended to '{ALERTS_SHEET}'")

    # ── Summary sheet ─────────────────────────────────────────────────────────
    ws_summary = get_or_create_sheet(wb, SUMMARY_SHEET, SUMMARY_HEADERS)
    ensure_header(ws_summary, SUMMARY_HEADERS)
    summary_row = build_summary_row(run_ts, symbol, interval, period,
                                    initial_cap, final_equity, tdf, alerts)
    ws_summary.append_rows(summary_row, value_input_option="USER_ENTERED")
    print(f"  Summary  → 1 row appended to '{SUMMARY_SHEET}'")

    sheet_url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}"
    print(f"\nDone → {sheet_url}")


# ── Standalone: push last backtest run from saved CSV + alert txt ──────────────
if __name__ == "__main__":
    import ast
    from pathlib import Path

    HERE     = Path(__file__).parent
    CSV_FILE = HERE / "apm_v3_trades_btcusd_15m.csv"
    TXT_FILE = HERE / "apm_v3_alerts_btcusd_15m.txt"

    if not CSV_FILE.exists():
        print(f"Run backtest_apm_v3.py first to generate {CSV_FILE.name}")
        sys.exit(1)

    tdf    = pd.read_csv(CSV_FILE)
    trades = tdf.to_dict(orient="records")

    # Re-build alerts list from the text log (type is inferred from content)
    alerts = []
    SEP = "-" * 70
    if TXT_FILE.exists():
        raw = TXT_FILE.read_text()
        blocks = [b.strip() for b in raw.split(SEP) if b.strip()]
        for block in blocks:
            first = block.splitlines()[0]
            # extract timestamp from "Time    : ..." line
            ts_line = [l for l in block.splitlines() if l.startswith("Time")]
            ts = ts_line[0].split(":", 1)[-1].strip() if ts_line else ""
            if "LONG ENTRY" in first or "SHORT ENTRY" in first:
                atype = "ENTRY"
            elif "TRAIL STOP" in first:
                atype = "TRAIL"
            elif "EXIT" in first:
                atype = "EXIT"
            elif "PANIC REGIME STARTED" in first:
                atype = "PANIC_START"
            elif "PANIC REGIME CLEARED" in first:
                atype = "PANIC_CLEAR"
            else:
                continue
            alerts.append((ts, atype, block))

    equity = tdf["equity"].iloc[-1] if not tdf.empty else 10_000.0

    push_results(
        trades      = trades,
        alerts      = alerts,
        symbol      = "BTC-USD",
        interval    = "15m",
        period      = "max",
        initial_cap = 10_000.0,
        final_equity= float(equity),
    )
