<div align="center">
  <img src="assets/logo.png" alt="logo deepseek-web-shim" width="128" height="128">
  <h1>deepseek-web-shim</h1>
  <p>Server lokal kompatibel OpenAI di depan web chat DeepSeek.<br>
  Proof-of-work-nya ditulis ulang dalam Python dan diverifikasi terhadap modul wasm milik vendor itu sendiri.</p>
  <p>
    <a href="https://github.com/0xgetz/deepseek-web-shim/releases"><img src="https://img.shields.io/github/v/release/0xgetz/deepseek-web-shim?style=flat-square" alt="rilis"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-3fb950?style=flat-square" alt="lisensi MIT"></a>
    <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.9%2B-blue?style=flat-square" alt="Python 3.9+"></a>
    <a href="tests"><img src="https://img.shields.io/badge/tests-54%20offline-2ea44f?style=flat-square" alt="54 tes offline"></a>
  </p>
  <p>
    <a href="README.md">English</a> ·
    <strong>Bahasa Indonesia</strong> ·
    <a href="README.zh-CN.md">简体中文</a> ·
    <a href="README.ja.md">日本語</a> ·
    <a href="README.ko.md">한국어</a>
  </p>
</div>

---

## Apa ini

Alat riset yang berbicara dengan protokol yang sama seperti `chat.deepseek.com`,
ditulis dari Python, lalu dipaparkan sebagai endpoint kompatibel OpenAI:

```bash
export DSW_API_KEY=local   # any value; it guards your own local port
curl http://127.0.0.1:8712/v1/chat/completions \
  -H "Authorization: Bearer local" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-web","messages":[{"role":"user","content":"halo"}]}'
```

Ada dua bagian yang layak dibaca meski Anda tidak pernah menjalankan servernya:

1. **Proof-of-work-nya, terverifikasi.** Tantangan DeepSeek bukan teka-teki
   leading zero, dan hash-nya bukan SHA3 standar maupun Keccak standar. Ia
   Keccak-f[1600] dengan **23 ronde** (round constant ke-0 dilewati), rate 136,
   padding `0x06`, dan tantangannya adalah **target preimage**: server memilih
   sebuah jawaban, menghash-nya, lalu meminta Anda menemukan preimage-nya di
   dalam batas difficulty. Lihat [`docs/protocol.md`](docs/protocol.md).
2. **Klien yang bisa diuji.** Hash Python mereproduksi keluaran modul wasm
   DeepSeek byte per byte, dan itulah yang membuat shim ini bisa jalan tanpa
   perlu ikut mendistribusikan biner mereka. Skrip riset yang memastikan hal ini,
   termasuk dua hipotesis yang salah, ada di [`research/`](research/README.md).

## Pasang

```bash
git clone https://github.com/0xgetz/deepseek-web-shim
cd deepseek-web-shim
uv venv && uv pip install -e ".[dev]"
```

## Ambil sesi

Shim ini berjalan di atas sesi **milik Anda sendiri**. Buka `chat.deepseek.com`
di browser, login, lalu di DevTools buka Network, kirim pesan apa saja, klik
permintaan `completion` dan salin nilai header `authorization`.

```bash
echo 'Bearer <tempel token Anda di sini>' > /tmp/tok.txt
PYTHONPATH=src python -m deepseek_web_shim --session /tmp/tok.txt
# {"saved": "...", "token_len": ..., "cookies": 0, ...}
rm /tmp/tok.txt        # token kini ada di ~/.deepseek-web-shim/session.json (mode 0600)
```

## Jalankan

```bash
PYTHONPATH=src DSW_API_KEY=local python -m deepseek_web_shim --serve
# GET  /healthz              -> {"ok":true,"pow_backend":"pure","authenticated":true}
# GET  /v1/models            -> deepseek-web, deepseek-web-reasoner, deepseek-web-search
# POST /v1/chat/completions  -> skema OpenAI, stream=true|false
```

Arahkan klien kompatibel OpenAI mana pun ke `http://127.0.0.1:8712/v1`.

| Nama model | Dipetakan ke |
| --- | --- |
| `deepseek-web` | model web default |
| `deepseek-web-reasoner` | `thinking_enabled: true` |
| `deepseek-web-search` | `search_enabled: true` |

