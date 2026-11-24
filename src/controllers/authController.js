import bcrypt from 'bcryptjs';
import jwt from 'jsonwebtoken';
import { findByEmail } from '../models/userModel.js';

// Dipakai saat email tidak terdaftar, supaya lama prosesnya sama dengan
// email yang terdaftar dan orang tidak bisa menebak email mana yang ada.
const DUMMY_HASH = bcrypt.hashSync('bukan-password-siapa-pun', 10);

// POST /api/login
export async function login(req, res) {
  const { email, password } = req.body ?? {};
  if (typeof email !== 'string' || typeof password !== 'string' || !email.trim() || !password) {
    return res.status(422).json({ message: 'Email dan password wajib diisi.' });
  }

  const user = await findByEmail(email.trim().toLowerCase());
  const passwordMatches = await bcrypt.compare(password, user ? user.password : DUMMY_HASH);
  if (!user || !passwordMatches) {
    return res.status(401).json({ message: 'Email atau password salah.' });
  }

  const token = jwt.sign(
    { sub: String(user.id), name: user.name, role: user.role },
    process.env.JWT_SECRET,
    { algorithm: 'HS256', expiresIn: process.env.JWT_EXPIRES_IN || '8h' },
  );
  return res.json({ token });
}
