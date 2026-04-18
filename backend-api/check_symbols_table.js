import dotenv from 'dotenv';
dotenv.config();
import mysql from 'mysql2/promise';

async function checkSymbolsTable() {
  try {
    const conn = await mysql.createConnection({
      host: process.env.MARIADB_HOST,
      user: process.env.MARIADB_USER,
      password: process.env.MARIADB_PASSWORD,
      database: process.env.MARIADB_DATABASE,
      port: process.env.MARIADB_PORT || 3306,
    });
    const [rows] = await conn.query('SELECT * FROM symbols LIMIT 10;');
    console.log('Rows in symbols table:', rows);
    await conn.end();
  } catch (err) {
    console.error('Error querying symbols table:', err);
    process.exit(1);
  }
}

checkSymbolsTable();
