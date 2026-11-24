import pool, { withTransaction } from '../config/db.js';

export async function findSettings() {
  const { rows } = await pool.query('SELECT key, value FROM settings');
  return Object.fromEntries(rows.map((row) => [row.key, row.value]));
}

export async function saveSettings(changes, userId) {
  await withTransaction(async (client) => {
    for (const [key, value] of Object.entries(changes)) {
      await client.query(
        `INSERT INTO settings (key, value, updated_by) VALUES ($1, $2, $3)
         ON CONFLICT (key) DO UPDATE
           SET value = EXCLUDED.value, updated_at = now(), updated_by = EXCLUDED.updated_by`,
        [key, String(value), userId],
      );
    }
  });
}