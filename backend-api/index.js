
import dotenv from 'dotenv';
dotenv.config();
import express from 'express';
import mysql from 'mysql2/promise';
import cors from 'cors';

const app = express();
app.use(cors());
app.use(express.json());

const dbConfig = {
  host: process.env.MARIADB_HOST || 'localhost',
  user: process.env.MARIADB_USER || 'root',
  password: process.env.MARIADB_PASSWORD || '',
  database: process.env.MARIADB_DATABASE || 'tradingcopilot',
  port: process.env.MARIADB_PORT || 3306,
};

// GET active and tradable Alpaca symbols for dropdown
app.get('/api/alpaca-symbols', async (req, res) => {
  let conn;
  try {
    conn = await mysql.createConnection(dbConfig);
    const [rows] = await conn.execute("SELECT symbol, name, asset_class, exchange FROM alpaca_symbols WHERE status='active' AND tradable=1 ORDER BY symbol ASC");
    res.json(rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  } finally {
    if (conn) await conn.end();
  }
});

// CREATE symbol
app.post('/api/symbols', async (req, res) => {
  let { symbol, description, asset_type, live_enabled = 0 } = req.body;
  if (!symbol) return res.status(400).json({ error: 'Symbol is required' });
  // Provide defaults if not present
  if (typeof description !== 'string') description = '';
  if (typeof asset_type !== 'string') asset_type = '';
  let conn;
  try {
    conn = await mysql.createConnection(dbConfig);
    await conn.execute(
      'INSERT INTO symbols (symbol, description, asset_type, live_enabled, isactive) VALUES (?, ?, ?, ?, 1) ON DUPLICATE KEY UPDATE description=VALUES(description), asset_type=VALUES(asset_type), live_enabled=VALUES(live_enabled), isactive=1',
      [symbol, description, asset_type, live_enabled]
    );
    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: err.message });
  } finally {
    if (conn) await conn.end();
  }
});

// UPDATE symbol (edit description, asset_type, live_enabled)
app.put('/api/symbols/:symbol', async (req, res) => {
  const { symbol } = req.params;
  const { description, asset_type, live_enabled } = req.body;
  let conn;
  try {
    conn = await mysql.createConnection(dbConfig);
    await conn.execute(
      'UPDATE symbols SET description=?, asset_type=?, live_enabled=? WHERE symbol=?',
      [description, asset_type, live_enabled, symbol]
    );
    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: err.message });
  } finally {
    if (conn) await conn.end();
  }
});

// DEACTIVATE symbol (set isactive=0 instead of delete)
app.patch('/api/symbols/:symbol/deactivate', async (req, res) => {
  const { symbol } = req.params;
  let conn;
  try {
    conn = await mysql.createConnection(dbConfig);
    await conn.execute('UPDATE symbols SET isactive=0 WHERE symbol=?', [symbol]);
    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: err.message });
  } finally {
    if (conn) await conn.end();
  }
});

app.get('/api/symbols', async (req, res) => {
  let conn;
  try {
    conn = await mysql.createConnection(dbConfig);
    const [rows] = await conn.execute('SELECT * FROM symbols WHERE isactive = 1');
    res.json(rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  } finally {
    if (conn) await conn.end();
  }
});

const PORT = process.env.PORT || 4000;
app.listen(PORT, () => {
  console.log(`Backend API listening on port ${PORT}`);
});
