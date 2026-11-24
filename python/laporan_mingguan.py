# Laporan mingguan ulasan — VoC Kedai Harapan Djaja (v2).
#
# Alur: JSON ulasan baru (1 minggu) -> model lokal TF-IDF + Logistic
# Regression (sentimen + topik, gratis, tanpa API) -> SHAP/koefisien
# menjelaskan kata pendukung tiap prediksi -> ulasan dikelompokkan per
# topik, NEGATIF dan POSITIF dipisah -> DUA prompt ringkasan dikirim ke
# LLM gratis (Particle-1 via OpenRouter; cadangan DeepSeek via
# OrcaRouter) -> output JSON terstruktur + laporan .md yang bisa dibaca
# manusia.
#
# Keputusan 17 Nov 2026: akurasi topik ~80% DITERIMA (berhenti kejar 90%).
# Sistem final: TF-IDF + LogReg + SHAP + LLM gratis, 1x seminggu,
# SATU hosting dengan web (bukan Streamlit, bukan hosting terpisah).
#
# Kenapa tidak kirim 50-100 ulasan mentah ke LLM: (1) hemat token dan
# cepat, (2) batas laju tier gratis (HTTP 429 kalau berlebihan),
# (3) LLM menerima ringkasan per topik + contoh, bukan teks penuh.
#
# LLM dipakai HANYA untuk merangkum dan memberi saran — klasifikasinya
# tetap dari model lokal, jadi kalau API mati pun laporannya tetap jalan
# (bagian saran tinggal kosong dengan catatan).
#
# Penjelasan prediksi (SHAP): untuk model linear, SHAP dihitung dengan
# shap.LinearExplainer pada classifier LogReg, background = vektor TF-IDF
# dari ulasan minggu ini (maks. 100). Kalau paket shap tidak terpasang,
# dipakai fallback koefisien (koefisien LogReg x nilai TF-IDF) — secara
# matematis sama dengan SHAP untuk model linear dengan background nol —
# dan metodenya ditulis jujur di output ("koefisien", bukan "shap").
# Model topik memakai TF-IDF huruf (char_wb 3-5), jadi nilai n-gram huruf
# diagregasi ke kata yang mengandungnya (dibagi proporsional bila sebuah
# n-gram muncul di lebih dari satu kata).
#
# Jalankan:  python3 laporan_mingguan.py input_mingguan.json
#   - tanpa kunci API: klasifikasi + SHAP + pengelompokan + kedua prompt
#     jalan, saran LLM dilewati ("BELUM ADA KUNCI API").
#   - dengan OPENROUTER_API_KEY: panggil Particle-1 (free) via OpenRouter.
#   - dengan ORCAROUTER_API_KEY (cadangan): panggil DeepSeek via OrcaRouter.
# Hasil: laporan_mingguan.json + laporan_mingguan.md +
#        prompt_deepseek_negatif.txt + prompt_deepseek_positif.txt
#        (nama file prompt masih "deepseek" dari versi awal; isinya
#        prompt yang sama untuk LLM mana pun.)
#
# Kunci API (gratis, tanpa kartu): daftar di https://openrouter.ai
# (Google/GitHub/email), buka halaman Keys, klik Create API Key, beri nama
# (mis. "voc-mingguan"), salin kuncinya SEKALI (awalan sk-or-v1-, tidak
# bisa dilihat lagi nanti), simpan sebagai OPENROUTER_API_KEY (environment
# variable di hosting web). JANGAN ditulis di kode. Batas model gratis:
# 20 request/menit, 50 request/hari (cukup: kita hanya butuh 2/minggu).
# Cadangan: kunci OrcaRouter (https://www.orcarouter.ai, GitHub, tier
# Hacker gratis, awalan sk-orca-) sebagai ORCAROUTER_API_KEY.

import json
import os
import sys

import joblib
import numpy as np

try:
    import shap as _shap
except Exception:  # paket shap tidak terpasang -> fallback koefisien
    _shap = None

MODEL_SENTIMEN = "model_sentimen_gabungan.pkl"        # di folder ini
MODEL_TOPIK = "model_topik_gabungan_char_logreg.pkl"    # di folder ini
TOPIK_URUT = ["tempat", "pelayanan", "rasa", "harga"]

