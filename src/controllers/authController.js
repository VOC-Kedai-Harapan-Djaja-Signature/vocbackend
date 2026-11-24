import bcrypt from 'bcryptjs';
import jwt from 'jsonwebtoken';
import { findByEmail, findById, updatePassword } from '../models/userModel.js';

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

// PATCH /api/me/password   body: { current_password, new_password }
// Mengganti password akun yang sedang login.
export async function changePassword(req, res) {
  const { current_password: lama, new_password: baru } = req.body ?? {};
  if (typeof lama !== 'string' || typeof baru !== 'string' || !lama || !baru) {
    return res.status(422).json({ message: 'Password lama dan password baru wajib diisi.' });
  }
  if (baru.length < 8) {
    return res.status(422).json({ message: 'Password baru minimal 8 karakter.' });
  }
  // bcrypt hanya membaca 72 byte pertama. Lebih dari itu ditolak,
  // supaya tidak ada bagian password yang diam-diam diabaikan.
  if (Buffer.byteLength(baru, 'utf8') > 72) {
    return res.status(422).json({ message: 'Password baru terlalu panjang (maksimal 72 karakter).' });
  }
  if (baru === lama) {
    return res.status(422).json({ message: 'Password baru harus berbeda dari password lama.' });
  }

  const user = await findById(req.user.id);
  if (!user) {
    return res.status(401).json({ message: 'Akun tidak ditemukan. Silakan login ulang.' });
  }
  // Sengaja 422, bukan 401: dashboard otomatis logout bila menerima 401.
  if (!(await bcrypt.compare(lama, user.password))) {
    return res.status(422).json({ message: 'Password lama salah.' });
  }

  await updatePassword(user.id, await bcrypt.hash(baru, 12));
  return res.json({ message: 'Password berhasil diganti.' });
}