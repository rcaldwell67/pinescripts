# Backend Python API

## Setup

1. Install dependencies:
   ```sh
   pip install -r requirements.txt
   ```
2. Set environment variables (see `.env` for MariaDB connection).
3. Run the API:
   ```sh
   python backend/api.py
   ```

## Docker

To build and run with Docker Compose (recommended):

```sh
docker-compose up --build
```

- Python API: http://localhost:5000/api/health
- Node.js API: http://localhost:4000/
- MariaDB: localhost:3306

## Endpoints
- `/api/health` — Health check
- `/api/symbols` — List active symbols

## Notes
- Update `.env` with your database credentials as needed.
- Extend endpoints as development progresses.