# Diambil dari file paket Trias (predict.py) — disalin agar script ini
# berdiri sendiri tanpa tergantung folder lain.
_DIR = os.path.dirname(os.path.abspath(__file__))


def _muat(nama):
    m = joblib.load(os.path.join(_DIR, nama))
    lr = m.steps[-1][1]
    if not hasattr(lr, "multi_class"):
        lr.multi_class = "auto"
    return m


def klasifikasi(teks_list, model_s, model_t):
    out = []
    ps = model_s.predict_proba(teks_list)
    pt = model_t.predict_proba(teks_list)
    ss = model_s.predict(teks_list)
    st = model_t.predict(teks_list)
    for i, teks in enumerate(teks_list):
        out.append({
            "teks": teks,
            "sentimen": str(ss[i]),
            "prob_sentimen": round(float(max(ps[i])), 4),
            "topik": str(st[i]),
            "prob_topik": round(float(max(pt[i])), 4),
        })
    return out


# ---------- Penjelasan prediksi (SHAP / fallback koefisien) ----------

def _kontribusi(model, teks_list, bg_n=100, latar_nol=False):
    """Kontribusi tiap fitur TF-IDF terhadap kelas yang diprediksi.

    Mengembalikan (daftar_per_teks, metode) dengan daftar_per_teks berisi
    (prediksi, indeks_fitur_yang_muncul, nilai_kontribusi). Metode 'shap'
    bila paket shap tersedia; kalau tidak, 'koefisien' (koefisien LogReg
    x nilai TF-IDF — sama dengan SHAP untuk model linear dengan
    background nol). Untuk model biner, nilai SHAP/koefisien menjelaskan
    kelas index 1, jadi dibalik tandanya bila prediksi adalah kelas 0.

    latar_nol=True: background SHAP-nya vektor nol (dipakai untuk SATU
    ulasan saja — kalau background-nya ulasan itu sendiri, nilainya jadi
    nol semua karena tidak ada pembanding). Hasilnya sama dengan metode
    koefisien, tapi dihitung lewat pustaka shap bila tersedia.
    """
    vec = model.steps[0][1]
    lr = model.steps[-1][1]
    X = vec.transform(teks_list)
    preds = model.predict(teks_list)
    kelas = [str(c) for c in lr.classes_]
    sv = None
    if _shap is not None:
        try:
            bg = np.zeros((1, X.shape[1])) if latar_nol else X[:bg_n]
            ex = _shap.LinearExplainer(lr, bg)
            sv = ex.shap_values(X)
        except Exception:
            sv = None
    out = []
    for i in range(len(teks_list)):
        pred = str(preds[i])
        k = kelas.index(pred)
        row = X[i]
        idxs = row.indices
        if sv is not None:
            if sv.ndim == 3:  # multikelas: (n, fitur, kelas)
                vals = sv[i, idxs, k]
            else:  # biner: nilai untuk kelas index 1
                vals = sv[i, idxs]
                if k == 0:
                    vals = -vals
        else:
            coef = lr.coef_[k] if lr.coef_.shape[0] > 1 else lr.coef_[0]
            vals = coef[idxs] * row.data
            if lr.coef_.shape[0] == 1 and k == 0:
                vals = -vals
        out.append((pred, idxs, np.asarray(vals, dtype=float)))
    return out, ("shap" if sv is not None else "koefisien")


def _top_kata(vec, teks, idxs, vals, n=3):
    """Peta kontribusi fitur ke kata; ambil n kata pendukung teratas.

    Model kata (sentimen): fitur sudah berupa kata/bigram, langsung dipakai.
    Model huruf (topik): nilai tiap n-gram huruf diagregasi ke kata yang
    mengandungnya; bila sebuah n-gram muncul di lebih dari satu kata,
    nilainya dibagi proporsional dengan jumlah kemunculannya.
    """
    fitur = vec.get_feature_names_out()
    skor = {}
    if vec.analyzer == "word":
        for j, v in zip(idxs, vals):
            f = fitur[j]
            skor[f] = skor.get(f, 0.0) + float(v)
    else:  # char_wb
        tokens = teks.lower().split()
        padded = [" " + tok + " " for tok in tokens]
        for j, v in zip(idxs, vals):
            f = fitur[j]
            hits = [m for m, p in enumerate(padded) if f in p]
            if not hits:
                continue
            cnt = [padded[m].count(f) for m in hits]
            tot = sum(cnt)
            for m, c in zip(hits, cnt):
                skor[tokens[m]] = skor.get(tokens[m], 0.0) + float(v) * c / tot
    return [{"kata": k, "nilai": round(v, 4)}
            for k, v in sorted(skor.items(), key=lambda kv: -kv[1])
            if v > 0][:n]


