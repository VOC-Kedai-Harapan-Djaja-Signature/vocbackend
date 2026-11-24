import 'dotenv/config';
import express from 'express';
import helmet from 'helmet';
import cors from 'cors';
import bcrypt from 'bcryptjs';
import swaggerUi from 'swagger-ui-express';
import pool from './src/config/db.js';
import { swaggerSpec } from './src/config/swagger.js';
import { createIfMissing } from './src/models/userModel.js';
import authRoutes from './src/routes/authRoutes.js';
import reviewRoutes from './src/routes/reviewRoutes.js';
import settingRoutes from './src/routes/settingRoutes.js';
import reportRoutes from './src/routes/reportRoutes.js';
import { nyalakanAi, statusAi } from './src/services/aiBridge.js';
import suggestionRoutes from './src/routes/suggestionRoutes.js';

const required = ['POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_DB', 'JWT_SECRET', 'IP_HASH_SALT'];
const missing = required.filter((name) => !process.env[name]);
if (missing.length > 0) {
  console.error(`Variabel berikut belum diisi di .env: ${missing.join(', ')}`);
  process.exit(1);
}

const app = express();
const port = Number(process.env.PORT) || 3000;
const corsOrigins = (process.env.CORS_ORIGIN || '').split(',').map((origin) => origin.trim()).filter(Boolean);

app.disable('x-powered-by');
// Di belakang proxy, alamat pengirim asli ada di header X-Forwarded-For.
app.set('trust proxy', Number(process.env.TRUST_PROXY) || 0);

app.use(helmet());
// Hanya alamat di CORS_ORIGIN yang boleh memanggil API dari browser.
app.use(cors({
  origin: corsOrigins.length > 0 ? corsOrigins : false,
  methods: ['GET', 'POST', 'PATCH'],
  allowedHeaders: ['Content-Type', 'Authorization', 'ngrok-skip-browser-warning'],
}));
app.use(express.json({ limit: '10kb' }));

app.use('/api/docs', swaggerUi.serve, swaggerUi.setup(swaggerSpec));
app.use('/api', authRoutes);
app.use('/api', reviewRoutes);
app.use('/api', settingRoutes);
app.use('/api', reportRoutes);
app.use('/api', suggestionRoutes);

app.get('/api/health', (req, res) => {
  res.json({
    ok: true,
    ai: statusAi(),
    llm: Boolean(process.env.OPENROUTER_API_KEY || process.env.ORCAROUTER_API_KEY),
  });
});

app.use((req, res) => {
  res.status(404).json({ message: 'Endpoint tidak ditemukan.' });
});

// Error handler global: jawaban selalu JSON, dan rincian kesalahan server
// hanya masuk log, tidak pernah dikirim ke pemanggil.
// eslint-disable-next-line no-unused-vars
app.use((error, req, res, next) => {
  if (res.headersSent) return next(error);
  if (error.type === 'entity.parse.failed') {
    return res.status(400).json({ message: 'Format JSON tidak valid.' });
  }
  if (error.type === 'entity.too.large') {
    return res.status(413).json({ message: 'Data yang dikirim terlalu besar.' });
  }
  console.error(`[${new Date().toISOString()}] ${req.method} ${req.originalUrl}`, error);
  return res.status(500).json({ message: 'Terjadi kesalahan pada server.' });
});

// Membuat akun admin pertama dari .env bila belum ada.
async function seedKepalaCabang() {
  const { KC_NAME = 'Kepala Cabang', KC_EMAIL, KC_PASSWORD } = process.env;
  if (!KC_EMAIL || !KC_PASSWORD) return;

  const created = await createIfMissing({
    name: KC_NAME,
    email: KC_EMAIL.trim().toLowerCase(),
    password: await bcrypt.hash(KC_PASSWORD, 12),
    role: 'kepala_cabang',
  });
  if (created) console.log(`Akun Kepala Cabang ${KC_EMAIL} dibuat.`);
}

// Database harus sudah siap sebelum aplikasi menerima permintaan.
try {
  await pool.query('SELECT 1');
  await seedKepalaCabang();
} catch (error) {
  console.error('Gagal menyiapkan database:', error.message);
  process.exit(1);
}

const server = app.listen(port, (error) => {
  if (error) throw error;
  console.log(`VoC API berjalan di port ${port}. Dokumentasi: /api/docs`);
  nyalakanAi();
});

// Mati dengan rapi saat container dihentikan.
function shutdown() {
  server.close(async () => {
    await pool.end().catch(() => {});
    process.exit(0);
  });
  setTimeout(() => process.exit(1), 10000).unref();
}
process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);
