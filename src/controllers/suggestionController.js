import { completeSuggestion, findActiveSuggestions, findCompletedSuggestions } from '../models/suggestionModel.js';

export async function listSuggestions(req, res) {
  const status = req.query.status || 'aktif';
  if (status === 'aktif') {
    return res.json({ data: await findActiveSuggestions() });
  }
  if (status === 'selesai') {
    return res.json({ data: await findCompletedSuggestions(100) });
  }
  return res.status(422).json({ message: 'status harus aktif atau selesai.' });
}

export async function markSuggestionDone(req, res) {
  const id = Number(req.params.id);
  if (!Number.isInteger(id) || id < 1) {
    return res.status(422).json({ message: 'ID saran tidak valid.' });
  }

  const raw = req.body?.note;
  if (raw !== undefined && raw !== null && typeof raw !== 'string') {
    return res.status(422).json({ message: 'note harus berupa teks.' });
  }
  const note = typeof raw === 'string' ? raw.trim() : '';
  if (note.length > 300) {
    return res.status(422).json({ message: 'Catatan maksimal 300 karakter.' });
  }

  const { updated, suggestion } = await completeSuggestion(id, req.user.id, note || null);
  if (!suggestion) return res.status(404).json({ message: 'Saran tidak ditemukan.' });
  if (!updated) {
    if (suggestion.status === 'selesai') {
      return res.status(409).json({ message: 'Saran ini sudah ditandai selesai.' });
    }
    return res.status(422).json({ message: 'Hanya saran perbaikan yang bisa ditandai selesai.' });
  }
  return res.json(suggestion);
}