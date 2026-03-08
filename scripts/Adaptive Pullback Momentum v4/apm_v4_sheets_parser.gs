/**
 * APM v4.1 — Google Apps Script
 * ==============================
 * Polls Gmail every 1 minute for TradingView alert emails from APM v4.1
 * (BTC-USD 1D, longs & shorts) and appends parsed rows to the
 * "Live Alerts v4" sheet in:
 * https://docs.google.com/spreadsheets/d/19wjt8sWl1PddkwYbk8NgXEzoZSo6dVbec3pUdAk3-n8
 *
 * SETUP (one-time):
 *   1. Copy this file into a new Apps Script project bound to the Sheet:
 *      Extensions → Apps Script → paste code → Save
 *   2. In TradingView, set each alert's Message exactly as the Pine Script
 *      alert() calls produce (multi-line format with "APM v4.1 | ... |" prefix).
 *   3. Run setupTrigger() once from the Apps Script editor to install the
 *      1-minute polling trigger.
 *   4. Create a Gmail label named "apm-v4-processed" (Gmail → Settings →
 *      Labels → Create new label).
 *   5. Run processAlertEmails() manually once to confirm it works.
 *
 * Alert types parsed:
 *   LONG/SHORT ENTRY, TRAIL STOP ACTIVATED, LONG/SHORT EXIT [WIN/LOSS],
 *   PANIC REGIME STARTED, PANIC REGIME CLEARED
 *
 * Note: v4.1 has no ATR floor and no EMA slope filter; those columns are
 * left blank in the sheet.
 */

var SPREADSHEET_ID   = "19wjt8sWl1PddkwYbk8NgXEzoZSo6dVbec3pUdAk3-n8";
var LIVE_SHEET_NAME  = "Live Alerts v4";
var PROCESSED_LABEL  = "apm-v4-processed";
var GMAIL_QUERY      = 'from:noreply@tradingview.com subject:"APM v4.1" -label:' + PROCESSED_LABEL;

var LIVE_HEADERS = [
  "Received At", "Symbol", "Timeframe", "Alert Type", "Direction",
  // Entry fields
  "Entry", "Stop", "Target", "R:R", "Risk ($)", "Qty",
  "ATR", "ATR %", "ATR Floor",
  "RSI", "RSI Range", "RSI Dir",
  "ADX", "DI+", "DI-",
  "Vol/MA", "Body (x ATR)",
  "EMA Fast", "EMA Mid", "EMA Slow",
  "Trail Activate ($)", "Trail Dist ($)",
  // Trail fields
  "Best Price", "New SL", "Prev SL", "Runup ($)", "Runup %",
  // Exit fields
  "Exit Price", "Move %", "P&L ($)", "Comm ($)", "Max Runup", "Bars",
  "Equity", "Closed Trades", "Win Rate",
  // Panic fields
  "ATR Value", "ATR Baseline", "ATR Ratio",
  // Raw
  "Raw Message",
  // ID
  "Message ID"
];

// ── Entry point ───────────────────────────────────────────────────────────────
function processAlertEmails() {
  var ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  var ws = getOrCreateSheet(ss, LIVE_SHEET_NAME, LIVE_HEADERS);
  var label = getOrCreateLabel(PROCESSED_LABEL);

  // Get existing message IDs to prevent duplicates
  var lastRow = ws.getLastRow();
  var existingIds = lastRow > 1
    ? ws.getRange(2, LIVE_HEADERS.indexOf("Message ID") + 1, lastRow - 1, 1).getValues().flat()
    : [];

  var threads = GmailApp.search(GMAIL_QUERY, 0, 50);
  if (threads.length === 0) return;

  var rows = [];
  for (var i = 0; i < threads.length; i++) {
    var msgs = threads[i].getMessages();
    for (var j = 0; j < msgs.length; j++) {
      var msg = msgs[j];
      var msgId = msg.getId();

      // Skip if the message ID already exists in the sheet
      if (existingIds.indexOf(msgId) > -1) {
        Logger.log("Skipping duplicate message ID: " + msgId);
        continue;
      }

      var body = msg.getPlainBody();
      var date = msg.getDate();
      var row = parseAlertBody(body, date, msgId);
      if (row) {
        rows.push(row);
        existingIds.push(msgId); // Add to local list to handle multiple new messages in one run
      }
    }
    threads[i].addLabel(label);
  }

  if (rows.length > 0) {
    ws.getRange(ws.getLastRow() + 1, 1, rows.length, LIVE_HEADERS.length)
      .setValues(rows);
    Logger.log("Appended " + rows.length + " alert rows.");
  }
}

