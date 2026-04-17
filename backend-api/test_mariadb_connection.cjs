require('dotenv').config({ path: '.venv/.env' });
const mysql = require('mysql2/promise');
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
    console.log('MariaDB connection successful');
    await conn.end();
    process.exit(0);
  } catch (e) {
    console.error('MariaDB connection failed:', e.message);
    process.exit(1);
  }
})();
