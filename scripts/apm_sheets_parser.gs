/**
 * APM — Combined Google Apps Script (v1.0 / v2.2 / v3.0 / v4.0)
 * ==============================================================
 * Single file that polls Gmail every 1 minute for TradingView alert
 * emails from all APM strategy versions and appends parsed rows to
 * the corresponding sheet in:
 * https://docs.google.com/spreadsheets/d/19wjt8sWl1PddkwYbk8NgXEzoZSo6dVbec3pUdAk3-n8
 *
 * SETUP (one-time):
 *   1. Extensions → Apps Script → paste this file → Save
 *   2. Run setupTrigger() once to install the 1-minute polling trigger.
 *   3. Ensure each Gmail label below exists (Gmail → Settings → Labels).
 *
 * Version differences handled automatically via APM_CONFIGS:
 *   - hasAtrFloor: v1–v3 check ATR floor; v4 does not.
 */

// ── Shared config ─────────────────────────────────────────────────────────────
var SPREADSHEET_ID = "19wjt8sWl1PddkwYbk8NgXEzoZSo6dVbec3pUdAk3-n8";

var APM_CONFIGS = [
  { version: "APM v1.0", sheetName: "Live Alerts",    label: "apm-processed",    hasAtrFloor: true  },
  { version: "APM v2.0", sheetName: "Live Alerts v2", label: "apm-v2-processed", hasAtrFloor: true  },
  { version: "APM v3.0", sheetName: "Live Alerts v3", label: "apm-v3-processed", hasAtrFloor: true  },
  { version: "APM v4.0", sheetName: "Live Alerts v4", label: "apm-v4-processed", hasAtrFloor: false },
];

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
  // Raw / ID
  "Raw Message",
  "Message ID"
];

var TRADE_LOG_HEADERS = [
  "Closed At",        // EXIT timestamp
  "Opened At",        // matching ENTRY timestamp
  "Version",
  "Symbol",
  "Timeframe",
  "Direction",
  "Entry Price",
  "Exit Price",
  "Stop",
  "Target",
  "R:R",
  "Risk ($)",
  "Qty",
  "Move %",
  "P&L ($)",
  "Comm ($)",
  "Net P&L ($)",
  "Max Runup",
  "Bars",
  "Result",
  "RSI at Entry",
  "ADX at Entry",
  "Vol/MA at Entry",
  "ATR % at Entry",
  "Exit Msg ID"       // dedup key
];


// ── Entry point: called by time trigger ──────────────────────────────────────
function processAlertEmails() {
  var ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  APM_CONFIGS.forEach(function(cfg) {
    processVersion(ss, cfg);
  });
  refreshDashboard(ss);
}

function processVersion(ss, cfg) {
  var ws    = getOrCreateSheet(ss, cfg.sheetName, LIVE_HEADERS);
  var label = getOrCreateLabel(cfg.label);
  var query = 'from:noreply@tradingview.com subject:"' + cfg.version + '" -label:' + cfg.label;

  var lastRow = ws.getLastRow();
  var existingIds = lastRow > 1
    ? ws.getRange(2, LIVE_HEADERS.indexOf("Message ID") + 1, lastRow - 1, 1).getValues().flat()
    : [];

  var threads = GmailApp.search(query, 0, 50);
  if (threads.length === 0) return;

  var rows = [];
  for (var i = 0; i < threads.length; i++) {
    var msgs = threads[i].getMessages();
    for (var j = 0; j < msgs.length; j++) {
      var msg   = msgs[j];
      var msgId = msg.getId();

      if (existingIds.indexOf(msgId) > -1) {
        Logger.log("[" + cfg.version + "] Skipping duplicate: " + msgId);
        continue;
      }

      var row = parseAlertBody(msg.getPlainBody(), msg.getDate(), msgId,
                               cfg.version, cfg.hasAtrFloor);
      if (row) {
        rows.push(row);
        existingIds.push(msgId);
      }
    }
    threads[i].addLabel(label);
  }

  if (rows.length > 0) {
    ws.getRange(ws.getLastRow() + 1, 1, rows.length, LIVE_HEADERS.length).setValues(rows);
    Logger.log("[" + cfg.version + "] Appended " + rows.length + " rows.");
    updateTradeLog(ss, rows, cfg.version);
  }
}


