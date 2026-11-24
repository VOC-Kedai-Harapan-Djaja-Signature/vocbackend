import { BridgeError, tanyaAi } from './aiBridge.js';

export class AiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

export async function mintaLaporanMingguan(payload) {
    const timeout = Number(process.env.AI_TIMEOUT_MS) || 240000;

    let hasil;
    try {
        hasil = await tanyaAi({ aksi: 'laporan', ...payload }, timeout);
  } catch (error) {
    if (error instanceof BridgeError) {
      throw new AiError(`Layanan AI tidak tersedia: ${error.message}`, 503);
    }
    throw error;
  }

  if (hasil && hasil.error) {
    throw new AiError(`AI gagal membuat laporan: ${hasil.error}`, 502);
  }
  if (!hasil || typeof hasil.ringkasan !== 'object' || typeof hasil.negatif_per_topik !== 'object') {
    throw new AiError('Jawaban layanan AI tidak sesuai format.', 502);
  }
  return hasil;
}