// ── Alert parser ──────────────────────────────────────────────────────────────
function parseAlertBody(body, date, msgId) {
  // Normalise line endings
  body = body.replace(/\r\n/g, "\n").replace(/\r/g, "\n").trim();

  var lines = body.split("\n");
  if (lines.length < 2) return null;

  var header = lines[0].trim();
  if (header.indexOf("APM v4.1") === -1) return null;

  // Build key→value map from "Key   : Value" lines
  var kv = {};
  for (var i = 1; i < lines.length; i++) {
    var idx = lines[i].indexOf(":");
    if (idx > 0) {
      var k = lines[i].substring(0, idx).trim();
      var v = lines[i].substring(idx + 1).trim();
      kv[k] = v;
    }
  }

  // Determine type from header
  var atype     = "";
  var direction = "";
  if (header.indexOf("LONG ENTRY") > -1)          { atype = "ENTRY";       direction = "LONG";  }
  else if (header.indexOf("SHORT ENTRY") > -1)     { atype = "ENTRY";       direction = "SHORT"; }
  else if (header.indexOf("TRAIL STOP") > -1)      { atype = "TRAIL";
    direction = body.indexOf("Direction : LONG") > -1 ? "LONG" : "SHORT";  }
  else if (header.indexOf("LONG EXIT") > -1)       { atype = "EXIT";        direction = "LONG";  }
  else if (header.indexOf("SHORT EXIT") > -1)      { atype = "EXIT";        direction = "SHORT"; }
  else if (header.indexOf("PANIC REGIME STARTED") > -1) { atype = "PANIC_START"; }
  else if (header.indexOf("PANIC REGIME CLEARED") > -1) { atype = "PANIC_CLEAR";  }
  else return null;

  // ── Parse symbol / timeframe from header
  // Header format: "APM v4.1 | SHORT ENTRY | BTC-USD [1D]"
  var symParts = header.split("|");
  var symRaw   = symParts.length >= 3 ? symParts[2].trim() : "";
  var symbol   = symRaw.split("[")[0].trim();
  var tf       = symRaw.indexOf("[") > -1
               ? symRaw.split("[")[1].replace("]","").trim()
               : "";

  var recvAt  = Utilities.formatDate(date, Session.getScriptTimeZone(), "yyyy-MM-dd HH:mm:ss");

  // ── Shared helpers
  function splitFirst(s, delim) {
    var idx = s.indexOf(delim);
    return idx >= 0 ? [s.substring(0, idx).trim(), s.substring(idx + delim.length).trim()] : [s.trim(), ""];
  }
  function extractBetween(s, open, close) {
    var a = s.indexOf(open), b = s.indexOf(close, a);
    return (a >= 0 && b > a) ? s.substring(a + open.length, b).trim() : "";
  }

  // ── Build the full row (matches LIVE_HEADERS order)
  var entry="", stop="", target="", rr="", risk="", qty="";
  var atr_v="", atr_pct="", atr_floor="";
  var rsi_v="", rsi_range="", rsi_dir="";
  var adx_v="", dip="", dim="";
  var vol_v="", body_v="";
  var ema_f="", ema_m="", ema_s="";
  var trail_act="", trail_dist="";
  var best="", new_sl="", prev_sl="", runup_d="", runup_pct="";
  var exit_p="", move_pct="", pnl_d="", comm_d="", max_runup="", bars="";
  var eq_v="", closed_v="", wr_v="";
  var atr_val="", atr_bl="", atr_ratio="";

  if (atype === "ENTRY") {
    var entryRaw = kv["Entry"] || "";
    entry  = entryRaw.indexOf("|") > -1 ? entryRaw.split("|")[0].trim() : entryRaw;
    stop   = (kv["Stop"]   || "").split("(")[0].trim();
    target = (kv["Target"] || "").split("(")[0].trim();

    var rrRaw = kv["R:R"] || "";
    rr   = rrRaw.indexOf("|") > -1 ? rrRaw.split("|")[0].trim() : rrRaw;
    risk = rrRaw.indexOf("Risk: $") > -1 ? rrRaw.split("Risk: $")[1].split(" ")[0] : "";
    qty  = kv["Qty"] || "";

    var atrRaw = kv["ATR"] || "";
    atr_v     = atrRaw.split(" ")[0];
    atr_pct   = extractBetween(atrRaw, "(", "%");
    // v4 has no ATR floor
    atr_floor = "";

    var rsiRaw = kv["RSI"] || "";
    rsi_v     = rsiRaw.split(" ")[0];
    rsi_range = extractBetween(rsiRaw, "[", "]");
    rsi_dir   = rsiRaw.indexOf("Dir:") > -1 ? rsiRaw.split("Dir:")[1].trim() : "";

    var adxRaw = kv["ADX"] || "";
    adx_v = adxRaw.split(" ")[0];
    dip   = adxRaw.indexOf("DI+:") > -1 ? adxRaw.split("DI+:")[1].split(" ")[0].trim() : "";
    dim   = adxRaw.indexOf("DI-:") > -1 ? adxRaw.split("DI-:")[1].split(" ")[0].trim() : "";

    vol_v  = (kv["Vol/MA"] || "").replace("x","").trim();
    body_v = (kv["Body"]   || "").split("x")[0].trim();

    // EMA line: "EMA21/50/200: val/val/val  Stack: ..."
    var emaLine = "";
    for (var li = 0; li < lines.length; li++) {
      if (lines[li].indexOf("Stack:") > -1) { emaLine = lines[li]; break; }
    }
    if (emaLine) {
      var emaVals = emaLine.split(":")[1].trim().split("  ")[0].split("/");
      if (emaVals.length === 3) { ema_f = emaVals[0]; ema_m = emaVals[1]; ema_s = emaVals[2]; }
    }

    var trailRaw = kv["Trail on"] || "";
    trail_act  = trailRaw.split("(")[0].replace(/[+\-]/g,"").trim();
    trail_dist = trailRaw.indexOf("Dist:") > -1 ? trailRaw.split("Dist:")[1].split("(")[0].trim() : "";
  }

  else if (atype === "TRAIL") {
    var bestRaw   = kv["Best price"] || "";
    best    = bestRaw.indexOf("|") > -1 ? bestRaw.split("|")[0].trim() : bestRaw;
    var trailSlRaw = kv["Trail SL"] || "";
    new_sl  = trailSlRaw.split("(")[0].trim();
    var prevSlRaw = kv["Prev SL"] || "";
    prev_sl = prevSlRaw.indexOf("|") > -1 ? prevSlRaw.split("|")[0].trim() : prevSlRaw;

    var runupRaw = kv["Runup"] || "";
    runup_d   = runupRaw.split(" ")[0].replace(/[+\-]/g,"");
    runup_pct = extractBetween(runupRaw, "(", "%");
  }

  else if (atype === "EXIT") {
    var epxpRaw = kv["Entry"] || "";
    var epxp    = epxpRaw.indexOf("->") > -1 ? epxpRaw.split("->") : [epxpRaw, ""];
    entry   = epxp[0].trim();
    exit_p  = epxp[1].trim();
    move_pct = (kv["Move"]  || "").replace("%","").trim();
    pnl_d    = (kv["P&L"]   || "").replace(" USD","").trim();
    comm_d   = (kv["Comm"]  || "").replace(" USD","").replace("-","").trim();
    max_runup= kv["Max runup"] || "";
    bars     = kv["Bars"] || "";
    eq_v     = (kv["Equity"] || "").replace("$","").trim();
    var trRaw = kv["Trades"] || "";
    closed_v = trRaw.indexOf("|") > -1 ? trRaw.split("|")[0].trim() : trRaw;
    wr_v     = trRaw.indexOf("Win rate:") > -1 ? trRaw.split("Win rate:")[1].trim() : "";
  }

  else if (atype === "PANIC_START" || atype === "PANIC_CLEAR") {
    var atrPanicRaw = kv["ATR"] || "";
    atr_val = atrPanicRaw.indexOf("|") > -1 ? atrPanicRaw.split("|")[0].trim() : atrPanicRaw;
    atr_bl  = atrPanicRaw.indexOf("ATR baseline:") > -1
              ? atrPanicRaw.split("ATR baseline:")[1].trim() : "";
    atr_ratio = (kv["Ratio"] || "").split("x")[0].trim();
  }

  return [
    recvAt, symbol, tf, atype, direction,
    entry, stop, target, rr, risk, qty,
    atr_v, atr_pct, atr_floor,
    rsi_v, rsi_range, rsi_dir,
    adx_v, dip, dim,
    vol_v, body_v,
    ema_f, ema_m, ema_s,
    trail_act, trail_dist,
    best, new_sl, prev_sl, runup_d, runup_pct,
    exit_p, move_pct, pnl_d, comm_d, max_runup, bars,
    eq_v, closed_v, wr_v,
    atr_val, atr_bl, atr_ratio,
    body,
    msgId
  ];
}

