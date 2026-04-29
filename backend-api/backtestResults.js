import mysql from 'mysql2/promise';
import dotenv from 'dotenv';
dotenv.config();

const dbConfig = {
  host: process.env.MARIADB_HOST || 'localhost',
  user: process.env.MARIADB_USER || 'root',
  password: process.env.MARIADB_PASSWORD || '',
  database: process.env.MARIADB_DATABASE || 'tradingcopilot',
  port: process.env.MARIADB_PORT || 3306,
};

export async function getBacktestResults() {
  let conn;
  try {
    conn = await mysql.createConnection(dbConfig);
    // Join with symbols table using symbol_id foreign key
    const [rows] = await conn.execute(`
      SELECT br.id, br.symbol_id, br.symbol, br.version, br.timestamp, br.metrics, br.notes, br.current_equity, s.asset_type
      FROM backtest_results br
      LEFT JOIN symbols s ON br.symbol_id = s.id
      ORDER BY br.symbol_id, br.version DESC, br.id DESC
    `);
    console.log('[DEBUG] SQL rows:', JSON.stringify(rows, null, 2));
    return rows;
  } finally {
    if (conn) await conn.end();
  }
}
