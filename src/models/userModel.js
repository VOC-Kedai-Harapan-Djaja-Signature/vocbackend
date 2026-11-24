import pool from '../config/db.js';

export async function findByEmail(email) {
  const { rows } = await pool.query(
    'SELECT id, name, email, password, role FROM users WHERE email = $1',
    [email],
  );
  return rows[0] || null;
}

// Mengembalikan true bila akun baru dibuat, false bila email sudah ada.
export async function createIfMissing({ name, email, password, role }) {
  const { rowCount } = await pool.query(
    `INSERT INTO users (name, email, password, role)
     VALUES ($1, $2, $3, $4)
     ON CONFLICT (email) DO NOTHING`,
    [name, email, password, role],
  );
  return rowCount === 1;
}