def tambah_shap(ulasan, model_s, model_t, latar_nol=False):
    """Tambahkan 'shap_sentimen' dan 'shap_topik' ke tiap ulasan (dict).

    Tiap field berisi {"metode": "shap"|"koefisien", "kata": [{"kata",
    "nilai"}, ...]} — 3 kata pendukung teratas prediksi itu.
    latar_nol=True dipakai untuk satu ulasan saja (lihat _kontribusi).
    """
    teks_list = [u["teks"] for u in ulasan]
    for model, kunci in ((model_s, "shap_sentimen"),
                         (model_t, "shap_topik")):
        kontribusi, metode = _kontribusi(model, teks_list,
                                         latar_nol=latar_nol)
        vec = model.steps[0][1]
        for u, (pred, idxs, vals) in zip(ulasan, kontribusi):
            u[kunci] = {"metode": metode,
                        "kata": _top_kata(vec, u["teks"], idxs, vals)}
    return None


# ---------- Prompt DeepSeek (dua: negatif + positif) ----------

def bangun_prompt(negatif_per_topik, periode):
    """Prompt 1 (negatif): keluhan utama per topik + saran perbaikan."""
    return bangun_prompt_negatif(negatif_per_topik, periode)


def bangun_prompt_negatif(negatif_per_topik, periode):
    """Satu prompt ringkasan untuk DeepSeek: hitungan per topik + contoh."""
    baris = [
        "Kamu adalah analis Voice of Customer untuk sebuah kedai kopi di "
        "Surabaya (Kedai Harapan Djaja, cabang Gunung Anyar).",
        f"Periode: {periode}. Berikut ringkasan {sum(len(v) for v in negatif_per_topik.values())} "
        "ulasan NEGATIF baru minggu ini, sudah dikelompokkan per topik oleh model lokal:",
    ]
    for topik in TOPIK_URUT:
        items = negatif_per_topik.get(topik, [])
        baris.append(f"\n## Topik {topik} ({len(items)} ulasan)")
        for it in items[:5]:
            baris.append(f'- "{it["teks"]}"')
    baris.append(
        "\nTugas: untuk SETIAP topik yang jumlahnya > 0, tulis 1-2 kalimat "
        "keluhan utamanya dan 2-3 saran tindakan yang konkret dan bisa "
        "dilakukan cabang minggu depan (sebut siapa yang sebaiknya "
        "melakukan: mis. kepala cabang, barista, kasir, atau tim kebersihan). "
        "Lalu tulis 3 saran prioritas utama minggu ini (urut dari yang "
        "paling banyak dikeluhkan)."
        "\nJawab HANYA dalam JSON valid dengan format ini (tanpa teks lain):"
        '\n{"per_topik": [{"topik": "...", "keluhan_utama": "...", '
        '"saran": ["...", "..."]}], '
        '"saran_prioritas": ["...", "...", "..."]}'
    )
    return "\n".join(baris)


