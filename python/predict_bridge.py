# VoC Kedai Harapan Djaja — bridge Python <-> Express (v2.4)
# Proses ini jalan terus selama server Express hidup. Model dimuat SEKALI
# di awal (biar prediksi cepat), lalu setiap baris JSON yang masuk lewat
# stdin dijawab dengan satu baris JSON ke stdout.
#
# Model utama ("gabungan") = model notebook baru (multi-topik, dilatih
# dari pool 1.877 + 288 terverifikasi AI; file voc_model.joblib +
# voc_pipeline.py). Model lama 333/66 tetap tersedia untuk perbandingan
# (pakai predict.py + .pkl lama).
#
# Protokol (satu JSON per baris):
#   masuk : {"teks": "makanannya enak", "model": "gabungan"}
#   keluar: {"sentimen": "Puas", "probabilitas_sentimen": {...},
#            "topik": "rasa", "probabilitas_topik": {...},
#            "topik_teratas2": [["rasa", 0.51], ["tempat", 0.22]],
#            "topik_semua": ["rasa", "tempat"], "klausa": [...],
#            "kata_pendorong": [{"kata": "enak", "bobot": 1.23}, ...],
#            "shap_sentimen": {...}, "shap_topik": {...},
#            "model": "gabungan", "model_info": {...}}
#   gagal : {"error": "pesan kesalahan"}
#
# "kata_pendorong", "shap_sentimen" dan "shap_topik" untuk model baru
# dihitung dari SHAP eksak model linier (voc_pipeline.shap_per_kata,
# sama dengan shap.LinearExplainer — sudah dibuktikan True di notebook).
# Untuk model lama, SHAP dihitung seperti sebelumnya lewat
# laporan_mingguan.tambah_shap.
#
# Aksi "laporan": {"aksi": "laporan", "periode": "...",
#   "ulasan": ["teks1", ...]} -> laporan mingguan lengkap
#   (klasifikasi + SHAP per ulasan + saran Particle-1 via OpenRouter,
#   cadangan DeepSeek via OrcaRouter; tanpa kunci API, sarannya None).
#   Bentuk jawabannya SAMA seperti v2.2 (ringkasan, negatif_per_topik,
#   saran_deepseek, ...) supaya client React tidak perlu diubah.

import json
import os
import sys

import joblib

import voc_pipeline as vp

from laporan_mingguan import tambah_shap
from predict import MODEL_TOPIK, _muat, prediksi_lengkap

_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_BARU = os.path.join(_DIR, "voc_model.joblib")
TOPIK_URUT = ["tempat", "pelayanan", "rasa", "harga"]

_M_BARU = None


def muat_baru():
    """Muat model notebook baru (sekali, lalu dipakai terus)."""
    global _M_BARU
    if _M_BARU is None:
        _M_BARU = joblib.load(MODEL_BARU)
    return _M_BARU


# ------------------------------------------------------------------ model lama
def kata_pendorong(teks, model_path, sentimen_prediksi, jumlah=5):
    """Kata yang paling mendorong prediksi sentimen (koefisien model).

    Model sentimen biner: coef_ milik kelas ke-2 (classes_[1]).
    Skor keputusan = coef . x + intercept; positif -> kelas ke-2.
    """
    try:
        model = _muat(model_path)
        tfidf = model.steps[0][1]
        lr = model.steps[-1][1]
        x = tfidf.transform([teks])
        coef = lr.coef_[0]
        kelas = list(model.classes_)
        # Arah: kalau prediksi = kelas ke-2, kata pendorong = kontribusi
        # positif terbesar; kalau kelas ke-1, sebaliknya.
        arah = 1 if str(sentimen_prediksi) == str(kelas[1]) else -1
        kontribusi = x.multiply(coef * arah).tocoo()
        nama_fitur = tfidf.get_feature_names_out()
        pasangan = [
            (str(nama_fitur[i]), round(float(v), 3))
            for i, v in zip(kontribusi.col, kontribusi.data)
            if v > 0
        ]
        pasangan.sort(key=lambda p: p[1], reverse=True)
        return [
            {"kata": kata, "bobot": bobot} for kata, bobot in pasangan[:jumlah]
        ]
    except Exception:
        return []


