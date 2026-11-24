"""Inti pipeline VoC: normalisasi teks, label lemah, pemecah klausa, SHAP linier."""
import re, unicodedata
import numpy as np

TOPIK = ["rasa", "harga", "pelayanan", "tempat"]

# ---------------------------------------------------------------- normalisasi
SLANG = {
    "bgt": "banget", "bngt": "banget", "bgtt": "banget", "bangett": "banget", "bet": "banget",
    "tp": "tapi", "tpi": "tapi", "yg": "yang", "dg": "dengan", "dgn": "dengan", "utk": "untuk",
    "ga": "tidak", "gak": "tidak", "gk": "tidak", "g": "tidak", "pesen": "pesan", "dtg": "datang", "dateng": "datang", "nggak": "tidak", "ngga": "tidak",
    "enggak": "tidak", "ngk": "tidak", "ndak": "tidak", "kagak": "tidak", "tdk": "tidak", "gaada": "tidak ada",
    "gada": "tidak ada", "blas": "sama sekali", "pdhl": "padahal", "pdhal": "padahal", "krn": "karena",
    "karna": "karena", "sdh": "sudah", "udh": "sudah", "udah": "sudah", "uda": "sudah", "dah": "sudah",
    "blm": "belum", "sm": "sama", "ama": "sama", "bkn": "bukan", "lg": "lagi", "lgi": "lagi",
    "kalo": "kalau", "klo": "kalau", "kl": "kalau", "kqlo": "kalau", "jd": "jadi", "jdi": "jadi",
    "aja": "saja", "aj": "saja", "doang": "saja", "bnyk": "banyak", "byk": "banyak", "bnyak": "banyak",
    "mknan": "makanan", "makanannya": "makanan nya", "mkanan": "makanan", "makananya": "makanan nya",
    "minumanya": "minuman nya", "mnuman": "minuman", "pelyanan": "pelayanan", "playanan": "pelayanan",
    "pelayaan": "pelayanan", "pelayanam": "pelayanan", "palayanan": "pelayanan", "pelanyannya": "pelayanan nya",
    "layanan": "pelayanan", "layanannya": "pelayanan nya", "service": "pelayanan", "servis": "pelayanan",
    "services": "pelayanan", "tmpt": "tempat", "t4": "tempat", "tempate": "tempat", "panggone": "tempat",
    "murce": "murah", "mumer": "murah meriah", "pricey": "mahal", "overprice": "mahal",
    "overpriced": "mahal", "overpice": "mahal", "affordable": "terjangkau", "afordable": "terjangkau",
    "worthit": "worth it", "wort": "worth", "whort": "worth", "worit": "worth it",
    "enk": "enak", "ena": "enak", "wenak": "enak", "uenak": "enak", "uwenak": "enak", "enakk": "enak",
    "anyep": "hambar", "sumuk": "panas", "gerah": "panas", "kemproh": "kotor", "jorok": "kotor",
    "koyor": "kotor", "nongki": "nongkrong", "nongs": "nongkrong", "nongkii": "nongkrong",
    "pw": "nyaman", "comfy": "nyaman", "cozy": "nyaman", "lamaa": "lama", "luama": "lama",
    "josjis": "jos", "josjiss": "jos", "jossjiss": "jos", "mantab": "mantap", "mantep": "mantap",
    "poll": "pol", "pwol": "pol", "pwoll": "pol", "rekomen": "rekomendasi", "recommended": "rekomendasi",
    "rekomended": "rekomendasi", "recommend": "rekomendasi", "rekom": "rekomendasi",
    "kasirnya": "kasir nya", "waiters": "pelayan", "waitersnya": "pelayan nya", "pegawai": "karyawan",
    "staff": "karyawan", "staf": "karyawan", "crew": "karyawan", "barista": "karyawan",
}
_NYA_SKIP = {"punya", "hanya", "bertanya", "tanya", "sebenarnya", "seharusnya", "biasanya", "akhirnya",
             "rupanya", "katanya", "sayangnya", "nya", "minusnya", "sepertinya", "kayaknya", "pokoknya",
             "intinya", "lainnya", "selanjutnya", "sebelumnya", "terutama", "kebanyaknya"}


