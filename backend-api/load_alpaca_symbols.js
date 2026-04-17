import dotenv from 'dotenv';
dotenv.config();
import mysql from 'mysql2/promise';
import fetch from 'node-fetch';

const dbConfig = {
  host: process.env.MARIADB_HOST || 'localhost',
  user: process.env.MARIADB_USER || 'root',
  password: process.env.MARIADB_PASSWORD || '',
  database: process.env.MARIADB_DATABASE || 'tradingcopilot',
  port: process.env.MARIADB_PORT || 3306,
};

const ALPACA_API_URL = 'https://paper-api.alpaca.markets/v2/assets';
const ALPACA_KEY = process.env.ALPACA_API_KEY;
const ALPACA_SECRET = process.env.ALPACA_API_SECRET;

async function fetchAlpacaSymbols() {
  const res = await fetch(ALPACA_API_URL, {
    headers: {
      'APCA-API-KEY-ID': ALPACA_KEY,
      'APCA-API-SECRET-KEY': ALPACA_SECRET,
    },
  });
  if (!res.ok) throw new Error('Failed to fetch Alpaca symbols');
  return res.json();
}

function safe(v) {
  return v === undefined ? null : v;
}

async function insertSymbols(symbols) {
  const conn = await mysql.createConnection(dbConfig);
  const sql = `REPLACE INTO alpaca_symbols (
    asset_id, symbol, name, status, tradable, marginable, shortable, easy_to_borrow, fractionable, asset_class, exchange, last_trade_time, maintenance_margin_requirement, min_order_size, min_trade_increment, min_trade_price_increment, attributes
  ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`;
  for (const s of symbols) {
    await conn.execute(sql, [
      safe(s.id),
      safe(s.symbol),
      safe(s.name),
      safe(s.status),
      s.tradable ? 1 : 0,
      s.marginable ? 1 : 0,
      s.shortable ? 1 : 0,
      s.easy_to_borrow ? 1 : 0,
      s.fractionable ? 1 : 0,
      safe(s.class), // Alpaca API uses 'class' not 'asset_class'
      safe(s.exchange),
      s.last_trade_time ? s.last_trade_time.replace('T', ' ').replace('Z', '') : null,
      safe(s.maintenance_margin_requirement),
      safe(s.min_order_size),
      safe(s.min_trade_increment),
      safe(s.min_trade_price_increment),
      s.attributes ? JSON.stringify(s.attributes) : null,
    ]);
  }
  await conn.end();
}

(async () => {
  try {
    const symbols = await fetchAlpacaSymbols();
    await insertSymbols(symbols);
    console.log(`Inserted ${symbols.length} symbols into alpaca_symbols.`);
  } catch (err) {
    console.error(err);
  }
})();