def bangun_prompt_positif(positif_per_topik, periode):
    """Prompt 2 (positif): kekuatan per topik + dipertahankan + ide promosi.

    Positif TIDAK diberi 'saran perbaikan' — tugasnya merangkum apa yang
    dipuji, apa yang harus dipertahankan, dan ide promosi dari hal yang
    paling sering disebut.
    """
    baris = [
        "Kamu adalah analis Voice of Customer untuk sebuah kedai kopi di "
        "Surabaya (Kedai Harapan Djaja, cabang Gunung Anyar).",
        f"Periode: {periode}. Berikut ringkasan {sum(len(v) for v in positif_per_topik.values())} "
        "ulasan POSITIF baru minggu ini, sudah dikelompokkan per topik oleh model lokal:",
    ]
    for topik in TOPIK_URUT:
        items = positif_per_topik.get(topik, [])
        baris.append(f"\n## Topik {topik} ({len(items)} ulasan)")
        for it in items[:5]:
            baris.append(f'- "{it["teks"]}"')
    baris.append(
        "\nTugas: untuk SETIAP topik yang jumlahnya > 0, tulis 1-2 kalimat "
        "kekuatannya (apa yang paling dipuji pelanggan) dan 1-2 hal yang "
        "harus DIPERTAHANKAN cabang (sebut siapa yang menjaganya: mis. "
        "barista, tim kebersihan, kepala cabang). Lalu tulis 1-2 ide "
        "promosi minggu ini berdasarkan hal yang paling sering dipuji "
        "(mis. menu, spot, atau suasana yang sering disebut bisa "
        "dipromosikan di media sosial)."
        "\nJawab HANYA dalam JSON valid dengan format ini (tanpa teks lain):"
        '\n{"per_topik": [{"topik": "...", "kekuatan": "...", '
        '"dipertahankan": "..."}], '
        '"ide_promosi": ["...", "..."]}'
    )
    return "\n".join(baris)


def panggil_llm(prompt):
    """Panggil LLM gratis untuk merangkum saran. Urutan:
    1) OpenRouter (env OPENROUTER_API_KEY) -> Particle-1 (free);
    2) OrcaRouter (env ORCAROUTER_API_KEY) -> DeepSeek V4.1 Flash (free).
    Mengembalikan dict hasil, atau None kalau gagal / tidak ada kunci."""
    target = None
    if os.environ.get("OPENROUTER_API_KEY", "").strip():
        target = ("https://openrouter.ai/api/v1",
                  os.environ["OPENROUTER_API_KEY"].strip(),
                  "particle-ai/particle-1:free")
    elif os.environ.get("ORCAROUTER_API_KEY", "").strip():
        target = ("https://api.orcarouter.ai/v1",
                  os.environ["ORCAROUTER_API_KEY"].strip(),
                  "deepseek/deepseek-v4.1-flash-free")
    if not target:
        return None, "BELUM ADA KUNCI API"
    try:
        from openai import OpenAI
    except ImportError:
        return None, "Paket openai belum terpasang (pip install openai)"
    try:
        base_url, kunci, model = target
        client = OpenAI(base_url=base_url, api_key=kunci)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        return json.loads(resp.choices[0].message.content), None
    except Exception as e:  # mis. 429 batas laju, kunci salah, tanpa internet
        return None, f"Gagal memanggil LLM: {e}"


def _item_laporan(u):
    return {"teks": u["teks"], "prob_sentimen": u["prob_sentimen"],
            "prob_topik": u["prob_topik"],
            "shap_topik": u.get("shap_topik"),
            "shap_sentimen": u.get("shap_sentimen")}