def normalisasi(teks: str) -> str:
    t = unicodedata.normalize("NFKC", str(teks)).lower()
    t = re.sub(r"https?://\S+", " ", t)
    t = t.replace("…", " ").replace("’", "'").replace("”", " ").replace("“", " ")
    t = re.sub(r"[^\w\s.,!?;:/&+\-]", " ", t)          # buang emoji & simbol
    t = re.sub(r"(\w)\1{2,}", r"\1", t)                   # enakkkk -> enak
    t = re.sub(r"\d+(?:[.,]\d+)?\s*(k|rb|ribu)\b", " hargaangka ", t)
    t = re.sub(r"\d+", " angka ", t)
    out = []
    for w in re.findall(r"[a-z]+|[.,!?;:/&+\-]", t):
        if len(w) > 3 and w[-1] == w[-2] and w[-1] in "aiueokhsngtlmrpyw":   # tempatnyaa, enakk, gass
            w = w[:-1]
        w = SLANG.get(w, w)
        for w2 in w.split():
            if w2.endswith("nya") and len(w2) > 5 and w2 not in _NYA_SKIP:
                out += [SLANG.get(w2[:-3], w2[:-3]), "nya"]
            else:
                out.append(w2)
    return re.sub(r"\s+", " ", " ".join(out)).strip()


# ------------------------------------------------- leksikon (label lemah multi-topik)
LEKSIKON = {
    # "enak" sengaja TIDAK dimasukkan: "tempatnya enak", "enak buat nongkrong" itu soal tempat.
    # Rasa hanya dihitung dari kata benda makanan/minuman atau kata rasa yang tidak ambigu.
    "rasa": r"\b(makan|makanan|minum|minuman|menu|rasa|rasanya|lezat|hambar|asin|manis|kemanisan|"
            r"pahit|matang|alot|kopi|kopinya|teh|matcha|mie|nasi|ayam|seafood|snack|"
            r"camilan|cemilan|platter|porsi|basi|kuah|bumbu|tasty|food|drink|drinks|sambal|sambel|"
            r"roti|kentang|cireng|otak|americano|latte|bakmi|thai|leci|jajan|jajanan|milo|creamy|"
            r"hidangan|masakan|wagyu|barendo|minumnya|makannya|kue|kebab|sosis|es|fnb|cuminya|wedang)\b",
    "harga": r"\b(harga|harganya|murah|mahal|terjangkau|worth|kantong|budget|bayar|refund|diskon|"
             r"promo|bill|hargaangka|ekonomis|hemat|price|bersahabat|kantong|overprice|"
             r"ribu|struk|tax|murah meriah)\b",
    "pelayanan": r"\b(pelayanan|pelayan|pelayannya|karyawan|kasir|ramah|judes|sinis|jutek|cuek|"
                 r"sopan|lama|lambat|lelet|cepat|cepet|gercep|sigap|antri|antre|antrian|antrean|"
                 r"pesanan|orderan|digarap|dikerjakan|diantar|disambut|sambut|senyum|attitude|atitude|tanggap|"
                 r"informatif|satset|hospitality|komplain|ditanya|helpfull|helpful|nunggu|menunggu|"
                 r"diantar|pengantaran|kakak|kakaknya|mas|mbak|owner|manajemen|melayani|layan)\b",
    "tempat": r"\b(tempat|tempatnya|suasana|suasananya|view|pemandangan|nyaman|luas|bersih|kotor|"
              r"debu|berdebu|parkir|parkiran|toilet|mushola|musholla|ac|kipas|panas|sejuk|adem|"
              r"indoor|outdoor|rooftop|lantai|sofa|kursi|meja|colokan|stop kontak|wifi|nyamuk|"
              r"tikus|lalat|musik|live|estetik|aesthetic|aestetic|estetic|syahdu|vibes|vibe|"
              r"nugas|nongkrong|lokasi|strategis|spot|sunset|asik|asyik|seru|tenang|berisik|"
              r"bau|pengap|angin|place|atmosfir|ambience|interior|dekorasi|toilet|jedinge|desain)\b",
}
_LEKS_RE = {k: re.compile(v) for k, v in LEKSIKON.items()}


