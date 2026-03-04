/**
 * APM v3.1 — Google Apps Script
 * ==============================
 * Polls Gmail every 1 minute for TradingView alert emails from APM v3.1
 * (BTC-USD 1h, longs only) and appends parsed rows to the
 * "Live Alerts v3" sheet in:
 * https://docs.google.com/spreadsheets/d/19wjt8sWl1PddkwYbk8NgXEzoZSo6dVbec3pUdAk3-n8
 *
 * SETUP (one-time):
 *   1. Copy this file into a new Apps Script project bound to the Sheet:
 *      Extensions → Apps Script → paste code → Save
 *   2. In TradingView, set each alert's Message exactly as the Pine Script
 *      alert() calls produce (multi-line format with "APM v3.1 | ... |" prefix).
 *   3. Run setupTrigger() once from the Apps Script editor to install the
 *      1-minute polling trigger.
 *   4. Create a Gmail label named "apm-v3-processed" (Gmail → Settings →
 *      Labels → Create new label).
 *   5. Run processAlertEmails() manually once to confirm it works.
 *
 * Alert types parsed:
 *   LONG ENTRY, TRAIL STOP ACTIVATED, LONG EXIT [WIN/LOSS],
 *   PANIC REGIME STARTED, PANIC REGIME CLEARED
 */

var SPREADSHEET_ID   = "19wjt8sWl1PddkwYbk8NgXEzoZSo6dVbec3pUdAk3-n8";
var LIVE_SHEET_NAME  = "Live Alerts v3";
var PROCESSED_LABEL  = "apm-v3-processed";
var GMAIL_QUERY      = 'from:noreply@tradingview.com subject:"APM v3.1" -label:' + PROCESSED_LABEL;

var LIVE_HEADERS = [
  "Received At", "Alert Type", "Direction",
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
];

// ── Entry point ───────────────────────────────────────────────────────────────
function processAlertEmails() {
  var threads = GmailApp.search(GMAIL_QUERY, 0, 50);
  if (threads.length === 0) return;

  var ss      = SpreadsheetApp.openById(SPREADSHEET_ID);
  var ws      = getOrCreateSheet(ss);
  var label   = getOrCreateLabel(PROCESSED_LABEL);
  var newRows = [];

  threads.forEach(function(thread) {
    thread.getMessages().forEach(function(msg) {
      var body = msg.getPlainBody();
      var date = msg.getDate();
      var row  = parseAlertBody(body, date);
      if (row) newRows.push(row);
    });
    thread.addLabel(label);
  });

  if (newRows.length > 0) {
    ws.getRange(ws.getLastRow() + 1, 1, newRows.length, LIVE_HEADERS.length)
      .setValues(newRows);
  }
}

