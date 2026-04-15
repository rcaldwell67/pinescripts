- All Alpaca symbols have been added to the symbols table.
- All Alpaca data headers/columns (description, asset_type, live_enabled, isactive, and all Alpaca API fields) are now present in the symbols table.
- Scripts were run in the correct order and the database schema was updated as needed.
- GitHub Actions workflow now runs every 12 hours to keep Alpaca symbols and data in sync automatically.
- Task complete.

Make sure above Alpaca symbols data has a github workflow schedule that runs every 12 hours