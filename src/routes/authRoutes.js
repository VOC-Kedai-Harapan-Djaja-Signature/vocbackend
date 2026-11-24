import { Router } from 'express';
import { rateLimit } from 'express-rate-limit';
import { changePassword, login } from '../controllers/authController.js';
import { authenticate } from '../middlewares/authMiddleware.js';

const router = Router();

// Paling banyak 10 percobaan login per 15 menit dari satu alamat.
const loginLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  limit: 10,
  standardHeaders: 'draft-7',
  legacyHeaders: false,
  message: { message: 'Terlalu banyak percobaan login. Coba lagi nanti.' },
});

// Paling banyak 10 percobaan ganti password per 15 menit untuk satu akun.
const passwordLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  limit: 10,
  standardHeaders: 'draft-7',
  legacyHeaders: false,
  keyGenerator: (req) => `akun-${req.user.id}`,
  message: { message: 'Terlalu banyak percobaan ganti password. Coba lagi nanti.' },
});

router.post('/login', loginLimiter, login);
router.patch('/me/password', authenticate, passwordLimiter, changePassword);

export default router;