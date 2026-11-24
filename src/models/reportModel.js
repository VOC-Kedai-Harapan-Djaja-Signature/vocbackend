import pool, { withTransaction } from '../config/db.js';

const TIMEZONE = process.env.APP_TIMEZONE || 'Asia/Jakarta';
const MODEL_VERSION = 'voc_model v4 (multi-topik, pool 1.877)';

export async function findReviewsForReport(from, to) {
  const { rows } = await pool.query(
    `SELECT r.id, r.text, r.source, r.rating,
            r.rating_rasa, r.rating_harga, r.rating_pelayanan, r.rating_tempat,
            to_char(COALESCE(r.review_date, (r.created_at AT TIME ZONE $1)::date), 'YYYY-MM-DD') AS date
     FROM reviews r
     WHERE r.text IS NOT NULL
       AND COALESCE(r.review_date, (r.created_at AT TIME ZONE $1)::date) BETWEEN $2 AND $3
     ORDER BY r.id`,
    [TIMEZONE, from, to],
  );
  return rows;
}

async function ambangSaran(client) {
  const { rows } = await client.query("SELECT value FROM settings WHERE key = 'ambang_saran'");
  return Number(rows[0]?.value) || 5;
}

export async function saveWeeklyReport({ from, to, hasil, idsByText }) {
  return withTransaction(async (client) => {
    const ringkasan = hasil.ringkasan;
    const { rows: [laporan] } = await client.query(
      `INSERT INTO weekly_reports
         (period_start, period_end, total_reviews, negative_count, positive_count, result, llm_model, llm_note)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
       ON CONFLICT (period_start, period_end) DO UPDATE SET
         total_reviews = EXCLUDED.total_reviews, negative_count = EXCLUDED.negative_count,
         positive_count = EXCLUDED.positive_count, result = EXCLUDED.result,
         llm_model = EXCLUDED.llm_model, llm_note = EXCLUDED.llm_note, created_at = now()
       RETURNING id`,
      [
        from, to,
        Number(ringkasan.total_baru) || 0,
        Number(ringkasan.negatif) || 0,
        Number(hasil.ringkasan_positif?.positif) || 0,
        hasil,
        hasil.model_llm ? String(hasil.model_llm).slice(0, 100) : null,
        // Kolom llm_note maksimal 100 karakter; pesan galat LLM bisa lebih panjang.
        String(hasil.catatan_saran || hasil.catatan_saran_positif || '').slice(0, 100) || null,
      ],
    );

    const { rows: topikDb } = await client.query('SELECT id, lower(name) AS nama FROM topics');
    const topikId = Object.fromEntries(topikDb.map((t) => [t.nama, t.id]));
    const semuaId = [...idsByText.values()].flat();
    await client.query("DELETE FROM review_topics WHERE assigned_by = 'ai' AND review_id = ANY($1)", [semuaId]);

    const perTeks = new Map();
    const kelompok = [['negatif_per_topik', 'tidak_puas'], ['positif_per_topik', 'puas']];
    for (const [kunci, sentimen] of kelompok) {
      for (const [topik, items] of Object.entries(hasil[kunci] || {})) {
        for (const item of Array.isArray(items) ? items : []) {
          const data = perTeks.get(item.teks) || { sentimen, topik: [], utama: null };
          if (!data.topik.includes(topik)) data.topik.push(topik);
          if (!data.utama || (item.prob_topik ?? 0) > (data.utama.prob_topik ?? 0)) {
            data.utama = { ...item, topik };
          }
          perTeks.set(item.teks, data);
        }
      }
    }

    let dianalisis = 0;
    for (const [teks, data] of perTeks) {
      const utama = data.utama;
      for (const reviewId of idsByText.get(teks) || []) {
        await client.query(
          `INSERT INTO review_analysis
             (review_id, sentiment, sentiment_score, topic_id, topic_score, explanation, model_version)
           VALUES ($1, $2, $3, $4, $5, $6, $7)
           ON CONFLICT (review_id) DO UPDATE SET
             sentiment = EXCLUDED.sentiment, sentiment_score = EXCLUDED.sentiment_score,
             topic_id = EXCLUDED.topic_id, topic_score = EXCLUDED.topic_score,
             explanation = EXCLUDED.explanation, model_version = EXCLUDED.model_version,
             analyzed_at = now()`,
          [
            reviewId, data.sentimen, utama.prob_sentimen ?? null,
            topikId[utama.topik] ?? null, utama.prob_topik ?? null,
            { shap_topik: utama.shap_topik ?? null, shap_sentimen: utama.shap_sentimen ?? null, topik_semua: data.topik },
            MODEL_VERSION,
          ],
        );
        for (const topik of data.topik) {
          if (!topikId[topik]) continue;
          await client.query(
            `INSERT INTO review_topics (review_id, topic_id, assigned_by) VALUES ($1, $2, 'ai')
             ON CONFLICT (review_id, topic_id) DO NOTHING`,
            [reviewId, topikId[topik]],
          );
        }
        dianalisis += 1;
      }
    }

    await client.query("DELETE FROM suggestions WHERE report_id = $1 AND status = 'aktif'", [laporan.id]);
    const ambang = await ambangSaran(client);
    const keluhan = ringkasan.per_topik || {};
    const terbanyak = Math.max(0, ...Object.values(keluhan).map(Number));
    // Prioritas: topik dengan keluhan terbanyak = mendesak, mencapai ambang = sedang, sisanya rendah.
    const prioritas = (jumlah) => {
      if (jumlah > 0 && jumlah === terbanyak) return 'mendesak';
      return jumlah >= ambang ? 'sedang' : 'rendah';
    };

     let saranDibuat = 0;
    const simpanSaran = async (topik, kind, priority, text, reason, count) => {
      if (!topikId[topik] || typeof text !== 'string' || !text.trim()) return;
      await client.query(
        `INSERT INTO suggestions (report_id, topic_id, kind, priority, text, reason, complaint_count)
         VALUES ($1, $2, $3, $4, $5, $6, $7)`,
        [laporan.id, topikId[topik], kind, priority, text.trim(), typeof reason === 'string' ? reason : null, count],
      );
      saranDibuat += 1;
    };

    for (const p of hasil.saran_deepseek?.per_topik || []) {
      const jumlah = Number(keluhan[p.topik]) || 0;
      for (const s of Array.isArray(p.saran) ? p.saran : []) {
        await simpanSaran(p.topik, 'perbaikan', prioritas(jumlah), s, p.keluhan_utama, jumlah);
      }
    }
    for (const p of hasil.saran_deepseek_positif?.per_topik || []) {
      await simpanSaran(p.topik, 'kekuatan', 'rendah', p.dipertahankan, p.kekuatan, 0);
    }

    return { id: laporan.id, dianalisis, saranDibuat };
  });
}

export async function findLatestReport() {
  const { rows } = await pool.query(
    `SELECT id, to_char(period_start, 'YYYY-MM-DD') AS period_start, to_char(period_end, 'YYYY-MM-DD') AS period_end,
            total_reviews, negative_count, positive_count, result, llm_note, created_at
     FROM weekly_reports
     ORDER BY period_end DESC, created_at DESC
     LIMIT 1`,
  );
  return rows[0] || null;
}