import pg from 'pg';

// Connection pool: koneksi dipakai bergantian, tidak dibuka-tutup tiap request.
const pool = new pg.Pool({
  host: process.env.DB_HOST || 'localhost',
  port: Number(process.env.DB_PORT) || 5432,
  user: process.env.POSTGRES_USER,
  password: process.env.POSTGRES_PASSWORD,
  database: process.env.POSTGRES_DB,
  max: 10,
});

pool.on('error', (error) => {
  console.error('Koneksi database bermasalah:', error.message);
});

// Menjalankan beberapa query sebagai satu kesatuan:
// semua berhasil (COMMIT) atau semua dibatalkan (ROLLBACK).
export async function withTransaction(work) {
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const result = await work(client);
    await client.query('COMMIT');
    return result;
  } catch (error) {
    await client.query('ROLLBACK');
    throw error;
  } finally {
    client.release();
  }
}

export default pool;
