-- Voice of Customer - skema PostgreSQL lengkap (10 tabel)
-- Di Docker, berkas ini dijalankan otomatis saat database PERTAMA KALI dibuat
-- (volume pgdata masih kosong). Database yang sudah berisi data tidak perlu menjalankannya lagi.
-- Aman dijalankan ulang: IF NOT EXISTS dan ON CONFLICT DO NOTHING.
-- Pelanggan anonim: tidak ada nama, telepon, atau email pelanggan (UU PDP).

-- =====================================================================
-- AKUN DASHBOARD
-- =====================================================================
CREATE TABLE IF NOT EXISTS users (
  id       SERIAL PRIMARY KEY,
  name     VARCHAR(100) NOT NULL,
  email    VARCHAR(150) NOT NULL UNIQUE,
  password VARCHAR(255) NOT NULL,  -- hash bcrypt, bukan password asli
  role     VARCHAR(20)  NOT NULL DEFAULT 'staff' CHECK (role IN ('kepala_cabang', 'staff'))
);

-- =====================================================================
-- ULASAN
--   source        : 'qr' dari form pelanggan; 'google_maps' / 'social_media' diinput staf
--   text          : komentar; boleh kosong bila pelanggan hanya memberi bintang
--   gender, age   : opsional dari form QR; NULL bila tidak diisi
--   rating_*      : bintang 1-5 per aspek dari form QR
--   rating        : bintang 1-5 ulasan Google Maps / media sosial
--   review_date   : tanggal ulasan asli di Google Maps / media sosial
--   responded_*   : kapan dan oleh siapa ulasan ditandai "Sudah Ditanggapi"
--   ip_hash       : sidik IP pengirim form (HMAC), bukan IP asli
-- =====================================================================
CREATE TABLE IF NOT EXISTS reviews (
  id               SERIAL PRIMARY KEY,
  source           VARCHAR(20) NOT NULL CHECK (source IN ('qr', 'google_maps', 'social_media')),
  text             TEXT,
  gender           VARCHAR(10) CHECK (gender IN ('laki-laki', 'perempuan')),
  age              SMALLINT    CHECK (age BETWEEN 10 AND 90),
  rating_rasa      SMALLINT    CHECK (rating_rasa BETWEEN 1 AND 5),
  rating_harga     SMALLINT    CHECK (rating_harga BETWEEN 1 AND 5),
  rating_pelayanan SMALLINT    CHECK (rating_pelayanan BETWEEN 1 AND 5),
  rating_tempat    SMALLINT    CHECK (rating_tempat BETWEEN 1 AND 5),
  rating           SMALLINT    CHECK (rating BETWEEN 1 AND 5),
  review_date      DATE,
  responded_at     TIMESTAMPTZ,
  responded_by     INTEGER REFERENCES users (id) ON DELETE SET NULL,
  ip_hash          CHAR(64),
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- Setiap ulasan minimal berisi komentar atau satu bintang.
  CONSTRAINT reviews_has_content CHECK (
    text IS NOT NULL OR rating IS NOT NULL OR rating_rasa IS NOT NULL
    OR rating_harga IS NOT NULL OR rating_pelayanan IS NOT NULL OR rating_tempat IS NOT NULL
  )
);
CREATE INDEX IF NOT EXISTS idx_reviews_created_at ON reviews (created_at);
CREATE INDEX IF NOT EXISTS idx_reviews_source ON reviews (source);

CREATE TABLE IF NOT EXISTS topics (
  id   SERIAL PRIMARY KEY,
  name VARCHAR(50) NOT NULL UNIQUE
);

-- Topik yang disinggung tiap ulasan. assigned_by: 'staf' (input manual) atau 'ai'.
CREATE TABLE IF NOT EXISTS review_topics (
  review_id   INTEGER NOT NULL REFERENCES reviews (id) ON DELETE CASCADE,
  topic_id    INTEGER NOT NULL REFERENCES topics (id),
  assigned_by VARCHAR(10) NOT NULL DEFAULT 'staf' CHECK (assigned_by IN ('staf', 'ai')),
  PRIMARY KEY (review_id, topic_id)
);
CREATE INDEX IF NOT EXISTS idx_review_topics_topic ON review_topics (topic_id);

-- Daftar menu kedai. Belum diisi: disiapkan untuk filter dan grafik menu (API 6).
CREATE TABLE IF NOT EXISTS menus (
  id        SERIAL PRIMARY KEY,
  name      VARCHAR(100) NOT NULL UNIQUE,
  is_active BOOLEAN      NOT NULL DEFAULT TRUE
);