// ── Utilities ─────────────────────────────────────────────────────────────────
function getOrCreateSheet(ss, name, headers) {
  var ws = ss.getSheetByName(name);
  if (!ws) {
    ws = ss.insertSheet(name);
    ws.appendRow(headers);
    ws.setFrozenRows(1);
    // Basic formatting: bold header, freeze
    ws.getRange(1, 1, 1, headers.length)
      .setFontWeight("bold")
      .setBackground("#1a1a2e")
      .setFontColor("#e2e8f0");
  }
  return ws;
}

function getOrCreateLabel(name) {
  var labels = GmailApp.getUserLabels();
  for (var i = 0; i < labels.length; i++) {
    if (labels[i].getName() === name) return labels[i];
  }
  return GmailApp.createLabel(name);
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

/** Utility: manually run once to test parsing against existing emails. */
function testParse() {
  var threads = GmailApp.search('from:noreply@tradingview.com subject:"APM v4.1"', 0, 3);
  for (var i = 0; i < threads.length; i++) {
    var msgs = threads[i].getMessages();
    for (var j = 0; j < msgs.length; j++) {
      var msg = msgs[j];
      var row = parseAlertBody(msg.getPlainBody(), msg.getDate(), "test-id-" + i + "-" + j);
      Logger.log(JSON.stringify(row));
    }
  }
}
