import crypto from 'node:crypto';
import { createReview, findReviews, setResponded } from '../models/reviewModel.js';

const ASPEK = ['rasa', 'harga', 'pelayanan', 'tempat'];
const GENDER = ['laki-laki', 'perempuan'];
const SUMBER_MANUAL = ['qr', 'google_maps', 'social_media'];

class InputError extends Error {}

function readText(value, label, max) {
  if (value === undefined || value === null) return null;
  if (typeof value !== 'string') throw new InputError(`${label} harus berupa teks.`);
  const text = value.trim();
  if (text === '') return null;
  if (text.length < 3 || text.length > max) {
    throw new InputError(`${label} harus 3 sampai ${max} karakter.`);
  }
  return text;
}

function readStars(value, label) {
  if (value === undefined || value === null) return null;
  if (!Number.isInteger(value) || value < 1 || value > 5) {
    throw new InputError(`Bintang ${label} harus angka 1 sampai 5.`);
  }
  return value;
}

function readGender(value) {
  if (value === undefined || value === null || value === '' || value === 'tidak_dijawab') return null;
  if (!GENDER.includes(value)) throw new InputError('Gender tidak dikenali.');
  return value;
}

function readAge(value) {
  if (value === undefined || value === null || value === '') return null;
  if (!Number.isInteger(value) || value < 10 || value > 90) {
    throw new InputError('Umur harus angka 10 sampai 90.');
  }
  return value;
}

function readReviewDate(value) {
  if (value === undefined || value === null || value === '') return null;
  const valid = typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value);
  const date = valid ? new Date(`${value}T00:00:00Z`) : null;
  if (!date || Number.isNaN(date.getTime()) || date.toISOString().slice(0, 10) !== value) {
    throw new InputError('Tanggal ulasan harus berformat YYYY-MM-DD.');
  }
  // Toleransi satu hari untuk perbedaan zona waktu.
  if (date.getTime() > Date.now() + 24 * 60 * 60 * 1000) {
    throw new InputError('Tanggal ulasan tidak boleh di masa depan.');
  }
  return value;
}

function readTopic(value) {
  if (value === undefined || value === null || value === '') return null;
  const topic = typeof value === 'string' ? value.trim().toLowerCase() : '';
  if (!ASPEK.includes(topic)) throw new InputError('Topik harus rasa, harga, pelayanan, atau tempat.');
  return topic;
}

function hashIp(ip) {
  return crypto
    .createHmac('sha256', process.env.IP_HASH_SALT)
    .update(String(ip || 'unknown'))
    .digest('hex');
}

function handleInputError(error, res) {
  if (error instanceof InputError) {
    return res.status(422).json({ message: error.message });
  }
  throw error;
}

export async function createPublicReview(req, res) {
  const body = req.body ?? {};
  try {
    const text = readText(body.comment ?? body.text, 'Komentar', 2000);
    const rawRatings = body.ratings && typeof body.ratings === 'object' ? body.ratings : {};
    const ratings = Object.fromEntries(ASPEK.map((aspek) => [aspek, readStars(rawRatings[aspek], aspek)]));
    const gender = readGender(body.gender);
    const age = readAge(body.age);

    if (!text && ASPEK.every((aspek) => ratings[aspek] === null)) {
      throw new InputError('Isi minimal satu bintang atau komentar.');
    }

    const id = await createReview({ source: 'qr', text, ratings, gender, age, ipHash: hashIp(req.ip) });
    return res.status(201).json({ id, message: 'Terima kasih, masukan Anda sudah kami terima.' });
  } catch (error) {
    return handleInputError(error, res);
  }
}

export async function createManualReview(req, res) {
  const body = req.body ?? {};
  try {
    const text = readText(body.text, 'Ulasan', 2000);
    if (!text) throw new InputError('Ulasan wajib diisi, 3 sampai 2000 karakter.');
    if (!SUMBER_MANUAL.includes(body.source)) {
      throw new InputError('Sumber harus google_maps atau social_media.');
    }
    const rating = readStars(body.rating, 'ulasan');
    if (rating === null) throw new InputError('Bintang ulasan wajib diisi, 1 sampai 5.');
    const reviewDate = readReviewDate(body.review_date);
    const topic = readTopic(body.topic);

    const id = await createReview({ source: body.source, text, rating, reviewDate, topic });
    return res.status(201).json({ id });
  } catch (error) {
    return handleInputError(error, res);
  }
}

