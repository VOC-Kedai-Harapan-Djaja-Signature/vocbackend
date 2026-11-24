import pool from '../config/db.js';

const KOLOM = `s.id, s.kind, s.priority, lower(t.name) AS topic, s.text, s.reason, s.complaint_count,
  s.status, s.created_at, s.completed_at, u.name AS completed_by, s.completion_note,
  to_char(w.period_start, 'YYYY-MM-DD') AS period_start,
  to_char(w.period_end, 'YYYY-MM-DD') AS period_end`;

const DARI = `FROM suggestions s
  JOIN topics t ON t.id = s.topic_id
  LEFT JOIN users u ON u.id = s.completed_by
  LEFT JOIN weekly_reports w ON w.id = s.report_id`;

export async function findActiveSuggestions() {
  const { rows } = await pool.query(
    `SELECT ${KOLOM} ${DARI}
     WHERE s.status = 'aktif'
       AND s.report_id = (SELECT id FROM weekly_reports ORDER BY period_end DESC, created_at DESC LIMIT 1)
     ORDER BY CASE s.priority WHEN 'mendesak' THEN 1 WHEN 'sedang' THEN 2 ELSE 3 END,
              s.complaint_count DESC, s.id`,
  );
  return rows;
}

export async function findCompletedSuggestions(limit) {
  const { rows } = await pool.query(
    `SELECT ${KOLOM} ${DARI}
     WHERE s.status = 'selesai'
     ORDER BY s.completed_at DESC, s.id DESC
     LIMIT $1`,
    [limit],
  );
  return rows;
}

export async function completeSuggestion(id, userId, note) {
  const { rowCount } = await pool.query(
    `UPDATE suggestions
        SET status = 'selesai', completed_at = now(), completed_by = $2, completion_note = $3
      WHERE id = $1 AND status = 'aktif' AND kind = 'perbaikan'`,
    [id, userId, note],
  );
  const { rows } = await pool.query(`SELECT ${KOLOM} ${DARI} WHERE s.id = $1`, [id]);
  return { updated: rowCount === 1, suggestion: rows[0] || null };
}