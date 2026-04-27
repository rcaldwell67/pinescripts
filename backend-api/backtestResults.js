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
    // Example: fetch all backtest results (customize as needed)
    const [rows] = await conn.execute('SELECT * FROM backtest_results ORDER BY symbol, version DESC, id DESC');
    return rows;
  } finally {
    if (conn) await conn.end();
  }
}