def buat_laporan(periode, teks_list, cabang="Gunung Anyar"):
    """Versi fungsi dari main(), untuk dipanggil dari bridge Express.

    Mengembalikan dict laporan yang sama dengan laporan_mingguan.json
    (ringkasan, negatif/positif per topik + SHAP, saran_deepseek dari
    Particle-1 / DeepSeek, dan catatan bila kunci API belum ada).
    Tidak menulis file. LLM dipanggil di sini juga — tanpa kunci, saran
    bernilai None dan laporan tetap lengkap klasifikasinya.
    """
    ulasan = [{"teks": t} for t in teks_list]
    model_s = _muat(MODEL_SENTIMEN)
    model_t = _muat(MODEL_TOPIK)
    hasil = klasifikasi([u["teks"] for u in ulasan], model_s, model_t)
    for u, h in zip(ulasan, hasil):
        u.update(h)
    tambah_shap(ulasan, model_s, model_t)

    negatif = [u for u in ulasan if u["sentimen"] == "Tidak puas"]
    positif = [u for u in ulasan if u["sentimen"] == "Puas"]
    per_topik = {t: [u for u in negatif if u["topik"] == t]
                 for t in TOPIK_URUT}
    per_topik_pos = {t: [u for u in positif if u["topik"] == t]
                     for t in TOPIK_URUT}
    for t in TOPIK_URUT:
        per_topik[t].sort(key=lambda u: u["prob_sentimen"], reverse=True)
        per_topik_pos[t].sort(key=lambda u: u["prob_sentimen"], reverse=True)

    prompt_neg = bangun_prompt_negatif(per_topik, periode)
    prompt_pos = bangun_prompt_positif(per_topik_pos, periode)
    saran, galat = panggil_llm(prompt_neg)
    saran_pos, galat_pos = panggil_llm(prompt_pos)

    return {
        "periode": periode,
        "cabang": cabang,
        "ringkasan": {
            "total_baru": len(ulasan),
            "negatif": len(negatif),
            "per_topik": {t: len(per_topik[t]) for t in TOPIK_URUT},
        },
        "ringkasan_positif": {
            "positif": len(positif),
            "per_topik": {t: len(per_topik_pos[t]) for t in TOPIK_URUT},
        },
        "negatif_per_topik": {
            t: [_item_laporan(u) for u in per_topik[t]]
            for t in TOPIK_URUT
        },
        "positif_per_topik": {
            t: [_item_laporan(u) for u in per_topik_pos[t]]
            for t in TOPIK_URUT
        },
        "saran_deepseek": saran,
        "catatan_saran": galat,
        "saran_deepseek_positif": saran_pos,
        "catatan_saran_positif": galat_pos,
    }