_RASA_NILAI = re.compile(r"\b(enak|lezat|hambar|asin|manis|kemanisan|pahit|matang|alot|basi|tasty|segar|seger|"
                         r"creamy|gurih|pedas|amis|keras|lembek|benyek|kering|berminyak|juara|mantap|jos|best|"
                         r"oke|ok|biasa|standar|zonk|gagal|rasa|rasanya|porsi|variatif|beragam|lengkap|banyak)\b")
_RASA_BUKAN = re.compile(r"\b(murah|mahal|harga|terjangkau|worth|kantong|lama|datang|nunggu|menunggu|keluar|"
                         r"cepat|cepet|antri|dibuat|digarap|disajikan|habis|kosong)\b")
_TEMPAT_KATA = re.compile(r"\b(tempat|suasana|view|nongkrong|nugas|santai|nyore|lantai|indoor|outdoor)\b")


def topik_leksikon(teks_norm: str) -> dict:
    """Jumlah kata kunci per topik, dibaca per klausa supaya kata makanan yang dibahas harganya
    ("harga makanan murah") atau waktunya ("makanan lama datang") tidak dihitung sebagai rasa,
    dan "enak" hanya jadi rasa bila bersanding dengan makanan/minuman (bukan "tempatnya enak")."""
    hit = {k: 0 for k in _LEKS_RE}
    for kl in pecah_klausa(teks_norm):
        for k, r in _LEKS_RE.items():
            n = len(r.findall(kl))
            if k == "rasa" and n:
                nilai = _RASA_NILAI.search(kl)
                if not nilai and _RASA_BUKAN.search(kl):
                    n = 0
            hit[k] += n
        if re.search(r"\benak\b", kl) and not _TEMPAT_KATA.search(kl) and len(kl.split()) <= 3 and not hit["rasa"]:
            pass   # "enak banget" saja: ambigu, tidak diberi topik
    return hit


# ---------------------------------------------------------- pemecah klausa
_PEMISAH = r"(?:[.!?;\n/]+|,|\b(?:tapi|tetapi|namun|cuma|cuman|sayang|sayangnya|minus|minusnya|padahal|" \
           r"sedangkan|walaupun|meskipun|meski|kecuali|hanya saja|tetep|plus|dan juga|serta)\b)"


def pecah_klausa(teks_norm: str, min_kata: int = 2):
    """Pecah ulasan jadi klausa supaya satu ulasan campuran bisa punya sentimen berbeda per topik.
    Klausa sangat pendek (<min_kata) digabung ke klausa sebelumnya."""
    bagian = [b.strip(" ,.-") for b in re.split(_PEMISAH, teks_norm) if b and b.strip(" ,.-")]
    hasil = []
    for b in bagian:
        if hasil and len(b.split()) < min_kata:
            hasil[-1] = hasil[-1] + " " + b
        else:
            hasil.append(b)
    return hasil or [teks_norm]


# --------------------------------------------------------- SHAP linier per kata
_NAMES_CACHE = {}


STOPWORD = set("""tidak nya yang dan di ke dari juga sudah saja sama aku saya kami kita ini itu ada
dengan untuk karena buat jadi lagi kalau tapi atau banget sangat sekali pol angka hargaangka the and
bisa mau udah belum pas jam baru masih lebih kurang terlalu agak cukup lumayan nih sih kok deh dong
ya yah aja kan pun oleh pada akan bikin mana apa kalo gitu kayak kek seperti""".split())


def shap_per_kata(teks_norm, vectorizer, coef, mean_x, top=8, buang_stopword=False):
    """SHAP eksak untuk model linier (fitur independen, sama dengan shap.LinearExplainer):
    phi_j = w_j * (x_j - E[x_j]) dalam skala log-odds.
    Kontribusi n-gram (kata & karakter) dibagi ke kata yang memuatnya -> daftar kata terbaca."""
    key = id(vectorizer)
    if key not in _NAMES_CACHE:
        _NAMES_CACHE[key] = vectorizer.get_feature_names_out()
    names = _NAMES_CACHE[key]
    x = vectorizer.transform([teks_norm]).tocsr()
    kata = list(dict.fromkeys(teks_norm.split()))
    skor = {w: 0.0 for w in kata}
    for j, v in zip(x.indices, x.data):
        phi = coef[j] * (v - mean_x[j])
        jenis, f = names[j].split("__", 1)
        if jenis == "w":
            pemilik = [w for w in f.split() if w in skor]
        else:
            inti = f.strip()
            pemilik = [w for w in kata if inti and inti in w]
        for w in pemilik:
            skor[w] += phi / len(pemilik)
    urut = sorted(((w, s) for w, s in skor.items() if len(w) > 2 and w.isalpha()
                   and not (buang_stopword and w in STOPWORD)), key=lambda t: -abs(t[1]))
    return [(w, round(float(s), 3)) for w, s in urut[:top]]


