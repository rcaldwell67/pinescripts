# Dashboard Updates: Order & Fill Event Display

## Summary
Updated [docs/site.js](docs/site.js) to display the new order tracking data (qty, notional, filled_qty, submitted_at) in the Activity Feed.

## Changes Made

### 1. Enhanced Order Events Display
**Function**: `queryOrderLogsFromDb()` (line ~1333)

**New Columns Queried**:
- `qty` - Order quantity in shares
- `notional` - Dollar amount value
- `filled_qty` - Actual quantity filled
- `submitted_at` - Order submission timestamp

**Detail Display Enhancement**:
- Before: `order_id=abc123`
- After: `order_id=abc123 • qty=100.0000 • notional=$5000.00 • filled=99.5000`
- Uses bullet separators (`•`) for readability
- Smart formatting:
  - Quantities shown as 4 decimal places
  - Notional values shown as 2 decimal places with $ prefix
  - Only shows filled_qty if it differs from qty (partial fill indicator)

**Paper + Live Support**:
- Queries both `paper_order_events` and `live_order_events` tables
- Adds `mode` field ('paper' or 'live') for event source identification
- Auto-detects live_order_events table existence (backward compatible)
- Merges and sorts all events by timestamp descending

### 2. Enhanced Fill Events Display
**Function**: `queryFillLogsFromDb()` (line ~1295)

**Detail Display Enhancement**:
- Before: `side=buy qty=100 price=45.50`
- After: `side=buy • qty=100 • price=45.50 • order_id=abc123`
- Added `order_id` to fill event details for order-to-fill tracing

**Paper + Live Support**:
- Queries both `paper_fill_events` and `live_fill_events` tables
- Adds `mode` field for event source identification
- Auto-detects live_fill_events table existence
- Merges and sorts all fill events by timestamp descending

## Activity Feed Display

### HTML Table Structure
The activity feed now shows:
```
Time | Source | Symbol | Event | Status | Detail
-----|--------|--------|-------|--------|-------
2026-04-02 15:30:45 | Orders | BTC/USD | order_placed | submitted | order_id=xxx • qty=1.5000 • notional=$65000.00
2026-04-02 15:30:46 | Fills | BTC/USD | fill | buy • side=buy • qty=1.5000 • price=43333.33 • order_id=xxx
```

## Benefits

✅ **Alpaca API Visibility**: Order quantities and notional values now visible
✅ **Partial Fill Tracking**: Shows when filled_qty differs from requested qty
✅ **Order Flow Tracing**: Can correlate orders with their fills via order_id
✅ **Paper + Live Unified**: Single feed shows both paper and live events with mode indicator
✅ **Backward Compatible**: Auto-gracefully handles databases without live tables
✅ **Human-Readable Formatting**: Decimal places and currency symbols for clarity

## Implementation Highlights

- **Robust Table Detection**: Uses `sqlite_master` query to check table existence
- **Error Handling**: Silently continues if live_order_events doesn't exist
- **Smart Formatting**: 
  - Qty: 4 decimal places for precision
  - Notional: 2 decimal places for USD amounts
  - Fills: Only shows if value differs from qty
- **Sorted Results**: Combined paper/live results sorted by time (newest first)
- **Detail String Building**: Parts filtered to exclude empty values, joined with bullet separator

## Testing
- Dashboard loads successfully with updated order/fill queries
- Gracefully handles databases before live tables were added
- Detail column provides comprehensive order information at a glance
