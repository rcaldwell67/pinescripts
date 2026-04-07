# PulseBoard React Dashboard

React dashboard for monitoring Crypto and ETF strategy performance from a single snapshot JSON.

## Data source

The UI reads:

- `public/data/dashboard_snapshot.json`

Generate the snapshot from the repository DB with:

```bash
python backend/data/export_dashboard_snapshot.py
```

This exporter also writes to:

- `docs/data/dashboard_snapshot.json`

## Run locally

```bash
cd frontend-react
npm install
npm run dev
```

## Build for GitHub Pages

Set the Vite base path to the deployment subpath:

```bash
set VITE_BASE_PATH=/pinescripts/
npm run build
```

Then publish `frontend-react/dist` to your Pages target folder.