# =====================================================================
#  MODEL: fitur TF-IDF kata + karakter, Logistic Regression (tanpa transfer learning)
# =====================================================================
import json, time, datetime as _dt
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import FeatureUnion
from sklearn.linear_model import LogisticRegression


def buat_vectorizer():
    return FeatureUnion([
        ("w", TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)),
        ("c", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=2, sublinear_tf=True)),
    ])


def buat_lr(C=4.0):
    return LogisticRegression(C=C, class_weight="balanced", max_iter=5000)


def label_bintang(b):
    """Label sentimen dari bintang: 4-5 = positif (1); 1-3 = negatif (0, ada keluhan)."""
    return int(b >= 4)


# =====================================================================
#  ANALISIS MINGGUAN
# =====================================================================
_KUNCI_TEKS = ["teks", "text", "review", "ulasan", "isi", "snippet", "comment"]
_KUNCI_BINTANG = ["bintang", "rating", "stars", "star", "nilai"]
_KUNCI_ID = ["id", "review_id", "reviewId", "id_ulasan"]
_KUNCI_TGL = ["tanggal", "date", "waktu", "tanggal_relatif", "publishedAtDate", "time"]


def _ambil(d, kunci, default=None):
    for k in kunci:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return default


def baca_json_ulasan(path_or_obj):
    """Terima list ulasan, atau dict {"ulasan": [...]} / {"reviews": [...]}. Nama kolom fleksibel."""
    obj = path_or_obj
    if isinstance(path_or_obj, str):
        with open(path_or_obj, encoding="utf-8") as f:
            obj = json.load(f)
    meta = {}
    if isinstance(obj, dict):
        meta = {k: v for k, v in obj.items() if not isinstance(v, list)}
        obj = next((v for v in obj.values() if isinstance(v, list)), [])
    rows = []
    for i, r in enumerate(obj):
        teks = _ambil(r, _KUNCI_TEKS, "")
        if not str(teks).strip():
            continue
        b = _ambil(r, _KUNCI_BINTANG)
        try:
            b = int(round(float(b))) if b is not None else None
        except (TypeError, ValueError):
            b = None
        rows.append({"id": str(_ambil(r, _KUNCI_ID, f"u{i+1:03d}")), "teks": str(teks).strip(),
                     "bintang": b, "tanggal": _ambil(r, _KUNCI_TGL, "")})
    return rows, meta


def prob_topik(teks_norm, X, M):
    """Probabilitas topik hibrida: (1-w)·model + w·kata kunci. Model menangkap frasa baru,
    kata kunci menjaga presisi untuk kata yang jelas. Ambang 0.5 (M['thr'])."""
    w = M.get("bobot_leksikon", 0.0)
    lk = topik_leksikon(teks_norm)
    return {k: (1 - w) * float(M["topik"][k].predict_proba(X)[0, 1]) + w * float(lk[k] > 0) for k in TOPIK}