// ── Parser ────────────────────────────────────────────────────────────────────
function parseAlertBody(body, date, msgId, versionStr, hasAtrFloor) {
  body = body.replace(/\r\n/g, "\n").replace(/\r/g, "\n").trim();

  var lines = body.split("\n");
  if (lines.length < 2) return null;

  var header = lines[0].trim();
  if (header.indexOf(versionStr) === -1) return null;

  // Build key→value map from "Key   : Value" lines
  var kv = {};
  for (var i = 1; i < lines.length; i++) {
    var idx = lines[i].indexOf(":");
    if (idx > 0) {
      kv[lines[i].substring(0, idx).trim()] = lines[i].substring(idx + 1).trim();
    }
  }

  // Determine alert type from header
  var atype = "", direction = "";
  if      (header.indexOf("LONG ENTRY")  > -1) { atype = "ENTRY"; direction = "LONG";  }
  else if (header.indexOf("SHORT ENTRY") > -1) { atype = "ENTRY"; direction = "SHORT"; }
  else if (header.indexOf("TRAIL STOP")  > -1) { atype = "TRAIL";
    direction = body.indexOf("Direction : LONG") > -1 ? "LONG" : "SHORT"; }
  else if (header.indexOf("LONG EXIT")   > -1) { atype = "EXIT";        direction = "LONG";  }
  else if (header.indexOf("SHORT EXIT")  > -1) { atype = "EXIT";        direction = "SHORT"; }
  else if (header.indexOf("PANIC REGIME STARTED") > -1) { atype = "PANIC_START"; }
  else if (header.indexOf("PANIC REGIME CLEARED")  > -1) { atype = "PANIC_CLEAR"; }
  else return null;

  // Parse symbol / timeframe — header: "APM vX.Y | LONG ENTRY | BTC-USD [15m]"
  var symParts = header.split("|");
  var symRaw   = symParts.length >= 3 ? symParts[2].trim() : "";
  var symbol   = symRaw.split("[")[0].trim();
  var tf       = symRaw.indexOf("[") > -1 ? symRaw.split("[")[1].replace("]","").trim() : "";
  var recvAt   = Utilities.formatDate(date, Session.getScriptTimeZone(), "yyyy-MM-dd HH:mm:ss");

  function extractBetween(s, open, close) {
    var a = s.indexOf(open), b = s.indexOf(close, a);
    return (a >= 0 && b > a) ? s.substring(a + open.length, b).trim() : "";
  }

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
    atr_floor = hasAtrFloor ? (atrRaw.indexOf("Floor: OK") > -1 ? "OK" : "FAIL") : "";

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

    // EMA line: "EMA21/50/200: val/val/val  Stack: ...  Slope: ..."
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
    var bestRaw = kv["Best price"] || "";
    best    = bestRaw.indexOf("|") > -1 ? bestRaw.split("|")[0].trim() : bestRaw;
    new_sl  = (kv["Trail SL"] || "").split("(")[0].trim();
    var prevSlRaw = kv["Prev SL"] || "";
    prev_sl = prevSlRaw.indexOf("|") > -1 ? prevSlRaw.split("|")[0].trim() : prevSlRaw;

    var runupRaw = kv["Runup"] || "";
    runup_d   = runupRaw.split(" ")[0].replace(/[+\-]/g,"");
    runup_pct = extractBetween(runupRaw, "(", "%");
  }

  else if (atype === "EXIT") {
    var epxpRaw = kv["Entry"] || "";
    var epxp    = epxpRaw.indexOf("->") > -1 ? epxpRaw.split("->") : [epxpRaw, ""];
    entry    = epxp[0].trim();
    exit_p   = epxp[1].trim();
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


// ── Trade Log ─────────────────────────────────────────────────────────────────
/**
 * For any EXIT rows in newRows, find the matching ENTRY in the Live Alerts sheet
 * and append a combined trade row to "Trade Log".
 */
function updateTradeLog(ss, newRows, version) {
  var tlSheet = getOrCreateSheet(ss, "Trade Log", TRADE_LOG_HEADERS);

  var tlLastRow = tlSheet.getLastRow();
  var exitIdCol = TRADE_LOG_HEADERS.indexOf("Exit Msg ID") + 1;
  var existingExitIds = tlLastRow > 1
    ? tlSheet.getRange(2, exitIdCol, tlLastRow - 1, 1).getValues().flat()
    : [];

  var cfg = null;
  for (var ci = 0; ci < APM_CONFIGS.length; ci++) {
    if (APM_CONFIGS[ci].version === version) { cfg = APM_CONFIGS[ci]; break; }
  }
  if (!cfg) return;

  var alertSheet  = ss.getSheetByName(cfg.sheetName);
  if (!alertSheet) return;
  var alertLastRow = alertSheet.getLastRow();
  var allAlertRows = alertLastRow > 1
    ? alertSheet.getRange(2, 1, alertLastRow - 1, LIVE_HEADERS.length).getValues()
    : [];

  // LIVE_HEADERS column indices (0-based)
  var C_RECV  = 0,  C_SYM  = 1,  C_TF    = 2,  C_TYPE = 3,  C_DIR  = 4;
  var C_ENTRY = 5,  C_STOP = 6,  C_TGT   = 7,  C_RR   = 8,  C_RISK = 9;
  var C_QTY   = 10, C_ATRP = 12, C_RSI   = 14, C_ADX  = 17, C_VOLMA = 20;
  var C_EXITP = 32, C_MOVE = 33, C_PNL   = 34, C_COMM = 35;
  var C_MXRUP = 36, C_BARS = 37, C_MSGID = 45;

  var tlRows = [];

  for (var i = 0; i < newRows.length; i++) {
    var r = newRows[i];
    if (r[C_TYPE] !== "EXIT") continue;

    var exitMsgId = r[C_MSGID];
    if (existingExitIds.indexOf(exitMsgId) > -1) continue;

    var closedAt  = r[C_RECV];
    var symbol    = r[C_SYM];
    var tf        = r[C_TF];
    var direction = r[C_DIR];
    var entryPx   = String(r[C_ENTRY]).trim();
    var exitPx    = r[C_EXITP];
    var movePct   = r[C_MOVE];
    var pnl       = r[C_PNL];
    var comm      = r[C_COMM];
    var maxRunup  = r[C_MXRUP];
    var bars      = r[C_BARS];

    var pnlNum  = parseFloat(pnl)  || 0;
    var commNum = parseFloat(comm) || 0;
    var netPnl  = (pnlNum - commNum).toFixed(2);
    var result  = pnlNum >= 0 ? "WIN" : "LOSS";

    // Find matching ENTRY: same symbol + direction + entry price, scan backwards
    var openedAt="", stop="", target="", rr="", risk="", qty="";
    var rsiEntry="", adxEntry="", volmaEntry="", atrPctEntry="";

    for (var k = allAlertRows.length - 1; k >= 0; k--) {
      var ar = allAlertRows[k];
      if (ar[C_TYPE] === "ENTRY" &&
          ar[C_SYM]  === symbol  &&
          ar[C_DIR]  === direction &&
          String(ar[C_ENTRY]).split("|")[0].trim() === entryPx) {
        openedAt   = ar[C_RECV];
        stop       = ar[C_STOP];
        target     = ar[C_TGT];
        rr         = ar[C_RR];
        risk       = ar[C_RISK];
        qty        = ar[C_QTY];
        rsiEntry   = ar[C_RSI];
        adxEntry   = ar[C_ADX];
        volmaEntry = ar[C_VOLMA];
        atrPctEntry= ar[C_ATRP];
        break;
      }
    }

    tlRows.push([
      closedAt, openedAt, version, symbol, tf, direction,
      entryPx, exitPx, stop, target, rr, risk, qty,
      movePct, pnl, comm, netPnl,
      maxRunup, bars, result,
      rsiEntry, adxEntry, volmaEntry, atrPctEntry,
      exitMsgId
    ]);
    existingExitIds.push(exitMsgId);
  }

  if (tlRows.length > 0) {
    tlSheet.getRange(tlSheet.getLastRow() + 1, 1, tlRows.length, TRADE_LOG_HEADERS.length)
      .setValues(tlRows);
    Logger.log("[Trade Log] Appended " + tlRows.length + " trade(s) from " + version);
  }
}


// ── Dashboard ─────────────────────────────────────────────────────────────────
/**
 * Rebuilds the Dashboard sheet from scratch using all Trade Log data.
 * Called after every poll cycle.
 */
function refreshDashboard(ss) {
  var tlSheet = ss.getSheetByName("Trade Log");
  var dbSheet = ss.getSheetByName("Dashboard");
  if (!dbSheet) dbSheet = ss.insertSheet("Dashboard");

  var tlLastRow = tlSheet ? tlSheet.getLastRow() : 0;
  var trades = tlLastRow > 1
    ? tlSheet.getRange(2, 1, tlLastRow - 1, TRADE_LOG_HEADERS.length).getValues()
    : [];

  // TRADE_LOG_HEADERS column indices
  var TL_CLOSED=0, TL_OPENED=1, TL_VER=2, TL_SYM=3, TL_TF=4, TL_DIR=5;
  var TL_ENTRY=6,  TL_EXIT=7,   TL_STOP=8, TL_TGT=9, TL_RR=10, TL_RISK=11, TL_QTY=12;
  var TL_MOVE=13,  TL_PNL=14,   TL_COMM=15, TL_NET=16;
  var TL_MXRUP=17, TL_BARS=18,  TL_RESULT=19;

  // Aggregate stats per version + ALL
  var versions = APM_CONFIGS.map(function(c){ return c.version; });
  var keys = versions.concat(["ALL"]);
  var stats = {};
  keys.forEach(function(k) {
    stats[k] = { total:0, wins:0, losses:0, grossPnl:0, netPnl:0, totalBars:0,
                 best:-Infinity, worst:Infinity };
  });

  trades.forEach(function(tr) {
    var ver   = tr[TL_VER];
    var res   = tr[TL_RESULT];
    var gross = parseFloat(tr[TL_PNL])  || 0;
    var net   = parseFloat(tr[TL_NET])  || 0;
    var bars  = parseFloat(tr[TL_BARS]) || 0;
    [ver, "ALL"].forEach(function(k) {
      if (!stats[k]) return;
      stats[k].total++;
      if (res === "WIN") stats[k].wins++; else stats[k].losses++;
      stats[k].grossPnl  += gross;
      stats[k].netPnl    += net;
      stats[k].totalBars += bars;
      if (net > stats[k].best)  stats[k].best  = net;
      if (net < stats[k].worst) stats[k].worst = net;
    });
  });

  // Latest equity value per version (last non-empty cell in Equity column)
  var latestEquity = {};
  APM_CONFIGS.forEach(function(cfg) {
    var ws = ss.getSheetByName(cfg.sheetName);
    if (!ws || ws.getLastRow() < 2) { latestEquity[cfg.version] = ""; return; }
    var eqCol = LIVE_HEADERS.indexOf("Equity") + 1;
    var col   = ws.getRange(2, eqCol, ws.getLastRow() - 1, 1).getValues().flat();
    var eq = "";
    for (var i = col.length - 1; i >= 0; i--) {
      if (col[i] !== "") { eq = col[i]; break; }
    }
    latestEquity[cfg.version] = eq;
  });

  // ── Write Dashboard ───────────────────────────────────────────────────────
  var now = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "yyyy-MM-dd HH:mm:ss");
  dbSheet.clearContents();
  dbSheet.clearFormats();

  // ── Section 1: title
  var DARK_BG = "#1a1a2e", LIGHT_FG = "#e2e8f0", HDR_BG = "#16213e", ALL_BG = "#0f3460";
  dbSheet.getRange(1, 1).setValue("APM Strategy Dashboard");
  dbSheet.getRange(1, 2).setValue("Last updated: " + now);
  dbSheet.getRange(1, 1, 1, 12)
    .setFontWeight("bold").setFontSize(13)
    .setBackground(DARK_BG).setFontColor("#ffffff");

  // ── Section 2: per-version stats table
  var STAT_START = 3;
  var statHdr = ["Version","Trades","Wins","Losses","Win Rate",
                 "Gross P&L ($)","Net P&L ($)","Avg Net ($)",
                 "Best ($)","Worst ($)","Avg Bars","Latest Equity ($)"];
  dbSheet.getRange(STAT_START, 1, 1, statHdr.length).setValues([statHdr])
    .setFontWeight("bold").setBackground(HDR_BG).setFontColor(LIGHT_FG);

  function fmtStat(s) {
    var n = s.total;
    return [
      n,
      s.wins,
      s.losses,
      n > 0 ? (s.wins / n * 100).toFixed(1) + "%" : "—",
      n > 0 ? s.grossPnl.toFixed(2) : "—",
      n > 0 ? s.netPnl.toFixed(2)   : "—",
      n > 0 ? (s.netPnl / n).toFixed(2) : "—",
      n > 0 && s.best  > -Infinity ? s.best.toFixed(2)  : "—",
      n > 0 && s.worst <  Infinity ? s.worst.toFixed(2) : "—",
      n > 0 ? (s.totalBars / n).toFixed(1) : "—"
    ];
  }

  var statRows = [];
  versions.forEach(function(v) {
    statRows.push([v].concat(fmtStat(stats[v])).concat([latestEquity[v] || ""]));
  });
  statRows.push(["ALL"].concat(fmtStat(stats["ALL"])).concat([""]));

  var statDataRange = dbSheet.getRange(STAT_START + 1, 1, statRows.length, statHdr.length);
  statDataRange.setValues(statRows);
  // Bold + highlight the ALL row
  dbSheet.getRange(STAT_START + statRows.length, 1, 1, statHdr.length)
    .setFontWeight("bold").setBackground(ALL_BG).setFontColor(LIGHT_FG);

  // ── Section 3: recent trades
  var RECENT_START = STAT_START + statRows.length + 3;
  dbSheet.getRange(RECENT_START, 1).setValue("Recent Trades (last 20)")
    .setFontWeight("bold").setFontSize(11);

  var recentHdr = ["Closed At","Version","Symbol","Direction",
                   "Entry","Exit","Move %","P&L ($)","Net P&L ($)","Result","Bars"];
  dbSheet.getRange(RECENT_START + 1, 1, 1, recentHdr.length).setValues([recentHdr])
    .setFontWeight("bold").setBackground(HDR_BG).setFontColor(LIGHT_FG);

  var recent = trades.slice(-20).reverse();
  if (recent.length > 0) {
    var recentRows = recent.map(function(tr) {
      return [tr[TL_CLOSED], tr[TL_VER], tr[TL_SYM], tr[TL_DIR],
              tr[TL_ENTRY], tr[TL_EXIT], tr[TL_MOVE],
              tr[TL_PNL], tr[TL_NET], tr[TL_RESULT], tr[TL_BARS]];
    });
    dbSheet.getRange(RECENT_START + 2, 1, recentRows.length, recentHdr.length)
      .setValues(recentRows);
  }

  Logger.log("Dashboard refreshed: " + trades.length + " total trades.");
}