def prediksi_lama(teks, model):
    """Prediksi pakai model lama (333 / 66) — sama seperti v2.2."""
    hasil = prediksi_lengkap(teks, model=model)
    prob_topik = hasil["probabilitas_topik"]
    teratas2 = sorted(prob_topik.items(), key=lambda kv: kv[1], reverse=True)[:2]
    hasil["topik_teratas2"] = [[k, v] for k, v in teratas2]
    if model == "66":
        from predict import MODEL_SEIMBANG66

        path = MODEL_SEIMBANG66
    else:
        from predict import MODEL_333

        path = MODEL_333
    hasil["kata_pendorong"] = kata_pendorong(
        teks, path, hasil["sentimen"]
    )
    try:
        u = {"teks": teks,
             "sentimen": hasil["sentimen"],
             "prob_sentimen": hasil["probabilitas_sentimen"][hasil["sentimen"]],
             "topik": hasil["topik"],
             "prob_topik": hasil["probabilitas_topik"][hasil["topik"]]}
        tambah_shap([u], _muat(path), _muat(MODEL_TOPIK), latar_nol=True)
        hasil["shap_sentimen"] = u["shap_sentimen"]
        hasil["shap_topik"] = u["shap_topik"]
    except Exception:
        hasil["shap_sentimen"] = None
        hasil["shap_topik"] = None
    return hasil


# ------------------------------------------------------------------ model baru
def _kata_ke_arah(shap_list, arah, jumlah):
    """Ambil kata SHAP yang mendorong ke arah prediksi (nilai > 0 ke
    arah itu), diurutkan dari yang paling besar. shap_list berisi
    (kata, phi); phi > 0 mendorong ke Puas, phi < 0 ke Tidak puas."""
    out = []
    for w, phi in shap_list:
        v = phi * arah
        if v > 0:
            out.append({"kata": w, "bobot": round(float(v), 3)})
    out.sort(key=lambda d: d["bobot"], reverse=True)
    return out[:jumlah]


def prediksi_baru(teks):
    """Prediksi pakai model notebook baru (multi-topik, 288 terverifikasi
    AI). Bentuk jawaban disamakan dengan model lama supaya client tidak
    perlu diubah; ditambah 'topik_semua' (semua topik yang terdeteksi),
    'klausa' (analisis per klausa) dan 'model_info'."""
    M = muat_baru()
    rows = [{"id": "u001", "teks": teks, "bintang": None, "tanggal": ""}]
    h = vp.analisis_ulasan(rows, M)[0]
    sentimen = "Puas" if h["sentimen"] == "positif" else "Tidak puas"
    p_pos = float(h["p_positif"])
    prob_sent = {"Puas": round(p_pos, 4), "Tidak puas": round(1.0 - p_pos, 4)}
    p_top = {k: round(float(v), 4) for k, v in h["p_topik"].items()}
    topik = max(p_top, key=p_top.get)
    teratas2 = sorted(p_top.items(), key=lambda kv: kv[1], reverse=True)[:2]
    arah = 1 if sentimen == "Puas" else -1
    pendorong = _kata_ke_arah(h["shap_ulasan"], arah, 5)
    shap_sent = {
        "metode": "shap",
        "kata": [{"kata": d["kata"], "nilai": d["bobot"]} for d in pendorong[:3]],
    }
    # SHAP topik: kontribusi kata ke topik teratas (koefisien model topik).
    shap_top = None
    try:
        st = vp.shap_per_kata(h["teks_normal"], M["vec"], M["coef_topik"][topik],
                              M["mean_x"], top=8, buang_stopword=True)
        kata_top = [{"kata": w, "nilai": round(float(phi), 3)}
                    for w, phi in st if phi > 0][:3]
        shap_top = {"metode": "shap", "kata": kata_top}
    except Exception:
        shap_top = None
    return {
        "sentimen": sentimen,
        "probabilitas_sentimen": prob_sent,
        "topik": topik,
        "probabilitas_topik": p_top,
        "topik_teratas2": [[k, v] for k, v in teratas2],
        "topik_semua": h["topik"],
        "klausa": h["klausa"],
        "kata_pendorong": pendorong,
        "shap_sentimen": shap_sent,
        "shap_topik": shap_top,
        "model": "gabungan",
        "model_info": {
            "nama": "notebook baru (multi-topik, 288 terverifikasi AI)",
            "versi": M.get("versi"),
            "n_latih": M.get("n_latih"),
            "n_gold": M.get("n_gold"),
            "akurasi_sentimen_oof": round(float(M.get("akurasi_sentimen_oof", 0)), 4),
            "akurasi_topik_oof": round(float(M.get("akurasi_topik_oof", 0)), 4),
            "akurasi_topik_gold": 0.8352,
            "catatan_gold": "gold = label verifikasi AI (V1), bukan manusia",
        },
    }