// ── Alert parser ──────────────────────────────────────────────────────────────
function parseAlertBody(body, date) {
  var lines = body.trim().split("\n");
  var first = lines[0] || "";

  var kv = {};
  lines.forEach(function(l) {
    var idx = l.indexOf(":");
    if (idx > 0) {
      var k = l.substring(0, idx).trim();
      var v = l.substring(idx + 1).trim();
      kv[k] = v;
    }
  });

  // helpers
  function get(k)      { return (kv[k] || "").trim(); }
  function splitFirst(s, sep) {
    var i = s.indexOf(sep);
    return i < 0 ? [s, ""] : [s.substring(0, i).trim(), s.substring(i + sep.length).trim()];
  }

  var receivedAt = Utilities.formatDate(date, "UTC", "yyyy-MM-dd HH:mm:ss 'UTC'");

  // ── ENTRY ─────────────────────────────────────────────────────────────────
  if (first.indexOf("LONG ENTRY") > -1 || first.indexOf("SHORT ENTRY") > -1) {
    var direction  = first.indexOf("LONG") > -1 ? "LONG" : "SHORT";
    var entryRaw   = get("Entry");
    var entry_v    = splitFirst(entryRaw, "|")[0].replace(/\$$/, "").trim();
    var stop_v     = splitFirst(get("Stop"),   "(")[0].trim();
    var target_v   = splitFirst(get("Target"), "(")[0].trim();
    var rr_raw     = get("R:R");
    var rr_v       = splitFirst(rr_raw, "|")[0].trim();
    var risk_v     = rr_raw.indexOf("Risk: $") > -1 ? rr_raw.split("Risk: $")[1].split(" ")[0] : "";
    var qty_v      = get("Qty");
    var atr_raw    = get("ATR");
    var atr_v      = atr_raw.split(" ")[0];
    var atr_pct    = atr_raw.indexOf("(") > -1 ? atr_raw.split("(")[1].split("%")[0] : "";
    var atr_floor  = atr_raw.indexOf("Floor: OK") > -1 ? "OK" : "FAIL";
    var rsi_raw    = get("RSI");
    var rsi_v      = rsi_raw.split(" ")[0];
    var rsi_range  = rsi_raw.indexOf("[") > -1 ? rsi_raw.split("[")[1].split("]")[0] : "";
    var rsi_dir    = rsi_raw.indexOf("Dir:") > -1 ? rsi_raw.split("Dir:")[1].trim() : "";
    var adx_raw    = get("ADX");
    var adx_v      = adx_raw.split(" ")[0];
    var dip        = adx_raw.indexOf("DI+:") > -1 ? adx_raw.split("DI+:")[1].split(" ")[0] : "";
    var dim        = adx_raw.indexOf("DI-:") > -1 ? adx_raw.split("DI-:")[1].split(" ")[0] : "";
    var vol_v      = get("Vol/MA").replace(/x.*/, "").trim();
    var body_v     = get("Body").replace(/x.*/, "").trim();
    var ema_line   = lines.filter(function(l){ return l.indexOf("Stack:") > -1; })[0] || "";
    var ema_f = "", ema_m = "", ema_s = "";
    if (ema_line) {
      var ep = ema_line.split(": ").pop().split("  ")[0].split("/");
      if (ep.length === 3) { ema_f = ep[0]; ema_m = ep[1]; ema_s = ep[2]; }
    }
    var trail_raw  = get("Trail on");
    var trail_act  = trail_raw.split("(")[0].replace(/[+-]/g, "").trim();
    var trail_dist = trail_raw.indexOf("Dist:") > -1 ? trail_raw.split("Dist:")[1].split("(")[0].trim() : "";

    return [
      receivedAt, "ENTRY", direction,
      entry_v, stop_v, target_v, rr_v, risk_v, qty_v,
      atr_v, atr_pct, atr_floor,
      rsi_v, rsi_range, rsi_dir,
      adx_v, dip, dim,
      vol_v, body_v,
      ema_f, ema_m, ema_s,
      trail_act, trail_dist,
      "", "", "", "", "",
      "", "", "", "", "", "", "", "", "", "",
      "", "", "",
      body,
    ];
  }

  // ── TRAIL STOP ACTIVATED ──────────────────────────────────────────────────
  if (first.indexOf("TRAIL STOP ACTIVATED") > -1) {
    var direction  = first.indexOf("LONG") > -1 ? "LONG" : "SHORT";
    var best_raw   = get("Best price");
    var best_v     = splitFirst(best_raw, "|")[0].trim();
    var entry_v    = best_raw.indexOf("Entry:") > -1 ? best_raw.split("Entry:")[1].trim() : "";
    var tsl_raw    = get("Trail SL");
    var trail_sl   = tsl_raw.split("(")[0].trim();
    var prev_sl_raw= get("Prev SL");
    var prev_sl    = splitFirst(prev_sl_raw, "|")[0].trim();
    var target_v   = prev_sl_raw.indexOf("Target:") > -1 ? prev_sl_raw.split("Target:")[1].trim() : "";
    var runup_raw  = get("Runup");
    var runup_v    = runup_raw.split(" ")[0].replace(/[+-]/g, "");
    var runup_pct  = runup_raw.indexOf("(") > -1 ? runup_raw.split("(")[1].replace("%)","").replace("%","").replace(")","").trim() : "";

    return [
      receivedAt, "TRAIL", direction,
      entry_v, "", target_v, "", "", "",
      "", "", "",
      "", "", "",
      "", "", "",
      "", "",
      "", "", "",
      "", "",
      best_v, trail_sl, prev_sl, runup_v, runup_pct,
      "", "", "", "", "", "", "", "", "", "",
      "", "", "",
      body,
    ];
  }

  // ── EXIT ─────────────────────────────────────────────────────────────────
  if (first.indexOf("EXIT [WIN]") > -1 || first.indexOf("EXIT [LOSS]") > -1) {
    var direction = first.indexOf("LONG") > -1 ? "LONG" : "SHORT";
    var ep_xp     = get("Entry");
    var ep_v      = ep_xp.indexOf("->") > -1 ? ep_xp.split("->")[0].trim() : ep_xp;
    var xp_v      = ep_xp.indexOf("->") > -1 ? ep_xp.split("->")[1].trim() : "";
    var move_v    = get("Move").replace("%","").trim();
    var pnl_v     = get("P&L").replace(" USD","").trim();
    var comm_v    = get("Comm").replace(" USD","").replace("-","").trim();
    var runup_v   = get("Max runup");
    var bars_v    = get("Bars");
    var eq_v      = get("Equity").replace("$","").trim();
    var tr_raw    = get("Trades");
    var tr_v      = tr_raw.indexOf("|") > -1 ? tr_raw.split("|")[0].trim() : tr_raw;
    var wr_v      = tr_raw.indexOf("Win rate:") > -1 ? tr_raw.split("Win rate:")[1].trim() : "";

    return [
      receivedAt, "EXIT", direction,
      ep_v, "", "", "", "", "",
      "", "", "",
      "", "", "",
      "", "", "",
      "", "",
      "", "", "",
      "", "",
      "", "", "", "", "",
      ep_v, xp_v, move_v, pnl_v, comm_v, runup_v, bars_v, eq_v, tr_v, wr_v,
      "", "", "",
      body,
    ];
  }

  // ── PANIC REGIME STARTED / CLEARED ───────────────────────────────────────
  if (first.indexOf("PANIC REGIME STARTED") > -1 || first.indexOf("PANIC REGIME CLEARED") > -1) {
    var atype   = first.indexOf("STARTED") > -1 ? "PANIC_START" : "PANIC_CLEAR";
    var atr_raw = get("ATR");
    var atr_v   = atr_raw.indexOf("|") > -1 ? atr_raw.split("|")[0].trim() : atr_raw;
    var atr_bl  = atr_raw.indexOf("ATR baseline:") > -1 ? atr_raw.split("ATR baseline:")[1].trim() : "";
    var ratio   = get("Ratio").replace(/x.*/, "").trim();

    return [
      receivedAt, atype, "",
      "", "", "", "", "", "",
      "", "", "",
      "", "", "",
      "", "", "",
      "", "",
      "", "", "",
      "", "",
      "", "", "", "", "",
      "", "", "", "", "", "", "", "", "", "",
      atr_v, atr_bl, ratio,
      body,
    ];
  }

  return null;  // unknown alert format
}