-- Menu yang disebut dalam komentar ulasan.
CREATE TABLE IF NOT EXISTS review_menus (
  review_id INTEGER NOT NULL REFERENCES reviews (id) ON DELETE CASCADE,
  menu_id   INTEGER NOT NULL REFERENCES menus (id),
  PRIMARY KEY (review_id, menu_id)
);
CREATE INDEX IF NOT EXISTS idx_review_menus_menu ON review_menus (menu_id);

-- =====================================================================
-- HASIL AI
-- =====================================================================
-- Satu baris per ulasan yang sudah dianalisis model.
CREATE TABLE IF NOT EXISTS review_analysis (
  review_id       INTEGER PRIMARY KEY REFERENCES reviews (id) ON DELETE CASCADE,
  sentiment       VARCHAR(12) NOT NULL CHECK (sentiment IN ('puas', 'tidak_puas')),
  sentiment_score NUMERIC(4, 3) CHECK (sentiment_score BETWEEN 0 AND 1),
  topic_id        INTEGER REFERENCES topics (id),
  topic_score     NUMERIC(4, 3) CHECK (topic_score BETWEEN 0 AND 1),
  explanation     JSONB,          -- kata berpengaruh (SHAP) dan semua topik ulasan
  model_version   VARCHAR(50),
  analyzed_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Laporan mingguan dari AI (aksi "laporan" di predict_bridge.py).
CREATE TABLE IF NOT EXISTS weekly_reports (
  id             SERIAL PRIMARY KEY,
  period_start   DATE    NOT NULL,
  period_end     DATE    NOT NULL,
  total_reviews  INTEGER NOT NULL CHECK (total_reviews >= 0),
  negative_count INTEGER NOT NULL CHECK (negative_count >= 0),
  positive_count INTEGER NOT NULL CHECK (positive_count >= 0),
  result         JSONB   NOT NULL,  -- jawaban lengkap dari AI
  llm_model      VARCHAR(100),
  llm_note       VARCHAR(100),      -- mis. BELUM ADA KUNCI API
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT weekly_reports_period_valid CHECK (period_end >= period_start),
  CONSTRAINT weekly_reports_period_unique UNIQUE (period_start, period_end)
);

-- =====================================================================
-- TINDAK LANJUT KEPALA CABANG
-- =====================================================================
-- Saran Tindakan Aktif dan Riwayat Saran yang Sudah Dilaksanakan.
--   kind: 'perbaikan' (dari keluhan) atau 'kekuatan' (dari pujian)
CREATE TABLE IF NOT EXISTS suggestions (
  id              SERIAL PRIMARY KEY,
  report_id       INTEGER REFERENCES weekly_reports (id) ON DELETE SET NULL,
  topic_id        INTEGER NOT NULL REFERENCES topics (id),
  kind            VARCHAR(12) NOT NULL DEFAULT 'perbaikan' CHECK (kind IN ('perbaikan', 'kekuatan')),
  priority        VARCHAR(10) NOT NULL CHECK (priority IN ('mendesak', 'sedang', 'rendah')),
  text            TEXT        NOT NULL,
  reason          TEXT,
  complaint_count INTEGER     NOT NULL DEFAULT 0 CHECK (complaint_count >= 0),
  status          VARCHAR(10) NOT NULL DEFAULT 'aktif' CHECK (status IN ('aktif', 'selesai')),
  completed_at    TIMESTAMPTZ,
  completed_by    INTEGER REFERENCES users (id) ON DELETE SET NULL,
  completion_note VARCHAR(300),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- Status "selesai" wajib punya waktu selesai, status "aktif" tidak boleh.
  CONSTRAINT suggestions_completed_consistent CHECK ((status = 'selesai') = (completed_at IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_suggestions_status ON suggestions (status);
CREATE INDEX IF NOT EXISTS idx_suggestions_topic ON suggestions (topic_id);

-- Pengaturan dashboard (ambang munculnya saran, interval saran).
CREATE TABLE IF NOT EXISTS settings (
  key        VARCHAR(50)  PRIMARY KEY,
  value      VARCHAR(100) NOT NULL,
  updated_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
  updated_by INTEGER REFERENCES users (id) ON DELETE SET NULL
);

-- =====================================================================
-- DATA AWAL
-- =====================================================================
INSERT INTO topics (name) VALUES ('Rasa'), ('Harga'), ('Pelayanan'), ('Tempat')
ON CONFLICT (name) DO NOTHING;

INSERT INTO settings (key, value) VALUES ('ambang_saran', '5'), ('interval_saran', 'mingguan')
ON CONFLICT (key) DO NOTHING;