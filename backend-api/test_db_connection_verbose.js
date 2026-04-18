import dotenv from 'dotenv';
dotenv.config();
import mysql from 'mysql2/promise';

async function testConnection() {
  try {
    const conn = await mysql.createConnection({
      host: process.env.MARIADB_HOST,
      user: process.env.MARIADB_USER,
      password: process.env.MARIADB_PASSWORD,
      database: process.env.MARIADB_DATABASE,
      port: process.env.MARIADB_PORT || 3306,
    });
    const [rows] = await conn.query('SHOW DATABASES;');
    console.log('Connection successful. Databases:', rows);
    await conn.end();
  } catch (err) {
    console.error('Connection failed:', err);
    process.exit(1);
  }
}

testConnection();
