import { Router } from 'express';
import { rateLimit } from 'express-rate-limit';
import { login } from '../controllers/authController.js';

const router = Router();

// Paling banyak 10 percobaan login per 15 menit dari satu alamat.
const loginLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  limit: 10,
  standardHeaders: 'draft-7',
  legacyHeaders: false,
  message: { message: 'Terlalu banyak percobaan login. Coba lagi nanti.' },
});

router.post('/login', loginLimiter, login);

export default router;
