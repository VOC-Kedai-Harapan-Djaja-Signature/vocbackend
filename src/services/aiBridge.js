import { spawn } from 'node:child_process';
import path from 'node:path';
import readline from 'node:readline';
import { fileURLToPath } from 'node:url';

const FOLDER_AI = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..', 'python');
const PYTHON_BIN = process.env.PYTHON_BIN || 'python3';
const BATAS_MEMUAT_MS = 120000;

export class BridgeError extends Error {}

let proses = null;
let menyala = null;
let antrean = [];
let status = 'mati'; 

function hentikan(alasan) {
  if (proses) proses.kill();
  proses = null;
  menyala = null;
  status = 'mati';
  const menunggu = antrean;
  antrean = [];
  for (const p of menunggu) {
    clearTimeout(p.timer);
    p.reject(new BridgeError(alasan));
  }
}

function nyalakan() {
  if (menyala) return menyala;
  status = 'memuat';
  menyala = new Promise((resolve, reject) => {
    const p = spawn(PYTHON_BIN, ['predict_bridge.py'], {
      cwd: FOLDER_AI,
      env: { ...process.env, PYTHONWARNINGS: 'ignore', PYTHONIOENCODING: 'utf-8', PYTHONUNBUFFERED: '1' },
    });
    proses = p;
    let siap = false;
    const logError = [];

    const gagal = (pesan) => {
      reject(new BridgeError(pesan));
      if (proses === p) hentikan(pesan);
    };
    const timerMemuat = setTimeout(() => gagal('AI terlalu lama memuat model.'), BATAS_MEMUAT_MS);

    p.stdin.on('error', () => {});
    p.stderr.on('data', (data) => {
      logError.push(String(data));
      if (logError.length > 20) logError.shift();
    });
    p.on('error', (error) => {
      clearTimeout(timerMemuat);
      gagal(`Python tidak bisa dijalankan (${error.code || error.message}). Periksa PYTHON_BIN.`);
    });
    p.on('exit', (code) => {
      clearTimeout(timerMemuat);
      if (!siap) console.error('[ai] bridge berhenti sebelum siap:\n' + logError.join('').slice(-2000));
      gagal(`Proses AI berhenti (kode ${code}).`);
    });

    readline.createInterface({ input: p.stdout }).on('line', (baris) => {
      let data;
      try {
        data = JSON.parse(baris);
      } catch {
        return;
      }
      if (!siap) {
        if (data && data.siap === true) {
          siap = true;
          status = 'siap';
          clearTimeout(timerMemuat);
          resolve();
        }
        return;
      }
      const permintaan = antrean.shift();
      if (permintaan) {
        clearTimeout(permintaan.timer);
        permintaan.resolve(data);
      }
    });
  });
  return menyala;
}

export async function tanyaAi(pesan, batasMs) {
  await nyalakan();
  if (!proses) throw new BridgeError('Proses AI tidak berjalan.');
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => hentikan('AI terlalu lama menjawab.'), batasMs);
    antrean.push({ resolve, reject, timer });
    proses.stdin.write(`${JSON.stringify(pesan)}\n`);
  });
}

export function nyalakanAi() {
  nyalakan().catch((error) => console.error('[ai]', error.message));
}

export function statusAi() {
  return status;
}