def analisis_ulasan(rows, M, bobot_bintang=0.3, top_shap=6, zona_netral=0.05):
    """Klasifikasi sentimen + topik per klausa, SHAP per ulasan & per klausa.
    M = dict artefak model hasil training (lihat notebook)."""
    vec, sent, topm, thr = M["vec"], M["sent"], M["topik"], M["thr"]
    coef_s, mean_x = M["coef_sent"], M["mean_x"]
    hasil = []
    for r in rows:
        norm = normalisasi(r["teks"])
        X = vec.transform([norm])
        p_pos_teks = float(sent.predict_proba(X)[0, 1])
        p_bintang = None if r["bintang"] is None else float(label_bintang(r["bintang"]))
        # sentimen ulasan: bintang adalah sinyal paling jujur untuk ulasan Google Maps;
        # kalau tidak ada bintang (mis. form QR), pakai model teks.
        p_ulasan = p_pos_teks if p_bintang is None else 0.5 * p_bintang + 0.5 * p_pos_teks
        p_top_ulasan = prob_topik(norm, X, M)
        klausa_out = []
        for kl in pecah_klausa(norm):
            Xk = vec.transform([kl])
            pk = float(sent.predict_proba(Xk)[0, 1])
            konteks = p_ulasan if p_bintang is None else p_bintang
            ps = (1 - bobot_bintang) * pk + bobot_bintang * konteks
            ptop = prob_topik(kl, Xk, M)
            topik_kl = [k for k in TOPIK if ptop[k] >= thr[k]]
            shap_s = shap_per_kata(kl, vec, coef_s, mean_x, top=top_shap, buang_stopword=True)
            klausa_out.append({
                "klausa": kl, "topik": topik_kl,
                "p_topik": {k: round(v, 3) for k, v in ptop.items()},
                "sentimen": "positif" if ps >= 0.5 + zona_netral else ("negatif" if ps < 0.5 - zona_netral
                                                                         else "netral"),
                "p_positif": round(ps, 3),
                "shap": shap_s,
                "shap_per_topik": _bagi_kata_ke_topik(kl, shap_s, topik_kl, M),
            })
        # klausa tanpa topik -> ikut topik terkuat ulasan (kalau ada)
        top_ulasan = [k for k in TOPIK if p_top_ulasan[k] >= thr[k]]
        for k in klausa_out:
            if not k["topik"] and len(k["klausa"].split()) >= 3 and top_ulasan:
                k["topik"] = [max(top_ulasan, key=lambda t: p_top_ulasan[t])]
                k["topik_dari"] = "ulasan"
        sent_ulasan = "positif" if p_ulasan >= 0.5 else "negatif"
        ada_keluhan = any(k["sentimen"] == "negatif" and k["topik"] for k in klausa_out)
        hasil.append({
            **r, "teks_normal": norm, "sentimen": sent_ulasan, "p_positif": round(p_ulasan, 3),
            "p_positif_teks": round(p_pos_teks, 3),
            "topik": top_ulasan, "p_topik": {k: round(v, 3) for k, v in p_top_ulasan.items()},
            "campuran": sent_ulasan == "positif" and ada_keluhan,
            "beda_bintang_teks": p_bintang is not None and (p_bintang >= 0.5) != (p_pos_teks >= 0.5),
            "shap_ulasan": shap_per_kata(norm, vec, coef_s, mean_x, top=top_shap, buang_stopword=True),
            "klausa": klausa_out,
        })
    return hasil


def _bagi_kata_ke_topik(kl, shap_s, topik_kl, M):
    """Klausa yang memuat >1 topik ("layanan lama, suasana kotor"): tiap kata pemicu sentimen
    diberikan ke topik yang paling 'diakui' kata itu menurut SHAP model topik."""
    if len(topik_kl) <= 1 or "coef_topik" not in M:
        return {t: shap_s for t in topik_kl}
    st = {t: dict(shap_per_kata(kl, M["vec"], M["coef_topik"][t], M["mean_x"], top=50)) for t in topik_kl}
    out = {t: [] for t in topik_kl}
    for w, phi in shap_s:
        skor = {t: st[t].get(w, 0.0) for t in topik_kl}
        terbaik = max(skor, key=skor.get)
        for t in ([terbaik] if skor[terbaik] > 0.05 else topik_kl):
            out[t].append((w, phi))
    return out


