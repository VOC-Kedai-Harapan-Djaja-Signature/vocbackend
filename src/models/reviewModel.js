import pool, { withTransaction } from '../config/db.js';
const TIMEZONE = process.env.APP_TIMEZONE || 'Asia/Jakarta';

export async function createReview({
  source,
  text = null,
  ipHash = null,
  gender = null,
  age = null,
  ratings = {},
  rating = null,
  reviewDate = null,
  topic = null,
}) {
  return withTransaction(async (client) => {
    const { rows } = await client.query(
      `INSERT INTO reviews
         (source, text, ip_hash, gender, age,
          rating_rasa, rating_harga, rating_pelayanan, rating_tempat,
          rating, review_date)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
       RETURNING id`,
      [
        source, text, ipHash, gender, age,
        ratings.rasa ?? null, ratings.harga ?? null, ratings.pelayanan ?? null, ratings.tempat ?? null,
        rating, reviewDate,
      ],
    );
    const id = rows[0].id;

    if (topic) {
      await client.query(
        'INSERT INTO review_topics (review_id, topic_id) SELECT $1, id FROM topics WHERE lower(name) = $2',
        [id, topic],
      );
    }
    return id;
  });
}

export async function findReviews({ from, to, source, topic, responded, limit, offset }) {
  const params = [TIMEZONE];
  const where = [];
  const add = (value) => {
    params.push(value);
    return `$${params.length}`;
  };

  const tanggal = 'COALESCE(r.review_date, (r.created_at AT TIME ZONE $1)::date)';

  if (from) where.push(`${tanggal} >= ${add(from)}`);
  if (to) where.push(`${tanggal} <= ${add(to)}`);
  if (source) where.push(`r.source = ${add(source)}`);
  if (topic) {
    where.push(`EXISTS (SELECT 1 FROM review_topics rt JOIN topics t ON t.id = rt.topic_id
                        WHERE rt.review_id = r.id AND lower(t.name) = ${add(topic)})`);
  }
  if (responded === true) where.push('r.responded_at IS NOT NULL');
  if (responded === false) where.push('r.responded_at IS NULL');

  const { rows } = await pool.query(
    `SELECT
       r.id, r.source, r.text, r.gender, r.age,
       r.rating_rasa, r.rating_harga, r.rating_pelayanan, r.rating_tempat, r.rating,
       to_char(${tanggal}, 'YYYY-MM-DD') AS date,
       r.created_at, r.responded_at,
       u.name AS responded_by_name,
       a.sentiment AS ai_sentiment,
       COALESCE((SELECT json_agg(lower(t.name) ORDER BY (rt.assigned_by = 'staf') DESC, (t.id = a.topic_id) IS TRUE DESC, t.id)
                 FROM review_topics rt JOIN topics t ON t.id = rt.topic_id
                 WHERE rt.review_id = r.id), '[]') AS topics,
       COALESCE((SELECT json_agg(m.name ORDER BY m.name)
                 FROM review_menus rm JOIN menus m ON m.id = rm.menu_id
                 WHERE rm.review_id = r.id), '[]') AS menus,
       COUNT(*) OVER () AS total
     FROM reviews r
     LEFT JOIN users u ON u.id = r.responded_by
     LEFT JOIN review_analysis a ON a.review_id = r.id
     ${where.length > 0 ? `WHERE ${where.join(' AND ')}` : ''}
     ORDER BY ${tanggal} DESC, r.id DESC
     LIMIT ${add(limit)} OFFSET ${add(offset)}`,
    params,
  );

  const total = rows.length > 0 ? Number(rows[0].total) : 0;
  return { rows, total };
}
export async function setResponded(id, responded, userId) {
  const { rows } = await pool.query(
    responded
      ? `UPDATE reviews
           SET responded_at = COALESCE(responded_at, now()),
               responded_by = COALESCE(responded_by, $2)
         WHERE id = $1
         RETURNING id, responded_at`
      : `UPDATE reviews SET responded_at = NULL, responded_by = NULL
         WHERE id = $1
         RETURNING id, responded_at`,
    responded ? [id, userId] : [id],
  );
  return rows[0] || null;
}