import { findSettings, saveSettings } from '../models/settingModel.js';

const AMBANG_MIN = 2;
const AMBANG_MAX = 25;
const AMBANG_BAWAAN = 5;
const INTERVAL = ['mingguan', '2_mingguan', '3_mingguan', 'bulanan'];

function toApi(settings) {
  const ambang = Number(settings.ambang_saran);
  return {
    suggestion_threshold: Number.isInteger(ambang) ? ambang : AMBANG_BAWAAN,
    suggestion_interval: INTERVAL.includes(settings.interval_saran) ? settings.interval_saran : 'mingguan',
  };
}

export async function showSettings(req, res) {
  return res.json(toApi(await findSettings()));
}

export async function updateSettings(req, res) {
  const body = req.body ?? {};
  const changes = {};

  if (body.suggestion_threshold !== undefined) {
    const ambang = body.suggestion_threshold;
    if (!Number.isInteger(ambang) || ambang < AMBANG_MIN || ambang > AMBANG_MAX) {
      return res.status(422).json({ message: `Ambang saran harus angka ${AMBANG_MIN} sampai ${AMBANG_MAX}.` });
    }
    changes.ambang_saran = ambang;
  }

  if (body.suggestion_interval !== undefined) {
    if (!INTERVAL.includes(body.suggestion_interval)) {
      return res.status(422).json({ message: `Interval saran harus salah satu dari: ${INTERVAL.join(', ')}.` });
    }
    changes.interval_saran = body.suggestion_interval;
  }

  if (Object.keys(changes).length === 0) {
    return res.status(422).json({ message: 'Isi suggestion_threshold dan/atau suggestion_interval.' });
  }

  await saveSettings(changes, req.user.id);
  return res.json(toApi(await findSettings()));
}