def kelompokkan_per_topik(hasil, maks_kutipan=15):
    """Kelompok negatif & positif per topik + kata pemicu (jumlah SHAP)."""
    grup = {}
    for t in TOPIK:
        for s in ["negatif", "positif"]:
            kut, kata, id_ul = [], {}, set()
            for u in hasil:
                kls = [k for k in u["klausa"] if t in k["topik"] and k["sentimen"] == s]
                if not kls:
                    continue
                id_ul.add(u["id"])
                kekuatan = 0.0
                for k in kls:
                    for w, phi in k.get("shap_per_topik", {}).get(t, k["shap"]):
                        if (s == "negatif" and phi < 0) or (s == "positif" and phi > 0):
                            kata[w] = kata.get(w, 0.0) + abs(phi)
                            kekuatan += abs(phi)
                kut.append({"id": u["id"], "bintang": u["bintang"],
                            "bagian": "; ".join(k["klausa"] for k in kls),
                            "teks_asli": u["teks"][:300], "_skor": kekuatan})
            # yang paling kuat sinyalnya (dan bintang paling rendah untuk keluhan) didahulukan
            kut.sort(key=lambda q: (-(q["_skor"]) + (0 if s == "positif" else 0.5 * (q["bintang"] or 3))))
            for q in kut:
                q.pop("_skor")
            grup[f"{t}|{s}"] = {
                "topik": t, "sentimen": s, "jumlah_ulasan": len(id_ul),
                "kata_pemicu_shap": [w for w, _ in sorted(kata.items(), key=lambda x: -x[1])[:10]],
                "kutipan": kut[:maks_kutipan],
            }
    return grup


# =====================================================================
#  LLM via OpenRouter (2 prompt)
# =====================================================================
SYSTEM_PROMPT = (
    "Kamu analis Voice of Customer untuk pemilik kedai kopi & makan di Surabaya. "
    "Kamu HANYA boleh memakai data yang diberikan: jangan mengarang keluhan, angka, atau nama. "
    "Setiap klaim wajib menyebut id ulasan sebagai bukti. Tulis dalam Bahasa Indonesia sederhana "
    "yang mudah dipahami kepala cabang (bukan bahasa teknis). Jawab HANYA dengan satu objek JSON valid."
)

PROMPT_KELUHAN = """Data keluhan pelanggan minggu ini, cabang {cabang}, periode {periode}.
Total ulasan: {n_ulasan}. Sistem sudah mengelompokkan bagian ulasan yang NEGATIF per topik
(rasa, harga, pelayanan, tempat). "kata_pemicu_shap" = kata yang paling mendorong model menilai negatif.

DATA:
{data}

Tugas: rangkum keluhan per topik dan beri saran perbaikan yang bisa dikerjakan minggu depan.
Urutkan dari yang paling mendesak (paling banyak ulasan & paling parah). Lewati topik yang jumlah_ulasan-nya 0.
Format JSON:
{{
  "ringkasan": "2-3 kalimat inti keluhan minggu ini",
  "keluhan": [
    {{"topik": "...", "masalah_utama": "...", "jumlah_ulasan": 0, "bukti_id": ["..."],
      "prioritas": "tinggi|sedang|rendah",
      "saran_tindakan": ["langkah konkret 1", "langkah konkret 2"],
      "indikator_berhasil": "cara mengecek minggu depan apakah perbaikan berhasil"}}
  ],
  "ulasan_perlu_dibalas": [{{"id": "...", "alasan": "...", "draf_balasan": "balasan sopan 2-3 kalimat"}}]
}}"""

PROMPT_POSITIF = """Data pujian pelanggan minggu ini, cabang {cabang}, periode {periode}.
Total ulasan: {n_ulasan}. Sistem sudah mengelompokkan bagian ulasan yang POSITIF per topik.
"kata_pemicu_shap" = kata yang paling mendorong model menilai positif.

DATA:
{data}

Tugas: sebutkan apa yang sudah bagus (perlu dipertahankan) dan ide promosi yang jujur,
berdasarkan pujian nyata pelanggan. Lewati topik yang jumlah_ulasan-nya 0.
Format JSON:
{{
  "ringkasan": "2-3 kalimat",
  "kekuatan": [{{"topik": "...", "yang_dipuji": "...", "jumlah_ulasan": 0, "bukti_id": ["..."],
                 "cara_mempertahankan": "..."}}],
  "ide_promosi": [{{"ide": "...", "dasar_bukti_id": ["..."], "kanal": "Instagram/TikTok/Google Maps/di kedai",
                    "contoh_caption": "..."}}]
}}"""