// ── Utilities ─────────────────────────────────────────────────────────────────
function getOrCreateSheet(ss) {
  var ws = ss.getSheetByName(LIVE_SHEET_NAME);
  if (!ws) {
    ws = ss.insertSheet(LIVE_SHEET_NAME);
    ws.appendRow(LIVE_HEADERS);
    ws.setFrozenRows(1);
  }
  return ws;
}

function getOrCreateLabel(name) {
  var label = GmailApp.getUserLabelByName(name);
  if (!label) label = GmailApp.createLabel(name);
  return label;
}

// ── Setup / Utilities ─────────────────────────────────────────────────────────
/**
 * Run this ONCE from the Apps Script editor to install the polling trigger.
 * Extensions → Apps Script → Run → setupTrigger
 */
function setupTrigger() {
  // Remove any existing triggers for this function first
  ScriptApp.getProjectTriggers()
    .filter(function(t){ return t.getHandlerFunction() === "processAlertEmails"; })
    .forEach(function(t){ ScriptApp.deleteTrigger(t); });

  ScriptApp.newTrigger("processAlertEmails")
    .timeBased()
    .everyMinutes(1)
    .create();

  Logger.log("Trigger installed: processAlertEmails every 1 minute.");
}

/**
 * Debug helper — paste a sample alert body below and run testParse()
 * to inspect the parsed row in the Apps Script logs.
 */
function testParse() {
  var sample = [
    "APM v3.1 | LONG ENTRY | BTC-USD [1h]",
    "Entry   : 63762.28  |  Equity: $10000.00",
    "Stop    : 63177.08  (-585.20 = ATR x1.5)",
    "Target  : 64347.48  (+585.20 = ATR x1.5)",
    "R:R     : 1:1.00  |  Risk: $100.00 (1.0%)",
    "Qty     : 0.1709",
    "ATR     : 390.13 (0.612% of price)  |  Floor: OK",
    "RSI     : 58.64 [42.0-72.0]  |  Dir: Rising",
    "ADX     : 39.32  DI+: n/a  DI-: n/a  [min 35.0]",
    "Vol/MA  : 11.71x  [min 1.5x]",
    "Body    : 0.939x ATR  [min 0.2x]",
    "EMA21/50/200: 63406.49/62596.59/61936.16  Stack: BULL  Slope: UP",
    "Trail on: +975.33 (ATR x2.5)  Dist: 195.07 (ATR x0.5)",
    "Time    : 2024-05-05 07:00:00+00:00",
  ].join("\n");

  var row = parseAlertBody(sample, new Date());
  Logger.log(row ? JSON.stringify(row) : "Parse returned null");
}
