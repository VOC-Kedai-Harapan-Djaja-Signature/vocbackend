import jwt from 'jsonwebtoken';

// Memastikan pemanggil sudah login: membaca "Authorization: Bearer <token>".
export function authenticate(req, res, next) {
  const [scheme, token] = (req.get('Authorization') || '').split(' ');
  if (scheme !== 'Bearer' || !token) {
    return res.status(401).json({ message: 'Anda belum login.' });
  }

  try {
    const payload = jwt.verify(token, process.env.JWT_SECRET, { algorithms: ['HS256'] });
    req.user = { id: Number(payload.sub), name: payload.name, role: payload.role };
    return next();
  } catch {
    return res.status(401).json({ message: 'Sesi tidak valid atau sudah berakhir. Silakan login ulang.' });
  }
}

export function requireRole(...roles) {
  return (req, res, next) => {
    if (!roles.includes(req.user?.role)) {
      return res.status(403).json({ message: 'Anda tidak punya akses untuk tindakan ini.' });
    }
    return next();
  };
}