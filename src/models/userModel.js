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

export async function findById(id) {
  const { rows } = await pool.query(
    'SELECT id, name, email, password, role FROM users WHERE id = $1',
    [id],
  );
  return rows[0] || null;
}

export async function updatePassword(id, passwordHash) {
  const { rowCount } = await pool.query(
    'UPDATE users SET password = $2 WHERE id = $1',
    [id, passwordHash],
  );
  return rowCount === 1;
}