function readQueryDate(value, name) {
  if (value === undefined || value === '') return null;
  const valid = typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value);
  const date = valid ? new Date(`${value}T00:00:00Z`) : null;
  if (!date || Number.isNaN(date.getTime()) || date.toISOString().slice(0, 10) !== value) {
    throw new InputError(`${name} harus berformat YYYY-MM-DD.`);
  }
  return value;
}

function readQueryInt(value, name, { min, max, fallback }) {
  if (value === undefined || value === '') return fallback;
  const number = Number(value);
  if (!Number.isInteger(number) || number < min || number > max) {
    throw new InputError(`${name} harus angka ${min} sampai ${max}.`);
  }
  return number;
}

function hitungRataRata(row) {
  const bintang = row.source === 'qr'
    ? [row.rating_rasa, row.rating_harga, row.rating_pelayanan, row.rating_tempat].filter((v) => v !== null)
    : [row.rating].filter((v) => v !== null);
  if (bintang.length === 0) return null;
  const rata = bintang.reduce((a, b) => a + b, 0) / bintang.length;
  return Math.round(rata * 10) / 10;
}

function tentukanKepuasan(row, rataRata) {
  if (row.ai_sentiment) return { satisfied: row.ai_sentiment === 'puas', basis: 'ai' };
  if (rataRata !== null) return { satisfied: rataRata >= 4, basis: 'bintang' };
  return { satisfied: null, basis: null };
}

function toApi(row) {
  const rataRata = hitungRataRata(row);
  const kepuasan = tentukanKepuasan(row, rataRata);
  return {
    id: row.id,
    source: row.source,
    date: row.date,
    created_at: row.created_at,
    text: row.text,
    gender: row.gender,
    age: row.age,
    ratings: {
      rasa: row.rating_rasa,
      harga: row.rating_harga,
      pelayanan: row.rating_pelayanan,
      tempat: row.rating_tempat,
    },
    rating: row.rating,
    average_rating: rataRata,
    satisfied: kepuasan.satisfied,
    satisfied_basis: kepuasan.basis,
    topics: row.topics,
    menus: row.menus,
    responded: row.responded_at !== null,
    responded_at: row.responded_at,
    responded_by: row.responded_by_name,
  };
}

export async function listReviews(req, res) {
  try {
    const q = req.query;
    const from = readQueryDate(q.from, 'from');
    const to = readQueryDate(q.to, 'to');
    if (from && to && from > to) throw new InputError('from tidak boleh setelah to.');

    const source = q.source || null;
    if (source && !SEMUA_SUMBER.includes(source)) {
      throw new InputError('source harus qr, google_maps, atau social_media.');
    }
    const topic = q.topic || null;
    if (topic && !ASPEK.includes(topic)) {
      throw new InputError('topic harus rasa, harga, pelayanan, atau tempat.');
    }
    let responded = null;
    if (q.responded === 'true') responded = true;
    else if (q.responded === 'false') responded = false;
    else if (q.responded !== undefined && q.responded !== '') {
      throw new InputError('responded harus true atau false.');
    }
    const limit = readQueryInt(q.limit, 'limit', { min: 1, max: 1000, fallback: 500 });
    const offset = readQueryInt(q.offset, 'offset', { min: 0, max: 1000000, fallback: 0 });

    const { rows, total } = await findReviews({ from, to, source, topic, responded, limit, offset });
    return res.json({ data: rows.map(toApi), total, limit, offset });
  } catch (error) {
    return handleInputError(error, res);
  }
}

export async function respondReview(req, res) {
  try {
    const id = Number(req.params.id);
    if (!Number.isInteger(id) || id < 1) throw new InputError('ID ulasan tidak valid.');
    const responded = req.body?.responded;
    if (typeof responded !== 'boolean') throw new InputError('responded harus true atau false.');

    const row = await setResponded(id, responded, req.user.id);
    if (!row) return res.status(404).json({ message: 'Ulasan tidak ditemukan.' });

    return res.json({ id: row.id, responded: row.responded_at !== null, responded_at: row.responded_at });
  } catch (error) {
    return handleInputError(error, res);
  }
}