def _data_prompt(grup, sentimen):
    out = []
    for t in TOPIK:
        g = grup[f"{t}|{sentimen}"]
        out.append({"topik": t, "jumlah_ulasan": g["jumlah_ulasan"], "kata_pemicu_shap": g["kata_pemicu_shap"],
                    "kutipan": [{"id": q["id"], "bintang": q["bintang"], "bagian_relevan": q["bagian"],
                                 "teks": q["teks_asli"]} for q in g["kutipan"]]})
    return json.dumps(out, ensure_ascii=False, indent=1)


def _parse_json(teks):
    teks = re.sub(r"^```(?:json)?|```$", "", teks.strip(), flags=re.M).strip()
    try:
        return json.loads(teks)
    except json.JSONDecodeError:
        a, b = teks.find("{"), teks.rfind("}")
        if a >= 0 and b > a:
            return json.loads(teks[a:b + 1])
        raise


def panggil_llm(prompt, api_key, model, suhu=0.2, maks_token=12000, coba=3):
    import requests
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
               "X-Title": "VoC Kedai Harapan Djaja"}
    body = {"model": model, "temperature": suhu, "max_tokens": maks_token,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"}}
    err = None
    for i in range(coba):
        try:
            r = requests.post(url, headers=headers, json=body, timeout=180)
            if r.status_code == 400 and "response_format" in body:   # model tak mendukung json mode
                body.pop("response_format")
                continue
            r.raise_for_status()
            msg = r.json()["choices"][0]["message"]
            if not (msg.get("content") or "").strip():      # model reasoning kehabisan token
                body["max_tokens"] = int(body["max_tokens"] * 1.5)
                raise ValueError("jawaban kosong")
            return _parse_json(msg["content"]), r.json().get("usage", {})
        except Exception as e:      # jaringan / JSON rusak -> ulangi
            err = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"LLM gagal setelah {coba} percobaan: {err}")


def _fallback_tanpa_llm(grup, sentimen):
    """Kalau API key belum ada: ringkasan berbasis aturan supaya pipeline tetap jalan."""
    items = []
    for t in TOPIK:
        g = grup[f"{t}|{sentimen}"]
        if g["jumlah_ulasan"]:
            items.append({"topik": t, "jumlah_ulasan": g["jumlah_ulasan"],
                          "kata_kunci": g["kata_pemicu_shap"][:6],
                          "bukti_id": [q["id"] for q in g["kutipan"][:5]]})
    items.sort(key=lambda x: -x["jumlah_ulasan"])
    if sentimen == "negatif":
        return {"ringkasan": "(mode tanpa LLM) Keluhan dikelompokkan otomatis, belum dirangkum LLM.",
                "keluhan": [{**i, "masalah_utama": ", ".join(i["kata_kunci"]),
                             "prioritas": "tinggi" if i["jumlah_ulasan"] >= 3 else "sedang",
                             "saran_tindakan": []} for i in items], "ulasan_perlu_dibalas": []}
    return {"ringkasan": "(mode tanpa LLM) Pujian dikelompokkan otomatis, belum dirangkum LLM.",
            "kekuatan": [{**i, "yang_dipuji": ", ".join(i["kata_kunci"])} for i in items], "ide_promosi": []}


def buat_laporan(rows, M, cabang, periode, api_key=None, model="particle-ai/particle-1", meta=None):
    hasil = analisis_ulasan(rows, M)
    grup = kelompokkan_per_topik(hasil)
    n = len(hasil)
    bintang = [u["bintang"] for u in hasil if u["bintang"] is not None]
    stat_topik = {t: {"positif": grup[f"{t}|positif"]["jumlah_ulasan"],
                      "negatif": grup[f"{t}|negatif"]["jumlah_ulasan"]} for t in TOPIK}
    isi = dict(cabang=cabang, periode=periode, n_ulasan=n)
    llm_info = {"model": model if api_key else None, "usage": {}}
    if api_key and n:
        keluhan, u1 = panggil_llm(PROMPT_KELUHAN.format(**isi, data=_data_prompt(grup, "negatif")), api_key, model)
        positif, u2 = panggil_llm(PROMPT_POSITIF.format(**isi, data=_data_prompt(grup, "positif")), api_key, model)
        llm_info["usage"] = {"prompt_keluhan": u1, "prompt_positif": u2}
    else:
        keluhan, positif = _fallback_tanpa_llm(grup, "negatif"), _fallback_tanpa_llm(grup, "positif")
    laporan = {
        "meta": {"cabang": cabang, "periode": periode, "dibuat": _dt.datetime.now().isoformat(timespec="seconds"),
                 "versi_model": M.get("versi"), "llm": llm_info, **(meta or {})},
        "statistik": {
            "jumlah_ulasan": n,
            "rata_bintang": round(sum(bintang) / len(bintang), 2) if bintang else None,
            "persen_puas": round(100 * sum(u["sentimen"] == "positif" for u in hasil) / n, 1) if n else None,
            "ulasan_negatif": sum(u["sentimen"] == "negatif" for u in hasil),
            "ulasan_campuran": sum(u["campuran"] for u in hasil),
            "per_topik": stat_topik,
        },
        "keluhan": keluhan, "positif": positif,
        "kelompok_topik": grup,
        "ulasan": hasil,
    }
    return laporan