// ── Utilities ─────────────────────────────────────────────────────────────────
function getOrCreateSheet(ss, name, headers) {
  var ws = ss.getSheetByName(name);
  if (!ws) {
    ws = ss.insertSheet(name);
    ws.appendRow(headers);
    ws.setFrozenRows(1);
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

/**
 * Run ONCE from the Apps Script editor to install the 1-minute polling trigger.
 * Extensions → Apps Script → Run → setupTrigger
 */
function setupTrigger() {
  ScriptApp.getProjectTriggers()
    .filter(function(t){ return t.getHandlerFunction() === "processAlertEmails"; })
    .forEach(function(t){ ScriptApp.deleteTrigger(t); });

  ScriptApp.newTrigger("processAlertEmails")
    .timeBased()
    .everyMinutes(1)
    .create();

  Logger.log("Trigger installed: processAlertEmails every 1 minute.");
}

/** Utility: manually run once to test parsing against recent emails for all versions. */
function testParse() {
  APM_CONFIGS.forEach(function(cfg) {
    var threads = GmailApp.search(
      'from:noreply@tradingview.com subject:"' + cfg.version + '"', 0, 3);
    for (var i = 0; i < threads.length; i++) {
      var msgs = threads[i].getMessages();
      for (var j = 0; j < msgs.length; j++) {
        var msg = msgs[j];
        var row = parseAlertBody(msg.getPlainBody(), msg.getDate(),
                                 "test-" + i + "-" + j, cfg.version, cfg.hasAtrFloor);
        Logger.log("[" + cfg.version + "] " + JSON.stringify(row));
      }
    }
  });
}

/**
 * One-time backfill: rebuilds Trade Log from scratch by scanning all Live Alert sheets.
 * Run manually after first-time setup or if Trade Log gets out of sync.
 * Extensions → Apps Script → Run → rebuildTradeLog
 */
function rebuildTradeLog() {
  var ss = SpreadsheetApp.openById(SPREADSHEET_ID);

  // Clear the Trade Log (keep header)
  var tlSheet = getOrCreateSheet(ss, "Trade Log", TRADE_LOG_HEADERS);
  if (tlSheet.getLastRow() > 1) {
    tlSheet.getRange(2, 1, tlSheet.getLastRow() - 1, TRADE_LOG_HEADERS.length).clearContent();
  }
  Logger.log("Trade Log cleared. Rebuilding...");

  APM_CONFIGS.forEach(function(cfg) {
    var alertSheet = ss.getSheetByName(cfg.sheetName);
    if (!alertSheet || alertSheet.getLastRow() < 2) return;

    var allRows = alertSheet.getRange(2, 1, alertSheet.getLastRow() - 1, LIVE_HEADERS.length).getValues();
    // Pass all rows through updateTradeLog as if they are "new"
    updateTradeLog(ss, allRows, cfg.version);
  });

  refreshDashboard(ss);
  Logger.log("rebuildTradeLog complete.");
}
