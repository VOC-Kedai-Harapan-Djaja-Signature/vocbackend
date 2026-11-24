const json = (schema) => ({ content: { 'application/json': { schema } } });
const ref = (name) => ({ $ref: `#/components/schemas/${name}` });
const fail = (description) => ({ description, ...json(ref('Message')) });

const LOGIN = [{ bearerAuth: [] }];
const stars = (description) => ({ type: 'integer', minimum: 1, maximum: 5, nullable: true, description });
const query = (name, schema, description) => ({ name, in: 'query', required: false, schema, description });

export const swaggerSpec = {
  openapi: '3.0.3',
  info: {
    title: 'Voice of Customer API',
    version: '1.0.0',
    description: 'Back-end Voice of Customer.',
  },
  servers: [{ url: '/api' }],
  tags: [
    { name: 'Auth' },
    { name: 'Ulasan' },
    { name: 'Pengaturan' },
    { name: 'Laporan AI' },
    { name: 'Saran' },
  ],
  components: {
    securitySchemes: {
      bearerAuth: { type: 'http', scheme: 'bearer', bearerFormat: 'JWT' },
    },
    schemas: {
      Message: { type: 'object', properties: { message: { type: 'string' } } },
      Suggestion: {
        type: 'object',
        properties: {
          id: { type: 'integer' },
          kind: { type: 'string', enum: ['perbaikan', 'kekuatan'] },
          priority: { type: 'string', enum: ['mendesak', 'sedang', 'rendah'] },
          topic: { type: 'string', example: 'pelayanan' },
          text: { type: 'string' },
          reason: { type: 'string', nullable: true },
          complaint_count: { type: 'integer' },
          status: { type: 'string', enum: ['aktif', 'selesai'] },
          period_start: { type: 'string', format: 'date', nullable: true },
          period_end: { type: 'string', format: 'date', nullable: true },
          created_at: { type: 'string', format: 'date-time' },
          completed_at: { type: 'string', format: 'date-time', nullable: true },
          completed_by: { type: 'string', nullable: true, description: 'Nama yang menandai selesai' },
          completion_note: { type: 'string', nullable: true },
        },
      },
      Settings: {
        type: 'object',
        properties: {
          suggestion_threshold: { type: 'integer', minimum: 2, maximum: 25, example: 5, description: 'Jumlah keluhan baru sebelum saran muncul' },
          suggestion_interval: { type: 'string', enum: ['mingguan', '2_mingguan', '3_mingguan', 'bulanan'], example: 'mingguan' },
        },
      },
      PublicReviewInput: {
        type: 'object',
        description: 'Kiriman form QR. Minimal satu bintang atau komentar. Field lain diabaikan.',
        properties: {
          comment: { type: 'string', minLength: 3, maxLength: 2000, nullable: true, example: 'Kopinya enak, tapi antrenya lama.' },
          ratings: {
            type: 'object',
            properties: {
              rasa: stars('Bintang rasa'),
              harga: stars('Bintang harga'),
              pelayanan: stars('Bintang pelayanan'),
              tempat: stars('Bintang tempat'),
            },
            example: { rasa: 5, harga: 4, pelayanan: 2, tempat: null },
          },
          gender: { type: 'string', enum: ['laki-laki', 'perempuan', 'tidak_dijawab'], nullable: true, example: 'perempuan' },
          age: { type: 'integer', minimum: 10, maximum: 90, nullable: true, example: 21 },
        },
      },
      ManualReviewInput: {
        type: 'object',
        required: ['text', 'source', 'rating'],
        properties: {
          text: { type: 'string', minLength: 3, maxLength: 2000, example: 'Pesanan datang 40 menit, padahal sepi.' },
          source: { type: 'string', enum: ['google_maps', 'social_media'], example: 'google_maps' },
          rating: { type: 'integer', minimum: 1, maximum: 5, example: 2 },
          review_date: { type: 'string', format: 'date', nullable: true, example: '2026-11-20' },
          topic: { type: 'string', enum: ['rasa', 'harga', 'pelayanan', 'tempat'], nullable: true, example: 'pelayanan' },
        },
      },
      ReviewItem: {
        type: 'object',
        properties: {
          id: { type: 'integer', example: 12 },
          source: { type: 'string', enum: ['qr', 'google_maps', 'social_media'] },
          date: { type: 'string', format: 'date', example: '2026-11-21', description: 'Tanggal ulasan (WIB)' },
          created_at: { type: 'string', format: 'date-time' },
          text: { type: 'string', nullable: true },
          gender: { type: 'string', enum: ['laki-laki', 'perempuan'], nullable: true },
          age: { type: 'integer', nullable: true },
          ratings: {
            type: 'object',
            properties: { rasa: stars(), harga: stars(), pelayanan: stars(), tempat: stars() },
          },
          rating: stars('Bintang ulasan manual'),
          average_rating: { type: 'number', nullable: true, example: 3.7 },
          satisfied: { type: 'boolean', nullable: true, description: 'null = belum diketahui' },
          satisfied_basis: { type: 'string', enum: ['ai', 'bintang'], nullable: true },
          topics: { type: 'array', items: { type: 'string' }, example: ['pelayanan'] },
          menus: { type: 'array', items: { type: 'string' } },
          responded: { type: 'boolean' },
          responded_at: { type: 'string', format: 'date-time', nullable: true },
          responded_by: { type: 'string', nullable: true, description: 'Nama staf yang menandai' },
        },
      },
    },
  },
  paths: {
    '/login': {
      post: {
        tags: ['Auth'],
        summary: 'Masuk dan mendapat token JWT',
        requestBody: {
          required: true,
          ...json({
            type: 'object',
            required: ['email', 'password'],
            properties: {
              email: { type: 'string', format: 'email', example: 'admin@contoh.id' },
              password: { type: 'string', format: 'password' },
            },
          }),
        },
        responses: {
          200: { description: 'Berhasil', ...json({ type: 'object', properties: { token: { type: 'string' } } }) },
          401: fail('Email atau password salah'),
          422: fail('Email atau password tidak diisi'),
          429: fail('Terlalu banyak percobaan'),
        },
      },
    },
    '/reviews': {
        get: {
        tags: ['Ulasan'],
        summary: 'Daftar ulasan untuk dashboard (urut terbaru)',
        security: LOGIN,
        parameters: [
          query('from', { type: 'string', format: 'date' }, 'Mulai tanggal (YYYY-MM-DD)'),
          query('to', { type: 'string', format: 'date' }, 'Sampai tanggal (YYYY-MM-DD)'),
          query('source', { type: 'string', enum: ['qr', 'google_maps', 'social_media'] }),
          query('topic', { type: 'string', enum: ['rasa', 'harga', 'pelayanan', 'tempat'] }),
          query('responded', { type: 'boolean' }, 'true = sudah ditanggapi, false = belum'),
          query('limit', { type: 'integer', minimum: 1, maximum: 1000, default: 500 }),
          query('offset', { type: 'integer', minimum: 0, default: 0 }),
        ],
        responses: {
          200: {
            description: 'Berhasil',
            ...json({
              type: 'object',
              properties: {
                data: { type: 'array', items: ref('ReviewItem') },
                total: { type: 'integer', description: 'Jumlah semua ulasan yang cocok dengan filter' },
                limit: { type: 'integer' },
                offset: { type: 'integer' },
              },
            }),
          },
          401: fail('Belum login'),
          422: fail('Filter tidak valid'),
        },
      },
      post: {
        tags: ['Ulasan'],
        summary: 'Pelanggan mengirim masukan dari form QR (publik, tanpa data pribadi)',
        requestBody: { required: true, ...json(ref('PublicReviewInput')) },
        responses: {
          201: {
            description: 'Tersimpan',
            ...json({ type: 'object', properties: { id: { type: 'integer' }, message: { type: 'string' } } }),
          },
          422: fail('Tidak ada bintang maupun komentar, atau isian di luar batas'),
          429: fail('Terlalu banyak kiriman'),
        },
      },
    },
    '/reviews/{id}/respond': {
      patch: {
        tags: ['Ulasan'],
        summary: 'Tandai ulasan sudah / belum ditanggapi',
        security: LOGIN,
        parameters: [{ name: 'id', in: 'path', required: true, schema: { type: 'integer' } }],
        requestBody: {
          required: true,
          ...json({
            type: 'object',
            required: ['responded'],
            properties: { responded: { type: 'boolean', example: true } },
          }),
        },
        responses: {
          200: {
            description: 'Berhasil',
            ...json({
              type: 'object',
              properties: {
                id: { type: 'integer' },
                responded: { type: 'boolean' },
                responded_at: { type: 'string', format: 'date-time', nullable: true },
              },
            }),
          },
          401: fail('Belum login'),
          404: fail('Ulasan tidak ditemukan'),
          422: fail('Isian tidak valid'),
        },
      },
    },
    '/reports/weekly': {
      post: {
        tags: ['Laporan AI'],
        summary: 'Buat / perbarui laporan mingguan (analisis AI, maks. 100 ulasan terbaru)',
        security: LOGIN,
        requestBody: {
          required: false,
          ...json({
            type: 'object',
            properties: {
              from: { type: 'string', format: 'date', example: '2026-11-16', description: 'Bawaan: 6 hari sebelum to' },
              to: { type: 'string', format: 'date', example: '2026-11-22', description: 'Bawaan: hari ini (WIB)' },
            },
          }),
        },
        responses: {
          201: { description: 'Laporan tersimpan (jumlah ulasan, yang dianalisis, saran yang dibuat)' },
          401: fail('Belum login'),
          422: fail('Periode tidak valid atau belum ada ulasan berkomentar'),
          502: fail('AI gagal membuat laporan'),
          503: fail('AI belum siap atau terlalu lama menjawab'),
        },
      },
    },
    '/reports/weekly/latest': {
      get: {
        tags: ['Laporan AI'],
        summary: 'Laporan terbaru: ringkasan, kata kunci keluhan, saran prioritas, ide promosi',
        security: LOGIN,
        responses: {
          200: { description: 'Berhasil' },
          401: fail('Belum login'),
          404: fail('Belum ada laporan'),
        },
      },
    },
    '/health': {
      get: {
        tags: ['Laporan AI'],
        summary: 'Status API dan AI (mati / memuat / siap), serta ada kunci LLM atau tidak',
        responses: { 200: { description: 'Berhasil' } },
      },
    },
    '/suggestions': {
      get: {
        tags: ['Saran'],
        summary: 'Saran aktif (dari laporan AI terbaru) atau riwayat saran selesai',
        security: LOGIN,
        parameters: [query('status', { type: 'string', enum: ['aktif', 'selesai'], default: 'aktif' })],
        responses: {
          200: { description: 'Berhasil', ...json({ type: 'object', properties: { data: { type: 'array', items: ref('Suggestion') } } }) },
          401: fail('Belum login'),
          422: fail('status tidak valid'),
        },
      },
    },
    '/suggestions/{id}/complete': {
      patch: {
        tags: ['Saran'],
        summary: 'Tandai saran sudah dilaksanakan (khusus Kepala Cabang)',
        security: LOGIN,
        parameters: [{ name: 'id', in: 'path', required: true, schema: { type: 'integer' } }],
        requestBody: {
          required: false,
          ...json({
            type: 'object',
            properties: {
              note: { type: 'string', maxLength: 300, nullable: true, example: 'Sudah briefing barista soal antrean jam sibuk.' },
            },
          }),
        },
        responses: {
          200: { description: 'Berhasil', ...json(ref('Suggestion')) },
          401: fail('Belum login'),
          403: fail('Bukan Kepala Cabang'),
          404: fail('Saran tidak ditemukan'),
          409: fail('Saran sudah ditandai selesai'),
          422: fail('ID atau catatan tidak valid, atau bukan saran perbaikan'),
        },
      },
    },
    '/settings': {
      get: {
        tags: ['Pengaturan'],
        summary: 'Ambang dan interval saran saat ini',
        security: LOGIN,
        responses: {
          200: { description: 'Berhasil', ...json(ref('Settings')) },
          401: fail('Belum login'),
        },
      },
      patch: {
        tags: ['Pengaturan'],
        summary: 'Ubah ambang dan/atau interval saran (khusus Kepala Cabang)',
        security: LOGIN,
        requestBody: { required: true, ...json(ref('Settings')) },
        responses: {
          200: { description: 'Tersimpan', ...json(ref('Settings')) },
          401: fail('Belum login'),
          403: fail('Bukan Kepala Cabang'),
          422: fail('Isian tidak valid'),
        },
      },
    },
    '/reviews/manual': {
      post: {
        tags: ['Ulasan'],
        summary: 'Staf menginput ulasan dari Google Maps dan sejenisnya',
        security: LOGIN,
        requestBody: { required: true, ...json(ref('ManualReviewInput')) },
        responses: {
          201: { description: 'Tersimpan', ...json({ type: 'object', properties: { id: { type: 'integer' } } }) },
          401: fail('Belum login'),
          422: fail('Isian tidak valid'),
        },
      },
    },
  },
};