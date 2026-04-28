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
    // Join with symbols table using symbols_id foreign key
    const [rows] = await conn.execute(`
      SELECT br.*, s.asset_type
      FROM backtest_results br
      LEFT JOIN symbols s ON br.symbol_id = s.id
      ORDER BY br.symbol_id, br.version DESC, br.id DESC
    `);
    return rows;
  } finally {
    if (conn) await conn.end();
  }
}
