# Database Schema Updates: Paper & Live Order Tracking

## Overview
Updated the `tradingcopilot.db` schema to add comprehensive order tracking support for both paper and live trading, with enhanced fields for Alpaca API order quantity and notional value constraints.

## Changes Made

### 1. **Enhanced Paper Trading Order Tables**
Updated `backend/paper_trading/realtime_alpaca_paper_trader.py`:
- **paper_order_events table** - Added columns:
  - `qty` (REAL) - Order quantity in shares
  - `notional` (REAL) - Dollar amount (alternative to qty)
  - `filled_qty` (REAL) - Actual quantity filled
  - `submitted_at` (TEXT) - When order was submitted

### 2. **Added Live Trading Order Tables** (NEW)
Added to `backend/live_trading/realtime_alpaca_live_trader.py`:
- **live_order_trade_links** - Links orders to trades
  - `order_id` (PRIMARY KEY)
  - `symbol`, `version`, `trade_id`, `role`
  
- **live_order_events** - Tracks order lifecycle with enhanced fields
  - `event_id` (PRIMARY KEY)
  - `order_id`, `symbol`, `status`, `event_type`, `event_time`
  - `qty`, `notional`, `filled_qty` - For quantity/notional tracking
  - `submitted_at` - Submission timestamp
  - `raw_json` - Full Alpaca response

- **Helper Functions Added**:
  - `_fill_exists()` - Check existing fills
  - `_link_order_to_trade()` - Associate orders with trades
  - `_trade_for_order()` - Lookup trade for an order

### 3. **Updated Database Schema**
Modified `backend/data/create_tradingcopilot_db.py`:
- Added all paper order tables to main DB creation
- Added all live order tables to main DB creation
- Ensured consistent schema across paper and live modes

### 4. **Migration Script**
Created `backend/data/migrate_add_live_order_tables.py`:
- Safely adds missing live order tables to existing databases
- Adds missing columns to paper_order_events
- Non-destructive (uses CREATE TABLE IF NOT EXISTS)
- Successfully ran: ✅

## Database Tables Structure

### Paper Trading
```
paper_fill_events
├── activity_id, symbol, side, qty, price, transaction_time, order_id

paper_order_trade_links
├── order_id → trade_id (with symbol, version, role)

paper_order_events (ENHANCED)
├── event_id, order_id, symbol, status, event_type, event_time
├── qty, notional, filled_qty (NEW - for Alpaca API constraints)
└── submitted_at, raw_json
```

### Live Trading (NEW)
```
live_fill_events
├── activity_id, symbol, side, qty, price, transaction_time, order_id

live_order_trade_links (NEW)
├── order_id → trade_id (with symbol, version, role)

live_order_events (NEW - Enhanced)
├── event_id, order_id, symbol, status, event_type, event_time
├── qty, notional, filled_qty (for Alpaca API constraints)
└── submitted_at, raw_json
```

## Alpaca API Alignment

The new columns support Alpaca order parameters:
- **qty**: Number of shares (fractionable for market/day orders)
- **notional**: Dollar amount alternative (market orders only)
- **filled_qty**: Partial fill tracking
- **submitted_at**: Order submission time for latency tracking

Since Alpaca doesn't document an explicit minimum share quantity, the schema now supports:
- Tracking calculated order quantities for validation
- Recording notional values for compliance
- Monitoring fill completeness (filled_qty vs qty)

## Migration Status
✅ **Completed** - All tables created/verified
✅ **Paper tables** enhanced with 4 new columns
✅ **Live tables** added (previously missing)
✅ **Backward compatible** - Existing data preserved

## Next Steps
1. Update order submission code to populate new columns (qty, notional)
2. Add order event logging when orders are submitted/updated
3. Enhance order validation with quantity constraints where needed