# ------------------------------------------------------- laporan (model baru)
def _llm_target():
    """Pilih LLM gratis: OpenRouter Particle-1 dulu, cadangan OrcaRouter
    DeepSeek. Mengembalikan (jenis, kunci, model) atau None."""
    if os.environ.get("OPENROUTER_API_KEY", "").strip():
        return ("openrouter", os.environ["OPENROUTER_API_KEY"].strip(),
                "particle-ai/particle-1:free")
    if os.environ.get("ORCAROUTER_API_KEY", "").strip():
        return ("orcarouter", os.environ["ORCAROUTER_API_KEY"].strip(),
                "deepseek/deepseek-v4.1-flash-free")
    return None


def _panggil_llm_baru(prompt):
    """Panggil LLM untuk satu prompt. Mengembalikan (hasil_dict, galat).
    OpenRouter lewat voc_pipeline.panggil_llm (requests); OrcaRouter
    lewat klien OpenAI (URL-nya beda, jadi tidak bisa pakai yang sama)."""
    target = _llm_target()
    if not target:
        return None, "BELUM ADA KUNCI API"
    jenis, kunci, model = target
    try:
        if jenis == "openrouter":
            hasil, _usage = vp.panggil_llm(prompt, kunci, model)
            return hasil, None
        from openai import OpenAI

        client = OpenAI(base_url="https://api.orcarouter.ai/v1", api_key=kunci)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": vp.SYSTEM_PROMPT},
                      {"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        return vp._parse_json(resp.choices[0].message.content), None
    except Exception as e:
        return None, f"Gagal memanggil LLM: {e}"


def _item_laporan_baru(u, t, M):
    """Satu ulasan dalam negatif/positif_per_topik (bentuk lama)."""
    p_pos = float(u["p_positif"])
    prob_sent = p_pos if u["sentimen"] == "positif" else 1.0 - p_pos
    arah = 1 if u["sentimen"] == "positif" else -1
    kata_s = [{"kata": w, "nilai": round(float(phi * arah), 3)}
              for w, phi in u["shap_ulasan"] if phi * arah > 0][:3]
    try:
        st = vp.shap_per_kata(u["teks_normal"], M["vec"], M["coef_topik"][t],
                              M["mean_x"], top=8, buang_stopword=True)
        kata_t = [{"kata": w, "nilai": round(float(phi), 3)}
                  for w, phi in st if phi > 0][:3]
    except Exception:
        kata_t = []
    return {
        "teks": u["teks"],
        "prob_sentimen": round(float(prob_sent), 4),
        "prob_topik": round(float(u["p_topik"][t]), 4),
        "shap_topik": {"metode": "shap", "kata": kata_t},
        "shap_sentimen": {"metode": "shap", "kata": kata_s},
    }


def buat_laporan_baru(periode, teks_list, cabang="Gunung Anyar"):
    """Laporan mingguan pakai model baru, tapi bentuk jawabannya SAMA
    seperti v2.2 supaya client React tidak perlu diubah."""
    M = muat_baru()
    rows = [{"id": f"u{i + 1:03d}", "teks": t, "bintang": None, "tanggal": ""}
            for i, t in enumerate(teks_list)]
    hasil = vp.analisis_ulasan(rows, M)
    grup = vp.kelompokkan_per_topik(hasil)
    negatif = [u for u in hasil if u["sentimen"] == "negatif"]
    positif = [u for u in hasil if u["sentimen"] == "positif"]
    per_topik_neg = {t: grup[f"{t}|negatif"]["jumlah_ulasan"] for t in TOPIK_URUT}
    per_topik_pos = {t: grup[f"{t}|positif"]["jumlah_ulasan"] for t in TOPIK_URUT}
    negatif_per_topik = {}
    positif_per_topik = {}
    for t in TOPIK_URUT:
        neg_t = [u for u in negatif if t in u["topik"]]
        neg_t.sort(key=lambda u: 1.0 - float(u["p_positif"]), reverse=True)
        negatif_per_topik[t] = [_item_laporan_baru(u, t, M) for u in neg_t]
        pos_t = [u for u in positif if t in u["topik"]]
        pos_t.sort(key=lambda u: float(u["p_positif"]), reverse=True)
        positif_per_topik[t] = [_item_laporan_baru(u, t, M) for u in pos_t]
    # LLM: dua prompt, masing-masing ditangani sendiri (kalau satu gagal,
    # yang lain tetap jalan — sama seperti v2.2).
    isi = dict(cabang=cabang, periode=periode, n_ulasan=len(hasil))
    saran, galat = _panggil_llm_baru(
        vp.PROMPT_KELUHAN.format(**isi, data=vp._data_prompt(grup, "negatif")))
    saran_pos, galat_pos = _panggil_llm_baru(
        vp.PROMPT_POSITIF.format(**isi, data=vp._data_prompt(grup, "positif")))

    def petakan_negatif(k):
        if not k:
            return None
        per = [{"topik": it.get("topik", ""),
                "keluhan_utama": it.get("masalah_utama", ""),
                "saran": it.get("saran_tindakan", [])}
               for it in k.get("keluhan", [])]
        urut = sorted(k.get("keluhan", []),
                      key=lambda it: ({"tinggi": 0, "sedang": 1, "rendah": 2}
                                      .get(it.get("prioritas", "sedang"), 1),
                                     -it.get("jumlah_ulasan", 0)))
        prior = []
        for it in urut:
            for s in it.get("saran_tindakan", []):
                if s not in prior:
                    prior.append(s)
                if len(prior) >= 3:
                    break
            if len(prior) >= 3:
                break
        return {"per_topik": per, "saran_prioritas": prior}

    def petakan_positif(p):
        if not p:
            return None
        per = [{"topik": it.get("topik", ""),
                "kekuatan": it.get("yang_dipuji", ""),
                "dipertahankan": it.get("cara_mempertahankan", "")}
               for it in p.get("kekuatan", [])]
        ide = [it.get("ide", "") for it in p.get("ide_promosi", [])
               if it.get("ide")]
        return {"per_topik": per, "ide_promosi": ide}

    return {
        "periode": periode,
        "cabang": cabang,
        "ringkasan": {"total_baru": len(hasil), "negatif": len(negatif),
                      "per_topik": per_topik_neg},
        "ringkasan_positif": {"positif": len(positif),
                              "per_topik": per_topik_pos},
        "negatif_per_topik": negatif_per_topik,
        "positif_per_topik": positif_per_topik,
        "saran_deepseek": petakan_negatif(saran),
        "catatan_saran": galat,
        "saran_deepseek_positif": petakan_positif(saran_pos),
        "catatan_saran_positif": galat_pos,
    }


# ------------------------------------------------------------------ penangan
def tangani(baris):
    try:
        data = json.loads(baris)
    except json.JSONDecodeError:
        return {"error": "Baris masuk bukan JSON yang valid."}
    if data.get("aksi") == "laporan":
        return tangani_laporan(data)
    teks = (data.get("teks") or "").strip()
    model = data.get("model") or "gabungan"
    if not teks:
        return {"error": "Teks ulasan kosong."}
    try:
        if model == "gabungan":
            return prediksi_baru(teks)
        return prediksi_lama(teks, model)
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Gagal memprediksi: {e}"}


def tangani_laporan(data):
    """Laporan mingguan: klasifikasi + SHAP + saran Particle-1/DeepSeek.

    Masuk: {"aksi": "laporan", "periode": "...", "cabang": "...",
            "ulasan": ["teks1", "teks2", ...]} (maks. 100 ulasan).
    Tanpa kunci API, saran LLM-nya None dengan catatan
    "BELUM ADA KUNCI API" — klasifikasinya tetap jalan.
    """
    periode = (data.get("periode") or "minggu ini").strip() or "minggu ini"
    cabang = (data.get("cabang") or "Gunung Anyar").strip() or "Gunung Anyar"
    mentah = data.get("ulasan") or []
    if not isinstance(mentah, list) or not mentah:
        return {"error": "Daftar ulasan kosong (kirim array 'ulasan')."}
    if len(mentah) > 100:
        return {"error": "Maksimal 100 ulasan per laporan."}
    teks_list = []
    for item in mentah:
        t = item.get("teks") if isinstance(item, dict) else item
        t = (t or "").strip() if isinstance(t, str) else ""
        if not t:
            return {"error": "Ada ulasan kosong di dalam daftar."}
        if len(t) > 2000:
            return {"error": "Ada ulasan lebih dari 2000 karakter."}
        teks_list.append(t)
    try:
        laporan = buat_laporan_baru(periode, teks_list, cabang=cabang)
    except Exception as e:
        return {"error": f"Gagal membuat laporan: {e}"}
    laporan["aksi"] = "laporan"
    laporan["ok"] = True
    return laporan


def main():
    # Muat semua model di awal supaya baris pertama tidak lambat.
    muat_baru()
    _muat(MODEL_TOPIK)
    from predict import MODEL_SEIMBANG66, MODEL_UTAMA

    _muat(MODEL_UTAMA)
    _muat(MODEL_SEIMBANG66)
    print(json.dumps({"siap": True}), flush=True)
    for baris in sys.stdin:
        baris = baris.strip()
        if not baris:
            continue
        print(json.dumps(tangani(baris), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