## Buktikan sendiri

```bash
PYTHONPATH=src python -m pytest tests/ -q          # 54 passed, 1 skipped, 0 failed
PYTHONPATH=src python -m deepseek_web_shim --selftest
# {"backend":"pure","planted":11,"pure_answer":11,"match":true}
```

Suite-nya sepenuhnya offline: tidak ada tes yang menyentuh jaringan.
`test_pow.py` memaku hash ke vektor known-answer yang dibekukan, dan
`test_server.py` menjalankan aplikasi ASGI asli melawan server hulu palsu yang
disuntikkan.

Untuk membandingkan hash Python dengan oracle wasm DeepSeek, ambil sendiri modul
itu (di sini **tidak** didistribusikan) lalu jalankan ulang:

```bash
python scripts/fetch_wasm.py                       # mencatat sha256 yang didapat
python scripts/fetch_wasm.py --file ~/Downloads/sha3_wasm_bg.7b9ca65ddd.wasm   # atau pakai salinan yang sudah Anda punya
PYTHONPATH=src DSW_WASM=wasm/sha3_wasm_bg.wasm python -m pytest tests/test_pow.py
```

## PoW cepat vs lambat

| Backend | Kecepatan | Perlu |
| --- | --- | --- |
| `wasm` | cepat | modul wasm DeepSeek, Anda sendiri yang mengambil (`DSW_WASM=`) |
| `pure` | sekitar 1,9 ribu hash/detik | tidak ada, ini kode di repo ini |

Keduanya menghasilkan **digest identik**, jadi pilihannya hanya soal latensi.
`--selftest` mencetak mana yang sedang aktif.

## Konfigurasi

Semuanya lewat environment, tidak pernah ikut ter-commit. Lihat
[`.env.example`](.env.example).

| Variabel | Arti |
| --- | --- |
| `DSW_API_KEY` | kunci yang harus dibawa klien; wajib, karena port ini di depan sesi Anda |
| `DSW_ALLOW_NO_AUTH` | set ke `1` untuk sengaja jalan tanpa kunci, loopback saja |
| `DSW_HOST` / `DSW_PORT` | alamat bind, default `127.0.0.1:8712` |
| `DS_TOKEN` | token bearer DeepSeek, alternatif dari `--session` |
| `DSW_STATE_DIR` | tempat sesi yang ditangkap disimpan |
| `DSW_WASM` | path ke modul wasm opsional |
| `DSW_POW_BACKEND` | set ke `pure` untuk memaksa backend Python murni walau modulnya ada |
| `DS_PROXY` | proxy residensial untuk leg keluar, jika IP Anda ditolak |

## Baca ini sebelum memakainya

Ini alat riset, bukan cara pintas akses. Ia mengirim **tanpa kredensial**, tidak
pernah membuat akun, dan tidak memecahkan CAPTCHA. Ia berjalan di sesi Anda, jadi
batas akun Anda dan eksposur akun Anda tetap berlaku. Akses otomatis ke
antarmuka web bisa melanggar ketentuan layanan itu; itu keputusan dan risiko
Anda. Teks lengkap: [`docs/intended-use.md`](docs/intended-use.md).

Ia membaca protokol yang tidak terdokumentasi, jadi ia akan rusak saat server hulu
berubah. Saat itu terjadi, ia dirancang gagal dengan terang lewat error JSON yang
dinamai (`not_authenticated`, `upstream_error`), bukan diam-diam mengembalikan
jawaban salah. Jawaban salah yang senyap adalah bug yang layak dilaporkan.

Kalau Anda butuh akses yang stabil, pakai API resminya. API resmi
terdokumentasi, didukung, dan menghapus semua catatan di halaman ini.

## Struktur

```
src/deepseek_web_shim/   pow.py (hash + pencarian terverifikasi), client.py (alur web),
                         server.py (shim OpenAI), config.py, __main__.py (CLI)
tests/                   54 tes offline
research/                skrip di balik kesimpulannya, termasuk jalan yang salah
docs/                    protocol.md, intended-use.md
scripts/fetch_wasm.py    pengambil wasm opsional, mencetak sha256-nya
```

## Lisensi

MIT. Lihat [LICENSE](LICENSE).