def main():
    if len(sys.argv) < 2:
        print("Pakai: python3 laporan_mingguan.py input_mingguan.json")
        sys.exit(1)
    with open(sys.argv[1], encoding="utf-8") as f:
        masuk = json.load(f)
    periode = masuk.get("periode", "-")
    ulasan = masuk.get("ulasan", [])
    print(f"Ulasan baru: {len(ulasan)} (periode {periode})")

    model_s = _muat(MODEL_SENTIMEN)
    model_t = _muat(MODEL_TOPIK)
    hasil = klasifikasi([u["teks"] for u in ulasan], model_s, model_t)
    for u, h in zip(ulasan, hasil):
        u.update(h)
    tambah_shap(ulasan, model_s, model_t)
    print("Penjelasan SHAP/koefisien: "
          f"{ulasan[0]['shap_sentimen']['metode'] if ulasan else '-'}")

    negatif = [u for u in ulasan if u["sentimen"] == "Tidak puas"]
    positif = [u for u in ulasan if u["sentimen"] == "Puas"]
    per_topik = {t: [u for u in negatif if u["topik"] == t]
                 for t in TOPIK_URUT}
    per_topik_pos = {t: [u for u in positif if u["topik"] == t]
                     for t in TOPIK_URUT}
    # Contoh yang ditampilkan (laporan .md + prompt DeepSeek) diurutkan
    # dari yang paling yakin sentimennya, supaya ulasan yang salah
    # klasifikasi (keyakinan rendah) tidak jadi contoh terdepan.
    # Hitungan per topik TIDAK berubah — hanya urutan contoh.
    for t in TOPIK_URUT:
        per_topik[t].sort(key=lambda u: u["prob_sentimen"], reverse=True)
        per_topik_pos[t].sort(key=lambda u: u["prob_sentimen"], reverse=True)
    print(f"Negatif: {len(negatif)} | Positif: {len(positif)} "
          f"dari {len(ulasan)}")
    for t in TOPIK_URUT:
        print(f"  {t}: negatif {len(per_topik[t])}, "
              f"positif {len(per_topik_pos[t])}")

    prompt_neg = bangun_prompt_negatif(per_topik, periode)
    with open("prompt_deepseek_negatif.txt", "w", encoding="utf-8") as f:
        f.write(prompt_neg)
    prompt_pos = bangun_prompt_positif(per_topik_pos, periode)
    with open("prompt_deepseek_positif.txt", "w", encoding="utf-8") as f:
        f.write(prompt_pos)

    saran, galat = panggil_llm(prompt_neg)
    saran_pos, galat_pos = panggil_llm(prompt_pos)
    if galat:
        print("DeepSeek (negatif):", galat,
              "-> laporan tetap dibuat tanpa saran AI.")
    if galat_pos:
        print("DeepSeek (positif):", galat_pos,
              "-> laporan tetap dibuat tanpa saran AI.")

    laporan = {
        "periode": periode,
        "cabang": masuk.get("cabang", "Gunung Anyar"),
        "ringkasan": {
            "total_baru": len(ulasan),
            "negatif": len(negatif),
            "per_topik": {t: len(per_topik[t]) for t in TOPIK_URUT},
        },
        "ringkasan_positif": {
            "positif": len(positif),
            "per_topik": {t: len(per_topik_pos[t]) for t in TOPIK_URUT},
        },
        "negatif_per_topik": {
            t: [_item_laporan(u) for u in per_topik[t]]
            for t in TOPIK_URUT
        },
        "positif_per_topik": {
            t: [_item_laporan(u) for u in per_topik_pos[t]]
            for t in TOPIK_URUT
        },
        "saran_deepseek": saran,
        "catatan_saran": galat,
        "saran_deepseek_positif": saran_pos,
        "catatan_saran_positif": galat_pos,
    }
    with open("laporan_mingguan.json", "w", encoding="utf-8") as f:
        json.dump(laporan, f, ensure_ascii=False, indent=2)

    # Laporan .md yang bisa dibaca manusia.
    md = [f"# Laporan Mingguan Ulasan — {periode}\n",
          f"Total ulasan baru: **{len(ulasan)}**, negatif: **{len(negatif)}**, "
          f"positif: **{len(positif)}**.\n",
          "## Negatif per topik",
          "| Topik | Jumlah |",
          "|---|---:|"]
    for t in TOPIK_URUT:
        md.append(f"| {t} | {len(per_topik[t])} |")
    md.append("")
    for t in TOPIK_URUT:
        if not per_topik[t]:
            continue
        md.append(f"## {t} ({len(per_topik[t])} negatif)")
        for u in per_topik[t][:5]:
            md.append(f'- "{u["teks"]}" (yakin {u["prob_topik"]:.2f})')
        md.append("")
    if saran:
        md.append("## Saran DeepSeek (negatif)\n")
        for item in saran.get("per_topik", []):
            md.append(f"### {item['topik']}")
            md.append(f"Keluhan utama: {item['keluhan_utama']}")
            for s in item["saran"]:
                md.append(f"- {s}")
            md.append("")
        md.append("### Prioritas minggu ini")
        for s in saran.get("saran_prioritas", []):
            md.append(f"- {s}")
        md.append("")
    else:
        md.append(f"## Saran DeepSeek (negatif)\n\nBelum ada — {galat}.\n")
    md.append("## Positif per topik")
    md.append("| Topik | Jumlah |")
    md.append("|---|---:|")
    for t in TOPIK_URUT:
        md.append(f"| {t} | {len(per_topik_pos[t])} |")
    md.append("")
    for t in TOPIK_URUT:
        if not per_topik_pos[t]:
            continue
        md.append(f"## {t} ({len(per_topik_pos[t])} positif)")
        for u in per_topik_pos[t][:3]:
            md.append(f'- "{u["teks"]}" (yakin {u["prob_topik"]:.2f})')
        md.append("")
    if saran_pos:
        md.append("## Kekuatan & promosi — DeepSeek (positif)\n")
        for item in saran_pos.get("per_topik", []):
            md.append(f"### {item['topik']}")
            md.append(f"Kekuatan: {item['kekuatan']}")
            md.append(f"Dipertahankan: {item['dipertahankan']}")
            md.append("")
        md.append("### Ide promosi")
        for s in saran_pos.get("ide_promosi", []):
            md.append(f"- {s}")
    else:
        md.append(f"## Kekuatan & promosi — DeepSeek (positif)\n\nBelum ada "
                  f"— {galat_pos}.")
    with open("laporan_mingguan.md", "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print("Tersimpan: laporan_mingguan.json, laporan_mingguan.md, "
          "prompt_deepseek_negatif.txt, prompt_deepseek_positif.txt")


if __name__ == "__main__":
    main()
