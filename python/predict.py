# VoC Kedai Harapan Djaja — fungsi prediksi sentimen + topik buat back-end (Trias)
# Model utama: TF-IDF + Logistic Regression (balanced), dilatih pada 1.339
# ulasan berteks berlabel dari 4 cabang (Riverside + Prapen + Sky Garden +
# Wadungasri; label dari bintang). Ringan, jalan lokal tanpa API eksternal
# dan tanpa GPU — cukup joblib + scikit-learn.
#
# Cara pakai:
#     from predict import prediksi_sentimen, prediksi_topik, prediksi_lengkap
#     prediksi_lengkap("makanannya enak, tempatnya nyaman")
#     # {'sentimen': 'Puas',
#     #  'probabilitas_sentimen': {'Puas': 0.60, 'Tidak puas': 0.40},
#     #  'topik': 'tempat',
#     #  'probabilitas_topik': {'tempat': 0.49, 'rasa': 0.22, ...},
#     #  'model': 'gabungan'}
#
# Model 'gabungan' = utama (sejak 21 Nov 2026; 1.339 ulasan unik dari
# dataset berlabel 1.440 — biner 1.407, buang 68 duplikat teks persis).
# Model '333' = model lama (333 ulasan Riverside saja) — masih tersedia
# buat perbandingan. Model '66' = alternatif seimbang (66 ulasan, 33 Puas
# + 33 Tidak puas). Model topik dilatih pada 975 baris gabungan
# (293 label final Riverside + 682 ulasan cabang lain yang tepercaya) —
# lihat README_SERAH_TERIMA.md untuk angka evaluasinya.

import os

import joblib

_DIR = os.path.dirname(os.path.abspath(__file__))

MODEL_GABUNGAN = os.path.join(_DIR, "model_sentimen_gabungan.pkl")
MODEL_333 = os.path.join(_DIR, "model_333_tfidf_logreg.pkl")
# MODEL_UTAMA = model utama yang dipakai kalau tidak disebut model lain.
MODEL_UTAMA = MODEL_GABUNGAN
MODEL_SEIMBANG66 = os.path.join(_DIR, "model_seimbang66_tfidf_logreg.pkl")
MODEL_TOPIK = os.path.join(_DIR, "model_topik_gabungan_char_logreg.pkl")

_CACHE = {}


def _muat(path):
    """Muat model sekali lalu simpan di cache."""
    if path not in _CACHE:
        model = joblib.load(path)
        # Shim kompatibilitas: model yang dilatih di scikit-learn >= 1.7 tidak
        # menyimpan atribut `multi_class`, padahal `predict_proba` di
        # scikit-learn 1.6.1 masih membacanya. Nilai 'auto' aman untuk
        # klasifikasi biner (Puas / Tidak puas) dan tidak mengubah hasil.
        lr = model.steps[-1][1]
        if not hasattr(lr, "multi_class"):
            lr.multi_class = "auto"
        _CACHE[path] = model
    return _CACHE[path]


def prediksi_sentimen(teks, model="gabungan"):
    """Prediksi sentimen satu ulasan.

    Args:
        teks: teks ulasan pelanggan (str).
        model: "gabungan" (utama, default), "333" (model lama) atau
            "66" (alternatif seimbang).

    Returns:
        dict dengan kunci 'sentimen' ("Puas" / "Tidak puas"),
        'probabilitas' (dict per kelas, dibulatkan 4 desimal),
        dan 'model' (yang dipakai).

    Raises:
        ValueError: kalau teks kosong atau pilihan model tidak dikenal.
    """
    ulasan = (teks or "").strip()
    if not ulasan:
        raise ValueError("Teks ulasan kosong.")
    if model == "gabungan":
        path = MODEL_GABUNGAN
    elif model == "333":
        path = MODEL_333
    elif model == "66":
        path = MODEL_SEIMBANG66
    else:
        raise ValueError("Pilihan model harus 'gabungan', '333' atau '66'.")

    m = _muat(path)
    proba = m.predict_proba([ulasan])[0]
    return {
        "sentimen": str(m.predict([ulasan])[0]),
        "probabilitas": {
            str(k): round(float(v), 4) for k, v in zip(m.classes_, proba)
        },
        "model": model,
    }


def prediksi_topik(teks):
    """Prediksi topik utama satu ulasan.

    Model: TF-IDF huruf (char_wb 3-5 gram) + Logistic Regression
    (balanced), dilatih pada 975 baris (293 label topik final Riverside
    + 682 ulasan cabang lain Prapen/Sky Garden/Wadungasri yang tepercaya
    — OK + terverifikasi AI; Fase 4, 17 Nov 2026, dari total 1.369 baris
    cabang lain). Evaluasi 5-fold CV dengan test HANYA ulasan Riverside:
    akurasi 0,8020, macro-F1 0,7619, top-2 0,9829; recall harga 0,7000
    (7/10), tempat 0,8210, rasa 0,8194, pelayanan 0,7347. Lihat README
    untuk detailnya.

    Returns:
        dict dengan kunci 'topik' ("rasa" / "harga" / "pelayanan" /
        "tempat"), 'probabilitas' (dict per kelas), dan 'model'
        ("topik-gabungan").
    """
    ulasan = (teks or "").strip()
    if not ulasan:
        raise ValueError("Teks ulasan kosong.")
    m = _muat(MODEL_TOPIK)
    proba = m.predict_proba([ulasan])[0]
    return {
        "topik": str(m.predict([ulasan])[0]),
        "probabilitas": {
            str(k): round(float(v), 4) for k, v in zip(m.classes_, proba)
        },
        "model": "topik-gabungan",
    }


def prediksi_lengkap(teks, model="gabungan"):
    """Prediksi sentimen + topik satu ulasan sekaligus.

    Returns:
        dict dengan kunci 'sentimen', 'probabilitas_sentimen', 'topik',
        'probabilitas_topik', dan 'model' (model sentimen yang dipakai).
    """
    s = prediksi_sentimen(teks, model=model)
    t = prediksi_topik(teks)
    return {
        "sentimen": s["sentimen"],
        "probabilitas_sentimen": s["probabilitas"],
        "topik": t["topik"],
        "probabilitas_topik": t["probabilitas"],
        "model": s["model"],
    }


if __name__ == "__main__":
    for contoh in [
        "tempat ini bagus tapi agak kurang menarik",
        "pelayanannya lama banget, kecewa",
        "makanannya enak, tempatnya nyaman",
    ]:
        print(repr(contoh), "->", prediksi_lengkap(contoh))
