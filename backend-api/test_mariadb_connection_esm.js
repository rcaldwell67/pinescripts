import dotenv from 'dotenv';
dotenv.config({ path: '.venv/.env' });
import mysql from 'mysql2/promise';

(async () => {
  try {
    const conn = await mysql.createConnection({
      host: process.env.MARIADB_HOST,
      user: process.env.MARIADB_USER,
      password: process.env.MARIADB_PASSWORD,
      database: process.env.MARIADB_DATABASE,
      port: process.env.MARIADB_PORT || 3306
    });
    await conn.ping();
    console.log('MariaDB connection successful (ESM .venv/.env)');
    await conn.end();
    process.exit(0);
  } catch (e) {
    console.error('MariaDB connection failed (ESM .venv/.env):', e.message);
    process.exit(1);
  }
})();
