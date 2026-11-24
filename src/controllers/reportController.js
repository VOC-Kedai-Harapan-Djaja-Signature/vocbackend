import { AiError, mintaLaporanMingguan } from '../services/aiService.js';
import { findLatestReport, findReviewsForReport, saveWeeklyReport } from '../models/reportModel.js';

const TIMEZONE = process.env.APP_TIMEZONE || 'Asia/Jakarta';
const MAKS_HARI = 31;
const MAKS_ULASAN_AI = 100;

function hariIni() {
  return new Intl.DateTimeFormat('en-CA', { timeZone: TIMEZONE }).format(new Date());
}

function geserHari(tanggal, n) {
  const d = new Date(`${tanggal}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

function bacaTanggal(value, name) {
  if (value === undefined || value === null || value === '') return null;
  const ok = typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
    && geserHari(value, 0) === value;
  if (!ok) throw Object.assign(new Error(`${name} harus berformat YYYY-MM-DD.`), { status: 422 });
  return value;
}

function bintangUlasan(r) {
  if (r.rating) return r.rating;
  const aspek = [r.rating_rasa, r.rating_harga, r.rating_pelayanan, r.rating_tempat].filter((v) => v !== null);
  return aspek.length ? Math.round(aspek.reduce((a, b) => a + b, 0) / aspek.length) : 0;
}

export async function createWeeklyReport(req, res) {
  try {
    const to = bacaTanggal(req.body?.to, 'to') || hariIni();
    const from = bacaTanggal(req.body?.from, 'from') || geserHari(to, -6);
    if (from > to) throw Object.assign(new Error('from tidak boleh setelah to.'), { status: 422 });
    if (geserHari(from, MAKS_HARI - 1) < to) {
      throw Object.assign(new Error(`Periode laporan paling panjang ${MAKS_HARI} hari.`), { status: 422 });
    }

    const semuaUlasan = await findReviewsForReport(from, to);
    if (semuaUlasan.length === 0) {
      return res.status(422).json({ message: 'Belum ada ulasan berkomentar pada periode ini.' });
    }

    const reviews = semuaUlasan.slice(-MAKS_ULASAN_AI);

    const idsByText = new Map();
    for (const r of reviews) idsByText.set(r.text, [...(idsByText.get(r.text) || []), r.id]);

    const hasil = await mintaLaporanMingguan({
      periode: `${from} s.d. ${to}`,
      cabang: 'Gunung Anyar',
      ulasan: reviews.map((r) => ({ id: String(r.id), tanggal: r.date, bintang: bintangUlasan(r), teks: r.text })),
    });

    const simpan = await saveWeeklyReport({ from, to, hasil, idsByText });
    return res.status(201).json({
      id: simpan.id,
      period_start: from,
      period_end: to,
      total_reviews: Number(hasil.ringkasan.total_baru) || 0,
      negative_count: Number(hasil.ringkasan.negatif) || 0,
      positive_count: Number(hasil.ringkasan_positif?.positif) || 0,
      analyzed_reviews: simpan.dianalisis,
      skipped_reviews: semuaUlasan.length - reviews.length,
      suggestions_created: simpan.saranDibuat,
      llm_note: hasil.catatan_saran || hasil.catatan_saran_positif || null,
    });
  } catch (error) {
    if (error instanceof AiError || error.status === 422) {
      return res.status(error.status).json({ message: error.message });
    }
    throw error;
  }
}

function kataKunciKeluhan(result) {
  const hitung = new Map();
  for (const [topik, items] of Object.entries(result?.negatif_per_topik || {})) {
    for (const item of Array.isArray(items) ? items : []) {
      const sudah = new Set(); // satu ulasan dihitung sekali per kata
      for (const k of item.shap_topik?.kata || []) {
        if (!(k.nilai > 0)) continue;
        const kata = String(k.kata).toLowerCase().replace(/[^\p{L}\p{N}]+/gu, '');
        if (kata.length < 3 || sudah.has(kata)) continue;
        sudah.add(kata);
        const kunci = `${kata}|${topik}`;
        hitung.set(kunci, (hitung.get(kunci) || 0) + 1);
      }
    }
  }
  return [...hitung.entries()]
    .map(([kunci, jumlah]) => ({ kata: kunci.split('|')[0], topik: kunci.split('|')[1], jumlah }))
    .sort((a, b) => b.jumlah - a.jumlah || a.kata.localeCompare(b.kata))
    .slice(0, 10);
}

export async function getLatestReport(req, res) {
  const row = await findLatestReport();
  if (!row) return res.status(404).json({ message: 'Belum ada laporan mingguan.' });

  const r = row.result || {};
  return res.json({
    id: row.id,
    period_start: row.period_start,
    period_end: row.period_end,
    created_at: row.created_at,
    total_reviews: row.total_reviews,
    negative_count: row.negative_count,
    positive_count: row.positive_count,
    complaints_per_topic: r.ringkasan?.per_topik || {},
    praise_per_topic: r.ringkasan_positif?.per_topik || {},
    keywords: kataKunciKeluhan(r),
    priority_suggestions: r.saran_deepseek?.saran_prioritas || [],
    promotion_ideas: r.saran_deepseek_positif?.ide_promosi || [],
    llm_note: row.llm_note,
  });
}