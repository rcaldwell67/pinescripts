# Daily Transactions Modal - Feature Implementation

## Overview
Added a new modal to the dashboard that displays all transactions (orders and fills) for the current day from both paper and live trading modes.

## Files Modified

### 1. [docs/index.html](docs/index.html)
**Added:**
- **Daily Transactions Button** (line 45)
  - Button ID: `openDailyTransactionsBtn`
  - Class: `mode-btn` (matches Account Info button style)
  - Title: "View today's trades and fills"

- **Daily Transactions Modal** (lines 240-251)
  - Modal ID: `dailyTransactionsModal`
  - Follows same structure as Account Info modal
  - Contains ordered/fill transaction tables within scrollable div

### 2. [docs/site.js](docs/site.js)

**New Functions Added:**

#### `getTodayTransactions()`  (line 622)
Queries the database for all transactions from the current day:
- **Paper fills**: From `paper_fill_events` table
- **Live fills**: From `live_fill_events` table (if exists)
- **Paper orders**: From `paper_order_events` table  
- **Live orders**: From `live_order_events` table (if exists)

**Parameters:**
- None

**Returns:**
```javascript
{
  fills: [
    { symbol, side, qty, price, transaction_time, order_id, mode },
    ...
  ],
  orders: [
    { symbol, status, event_type, event_time, order_id, qty, notional, filled_qty, mode },
    ...
  ]
}
```

**Features:**
- Auto-detects if live tables exist (backward compatible)
- Error handling for missing tables
- ISO datetime filtering for exact "today" boundary
- Separates paper vs live transactions via `mode` field

#### `renderDailyTransactionsModal()` (line 720)
Renders the modal content with formatted transaction tables:
- Shows "No transactions today" if empty
- Displays orders table with columns: Time, Symbol, Type, Status, Qty, Notional, Mode
- Displays fills table with columns: Time, Symbol, Side, Qty, Price, Total, Mode
- Color coding:
  - Green highlight for buy fills
  - Red highlight for sell fills
  - Status badges (green for submitted, red for rejected, gray for other)
  - Paper/Live mode badges (blue for paper, red for live)

**Formatting:**
- Time: HH:MM:SS (24-hour)
- Qty: 4 decimal places
- Price/Notional: 2 decimal places with currency symbol
- Total: qty × price calculation

#### `openDailyTransactionsModal()` (line 819)
Opens the modal:
- Fetches latest transactions via `getTodayTransactions()`
- Renders content via `renderDailyTransactionsModal()`
- Adds 'open' class for CSS display
- Sets `aria-hidden` to false

#### `closeDailyTransactionsModal()` (line 826)
Closes the modal:
- Removes 'open' class
- Sets `aria-hidden` to true

**Event Listeners Added** (lines 2951-2970)

- Button click → `openDailyTransactionsModal()`
- Close button click → `closeDailyTransactionsModal()`
- Modal backdrop click → `closeDailyTransactionsModal()`
- ESC key → Close both Account Info and Daily Transactions modals

## Features

✅ **Real-Time Querying**: Queries database when button clicked (always current data)  
✅ **Paper + Live Combined**: Single unified view of both trading modes  
✅ **Comprehensive Display**: Shows orders and fills separately with all relevant details  
✅ **Smart Formatting**: Currency symbols, decimal places, time formatting  
✅ **Color Coded**: Visual indicators for transaction type, status, and mode  
✅ **Responsive**: Scrollable content for large transaction volumes  
✅ **Backward Compatible**: Gracefully handles older databases without live tables  
✅ **Accessible**: Proper ARIA labels, keyboard navigation (ESC to close)  

## Today's Definition
- **Start**: Midnight (00:00:00) of current day in browser timezone
- **End**: Midnight of next day
- Uses ISO 8601 format for consistent database queries

## UI Elements

### Transaction Table Format

**Orders Table Headers:**
```
Time | Symbol | Type | Status | Qty | Notional | Mode
```

**Fills Table Headers:**
```
Time | Symbol | Side | Qty | Price | Total | Mode
```

**Status/Mode Badges:**
- Status: Submitted (green), Rejected (red), Other (gray)
- Mode: Paper (blue background), Live (red background)

## Future Enhancements

Potential improvements:
- Filter by symbol
- Filter by side (buy/sell) or order type
- Export to CSV
- Statistics summary (total trades, win rate, etc.)
- Expandable row details
- Time range selection (not just today)
- Sort by column