def laporan_ke_teks(L):
    s, g = L["statistik"], L["kelompok_topik"]
    baris = [
        "=" * 64,
        f"LAPORAN SUARA PELANGGAN MINGGUAN — {L['meta']['cabang']}",
        f"Periode: {L['meta']['periode']}   (dibuat {L['meta']['dibuat']})",
        "=" * 64,
        f"Ulasan masuk   : {s['jumlah_ulasan']}",
        f"Rata-rata ★    : {s['rata_bintang']}",
        f"Pelanggan puas : {s['persen_puas']}%   | ulasan negatif: {s['ulasan_negatif']}"
        f"   | puas tapi ada keluhan: {s['ulasan_campuran']}",
        "",
        "Per topik (jumlah ulasan yang memuji / mengeluh):",
    ]
    for t in TOPIK:
        p, n = s["per_topik"][t]["positif"], s["per_topik"][t]["negatif"]
        baris.append(f"  {t:<10} 👍 {p:>3}   👎 {n:>3}   {'█' * n}")
    K = L["keluhan"]
    baris += ["", "-" * 64, "YANG PERLU DIPERBAIKI", "-" * 64, K.get("ringkasan", "")]
    for i, k in enumerate(K.get("keluhan", []), 1):
        baris.append(f"\n{i}. [{k.get('prioritas', '-').upper()}] {k.get('topik', '').upper()} — "
                     f"{k.get('masalah_utama', '')} ({k.get('jumlah_ulasan', '?')} ulasan; bukti: "
                     f"{', '.join(map(str, k.get('bukti_id', [])[:5]))})")
        for a in k.get("saran_tindakan", []):
            baris.append(f"   → {a}")
        if k.get("indikator_berhasil"):
            baris.append(f"   ✓ Cek minggu depan: {k['indikator_berhasil']}")
    if K.get("ulasan_perlu_dibalas"):
        baris += ["", "Ulasan yang sebaiknya dibalas di Google Maps:"]
        for u in K["ulasan_perlu_dibalas"]:
            baris.append(f"  • {u.get('id')}: {u.get('alasan', '')}\n    Draf: {u.get('draf_balasan', '')}")
    P = L["positif"]
    baris += ["", "-" * 64, "YANG SUDAH BAGUS (PERTAHANKAN & PROMOSIKAN)", "-" * 64, P.get("ringkasan", "")]
    for k in P.get("kekuatan", []):
        baris.append(f"  • {k.get('topik', '').upper()}: {k.get('yang_dipuji', '')} "
                     f"({k.get('jumlah_ulasan', '?')} ulasan)")
        if k.get("cara_mempertahankan"):
            baris.append(f"    → {k['cara_mempertahankan']}")
    if P.get("ide_promosi"):
        baris.append("\nIde promosi:")
        for k in P["ide_promosi"]:
            baris.append(f"  • {k.get('ide', '')} [{k.get('kanal', '')}]")
            if k.get("contoh_caption"):
                baris.append(f"    Caption: \"{k['contoh_caption']}\"")
    baris += ["", "-" * 64,
              "Catatan: sentimen & topik dibaca per bagian kalimat oleh model lokal; kata pemicu dari SHAP;",
              "ringkasan & saran ditulis LLM hanya dari ulasan di atas. Keputusan tetap di kepala cabang.",
              "=" * 64]
    return "\n".join(baris)
