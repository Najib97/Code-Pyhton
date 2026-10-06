"""
CCTV Bapenda - AI Traffic Counting v5
-------------------------------------
Saat program mulai: (1) masukkan URL stream, (2) gambar 3 area langsung di layar.
Area SELALU direset dan digambar ulang setiap program dijalankan (tidak disimpan):
    1) AREA INISIALISASI (KUNING)
    2) AREA COUNTING MOTOR (HIJAU)
    3) AREA COUNTING MOBIL (MERAH)
Aturan:
  * Kendaraan harus lebih dulu menyentuh area KUNING (inisialisasi).
  * Counting tidak memakai bagian dalam/border area sebagai indikator. Motor dihitung saat BADAN kendaraan
    menyentuh/menyeberangi GARIS HIJAU; mobil/bus/truk saat RODA atau BADAN kendaraan
    menyentuh/menyeberangi GARIS MERAH.
  * Deteksi YOLO berjalan di PROSES TERPISAH dari jendela tampilan, supaya jendela tidak "Not Responding"
    walau ada banyak kendaraan sekaligus / deteksi sedang berat.
  * Setiap ID hanya dihitung SATU KALI selama program berjalan.
  * KENDARAAN PARKIR TIDAK DIHITUNG: objek yang diam (posisi hampir tidak berubah selama PARK_WINDOW_SEC)
    ditandai PARKIR dan diabaikan. Counting hanya untuk kendaraan yang BERGERAK dan benar-benar MELINTASI
    area hijau (motor) / merah (mobil) setelah sebelumnya berada di luar area tersebut.
  * Arah satu arah: hanya kuning -> hijau/merah yang dihitung. Urutan sentuh TITIK KAKI (bidang tanah)
    harus KUNING DULU baru HIJAU/MERAH. Kendaraan yang lebih dulu menyentuh hijau/merah baru ke kuning
    (arah balik) ditandai ARAH BALIK dan tidak pernah dihitung.
  * Kendaraan yang sempat BERHENTI sebentar (mis. di pos/tenda kuning) lalu jalan lagi tetap bisa dihitung
    (PARKED_CAN_RESUME_COUNT). Parkir permanen tidak pernah dihitung karena tidak pernah bergerak melintas.
  * Bila ByteTrack mengganti ID di tengah jalan, track lama disambung ke ID baru (relink dengan prediksi gerak).
  * INISIALISASI LEWAT GERAK (v10): kendaraan yang baru terdeteksi setelah keluar dari bayangan/halangan (mis. di
    bawah tenda: kaki sudah di hijau, hanya BADAN yang masih menyentuh kuning) tetap sah bila badannya menyentuh
    kuning DAN ia bergerak maju searah kuning -> hijau/merah. Arah balik tetap ditolak karena geraknya mundur.
  * MODE FPS RENDAH: (a) titik masuk kuning diperkirakan dari LINTASAN antar-frame, bukan posisi kaki sekarang;
    (b) sentuhan garis hijau/merah DIKUNCI (kunci lintas), jadi observasi konfirmasi berikutnya tidak harus masih
    menyentuh garis -- cukup tidak mundur. Kunci dilepas bila kendaraan mundur (lonjakan bbox, bukan lintasan);
    (c) waktu gerak memakai waktu frame, bukan waktu selesai inferensi; (d) foto capture = saat menyentuh garis.
  * ANTI-DUPLIKAT: dua ID pada kendaraan yang sama / ID yang berganti setelah terhitung tidak dihitung dua kali.
  * SAPUAN AKHIR (MISSED_FLUSH): bila sebuah track jelas melintas (kuning -> menyentuh hijau/merah, bergerak jauh,
    mendekat) tetapi pada saat itu tidak lolos gerbang per-frame (deteksi putus-putus, ID berganti, dsb.),
    kendaraan tetap dihitung begitu track-nya berakhir, memakai foto saat pertama menyentuh area counting.
  * Mode debug (tombol d): setiap kendaraan diberi label ALASAN real-time kenapa belum/tidak terhitung.
  * Debug: saat sebuah track menyentuh area counting tetapi TIDAK terhitung, konsol mencetak baris
    [DIAG] berisi alasannya (DIAG_LOG = True).
  * Setiap capture yang terhitung otomatis ditambahkan ke log_capture_kendaraan.xlsx (ditulis ulang
    berkala di thread background; bila file sedang dibuka di Excel, ditunda lalu disinkronkan otomatis).
  * Arah masuk otomatis: motor = pusat kuning -> pusat hijau, mobil = pusat kuning -> pusat merah.
  * Gambar area merah agar mencakup titik tempat mobil berhenti/parkir (titik kaki = titik magenta
    di bawah bounding box) dan JANGAN menyentuh badan jalan raya.

Cara pakai:
  python traffic_counter_v5.py                      -> program menanyakan URL stream (Enter = URL default)
  python traffic_counter_v5.py "<URL stream>"        -> langsung pakai URL tersebut
URL yang diterima:
  - https://panel.jastrak.id/dashboard/video-stream?id=<UUID>   (ID diambil dari parameter id)
  - <UUID> saja
  - rtsp:// , rtmp:// , atau http(s):// stream langsung (tanpa login Jasnita)

Saat menggambar ROI:
  Klik kiri = tambah titik | Klik kanan / Backspace = undo titik
  ENTER = selesai satu area (minimal 3 titik) | C = ulang area ini
  F = ambil frame baru | Q / Esc = batal
  Setelah 3 area lengkap: ENTER = mulai | R = ulang semua | M = ulang area merah saja

Output (disimpan di folder yang sama dengan script):
  capture/<CCTV_ID>/<mobil|motor>/<tanggal>/HHMMSS_ID<n>_track<id>.jpg   foto tiap kendaraan terhitung
  log_kendaraan_terhitung.csv               log utama format Excel Bapenda (ID/NOP/CCTV_ID/NAMA_OP/.../VENDOR)
  ringkasan_hitungan.csv                    id CCTV / URL stream, jumlah mobil & motor (tiap 60 dtk jika berubah,
                                            dan 1 baris saat program berhenti)
  log_koneksi_stream.csv                    riwayat sambung/terputus/refresh stream + durasi -> utk cari pola jam sering putus
  laporan/laporan_<id_cctv>_<tanggal>.html  dashboard HTML per CCTV (dibuat ulang tiap ringkasan & saat keluar)

Laporan HTML (tanpa menjalankan kamera):
  python traffic_counter_v5.py --report                -> buat laporan utk semua ID CCTV yang ada di log hari ini
  python traffic_counter_v5.py --report "<id_cctv>"     -> buat laporan utk satu ID CCTV saja

Saat counting:
  q = keluar | d = tampilkan semua deteksi (debug) | r = edit/gambar ulang ROI
  klik kiri kendaraan = beri/hapus TANDA X MERAH (dikecualikan, tidak pernah dihitung) | c = hapus semua tanda X
  Tanda X ikut pindah bila ID tracker berganti; kendaraan parkir bertanda X tetap dikecualikan walau sempat hilang
  dari deteksi (EXCLUDE_KEEP_PARKED_SEC). Kendaraan yang SUDAH terhitung sebelum diberi X tidak dikurangi.
  z = +1 motor MANUAL (ground truth) | x = +1 mobil MANUAL (ground truth)
"""
import base64
import csv
import html
import multiprocessing as mp
import os
import re
import subprocess
import sys
import threading
import time
from collections import Counter, deque
from pathlib import Path
from queue import Empty, Queue
from urllib.parse import parse_qs, urlparse

# Opsi FFmpeg harus dipasang sebelum backend FFmpeg OpenCV dipakai.
os.environ.setdefault(
    "OPENCV_FFMPEG_CAPTURE_OPTIONS",
    "reconnect;1|"
    "reconnect_streamed;1|"
    "reconnect_at_eof;1|"
    "reconnect_on_network_error;1|"
    "reconnect_delay_max;5|"
    "rw_timeout;15000000",
)

import cv2
import numpy as np
import requests

# ==========================================
# 0. KONFIGURASI
# ==========================================
JASNITA_USER = 'sby@jasnita.co.id'
JASNITA_PASS = 'surabaya2025!!'
JASNITA_URL = os.getenv("JASNITA_URL", "https://panel.jastrak.id/api")

OPEN_TIMEOUT_MS = 15000        # batas waktu MEMBUKA koneksi stream
READ_TIMEOUT_MS = 15000        # batas waktu MEMBACA setiap frame
TOKEN_REFRESH_SEC = 240        # token Jasnita berlaku 300 dtk -> sambung ulang di 240 dtk (sebelum kedaluwarsa)

# Retry pembukaan stream. Token yang sama dicoba beberapa kali dulu sebelum meminta token baru,
# agar API Jasnita tidak dihantam login berulang saat koneksi kamera sedang lambat.
STREAM_OPEN_ATTEMPTS = 3
STREAM_OPEN_DELAY_SEC = 1.0
STREAM_OPEN_BACKOFF_MAX = 6.0
STREAM_TOKEN_RETRIES = 3
STREAM_RETRY_DELAY_SEC = 3.0
STREAM_HTTP_PROBE_TIMEOUT = (5, 8)
STREAM_USER_AGENT = "Mozilla/5.0 CCTV-Bapenda-TrafficCounter/5"
# URL default jika Anda hanya menekan Enter saat diminta input URL stream
DEFAULT_STREAM_URL = 'https://panel.jastrak.id/dashboard/video-stream?id=a02e5078-f6fb-463b-98bc-02fc3ce8be28'
TIMEOUT = 30

FRAME_W, FRAME_H = 1024, 576

# Model & deteksi
MODEL_NAME = "yolov8l.pt"      # YOLO Large: lebih kuat untuk membedakan mobil vs motor, terutama objek kecil/jauh
IMGSZ = 960                     # resolusi inferensi lebih tinggi untuk membantu objek kecil pada CCTV
DET_CONF = 0.05                 # kandidat low-score tetap dipertahankan untuk ByteTrack; keputusan akhir diperketat
MAX_DET = 200                   # jangan membuang motor hanya karena jumlah objek dalam satu frame cukup banyak
TARGET_CLASSES = [2, 3, 5, 7]  # 2 car, 3 motorcycle, 5 bus, 7 truck

# Stabilitas IDENTIFIKASI KELAS (mobil / motor)
MIN_CLASS_CONF = 0.10           # observasi dengan confidence di bawah ini tidak ikut voting kelas
MIN_CLASS_CONFIRM_FRAMES = 2    # minimal observasi valid sebelum kelas dipakai untuk counting
CLASS_SCORE_MARGIN = 0.15       # kelas pemenang harus unggul minimal 15% dari kelas lain jika keduanya muncul

# Logika counting
MIN_TRAVEL_PX = 20              # jarak tempuh minimum dari titik kontak kuning sampai saat dihitung (px) ...
TRAVEL_RATIO = 0.30             # ... atau 30% lebar bbox, mana yang lebih besar
APPROACH_MIN_PX = 0.0           # kemajuan MENDEKATI area counting sejak kontak kuning (>=0 = tidak boleh menjauh)
FOOT_BAND_FRAC = 0.35           # 'kaki' = 35% bagian bawah bbox (lebih toleran dari 3 titik roda saja)
COUNT_CONFIRM_FRAMES = 2         # syarat hitung harus terpenuhi di N observasi BERURUTAN (lonjakan jitter 1 frame tidak cukup)
CROSS_RETREAT_PX = 10.0          # FPS rendah: 'kunci lintas' hijau/merah dilepas bila kendaraan MUNDUR > max(10 px, ...
CROSS_RETREAT_RATIO = 0.15       # ... 15% lebar bbox) dari titik saat menyentuh garis (= lonjakan bbox, bukan lintasan nyata)
PARK_RADIUS_PERCENTILE = 85      # radius parkir memakai persentil ini (tahan lonjakan jitter), bukan nilai maksimum
INIT_FWD_PX = 45.0               # inisialisasi lewat gerak: maju minimal sekian px sejak pertama terlihat ...
INIT_FWD_RATIO = 0.80            # ... atau 80% lebar bbox, mana yang lebih besar (di atas jitter bbox kendaraan diam)
DUP_WINDOW_SEC = 2.5             # anti-duplikat: dua hitungan sekelas dalam jendela waktu ini diperiksa kedekatannya
DUP_MIN_PX = 25.0                # anti-duplikat: dianggap kendaraan yang sama bila jarak <= max(25 px, ...
DUP_RATIO = 0.70                 # ... 70% lebar bbox)
RELINK_BASE_PX = 45.0            # relink: jarak tersambung = 45 px + kecepatan x selang waktu ...
RELINK_SPEED_PX_S = 120.0        # ... (px/detik), dibatasi RELINK_DIST
MISSED_FLUSH = True              # sapuan akhir: hitung track yang jelas melintas tapi lolos dari gerbang per-frame
FLUSH_MIN_PROGRESS_PX = 5.0      # sapuan akhir: minimal kemajuan mendekati area counting (px)
FLUSH_MIN_TRAVEL_PX = 40.0       # sapuan akhir: jarak tempuh bersih minimal dari kontak kuning (px) ...
FLUSH_TRAVEL_RATIO = 0.60        # ... atau 60% lebar bbox, mana yang lebih besar
DIAG_LOG = True                 # cetak alasan bila track menyentuh area counting tapi tidak terhitung
MIN_TRACK_FRAMES = 2            # motor yang singkat terlihat tetap bisa diinisialisasi
MIN_YELLOW_HITS = 1              # satu bukti kontak badan/anchor dengan area kuning sudah cukup
LOST_AFTER = 1.2                 # jangan terlalu cepat melepas track saat inference tidak setiap frame
RELINK_TIME = 4.5                # pertahankan kandidat lebih lama saat ID ByteTrack berganti
RELINK_DIST = 140                # toleransi perpindahan posisi saat ID berubah

# Deteksi PARKIR (objek diam tidak boleh dihitung) & syarat GERAK searah
PARK_WINDOW_SEC = 3.0             # objek dianggap parkir bila nyaris tidak berpindah selama durasi ini
PARK_MIN_SAMPLES = 3              # minimal jumlah observasi di dalam jendela tersebut (3 = tetap jalan di FPS ~1)
PARK_MIN_RADIUS_PX = 15.0         # jitter bounding box yang masih dianggap "diam" (px)
PARK_RADIUS_RATIO = 0.25          # ... atau 25% lebar bbox, mana yang lebih besar (kendaraan dekat kamera = jitter lebih besar)
PARK_RELEASE_PX = 45.0            # parkir dianggap mulai berjalan lagi jika bergeser lebih dari ini (px) ...
PARK_RELEASE_RATIO = 0.60         # ... atau 60% lebar bbox
PARKED_CAN_RESUME_COUNT = True    # True = kendaraan yang sempat berhenti lalu jalan lagi boleh dihitung; False = tidak pernah
MOVE_WINDOW_SEC = 2.5             # jendela waktu untuk menilai kendaraan sedang bergerak
MOVE_MIN_PX = 25.0                # perpindahan minimum di jendela tsb (px) agar dianggap bergerak ...
MOVE_RATIO = 0.30                 # ... atau 40% lebar bbox, mana yang lebih besar

# Counting berbasis GARIS, bukan area bagian dalam ROI.
LINE_TOUCH_TOLERANCE_PX = 5.0    # toleransi tipis untuk perbedaan bounding box/pixel CCTV
LINE_CROSS_SAMPLES = 20          # sampling lintasan antar-frame agar garis tipis tidak terlewati
WHEEL_INSET = 0.20                # posisi roda: kiri/tengah/kanan di bawah bounding box
MIN_ENTRY_VECTOR_PX = 40          # jarak minimum antar pusat area untuk menentukan arah masuk

# ROI
COLOR_YELLOW = (0, 255, 255)
COLOR_GREEN = (0, 255, 0)
COLOR_RED = (0, 0, 255)

# Tanda X merah: kendaraan yang diklik operator dikecualikan dari counting
EXCLUDE_IOU = 0.45                # ID baru mewarisi tanda X bila bbox-nya menumpuk >= 45% dgn posisi tanda (ID berganti)
EXCLUDE_KEEP_SEC = 10.0           # tanda X kendaraan BERGERAK dibuang setelah tak terlihat selama ini (detik)
EXCLUDE_KEEP_PARKED_SEC = 1800.0  # tanda X kendaraan DIAM/PARKIR diingat selama ini walau sempat tak terdeteksi
ROI_STEPS = [
    ("AREA INISIALISASI (KUNING)", COLOR_YELLOW),
    ("AREA COUNTING MOTOR (HIJAU)", COLOR_GREEN),
    ("AREA COUNTING MOBIL (MERAH)", COLOR_RED),
]

# Output (semua disimpan di folder yang sama dengan script)
BASE_DIR = Path(__file__).resolve().parent
CSV_DELIMITER = ","                                          # Excel versi Indonesia biasanya butuh ";"
EVENT_LOG_FILE = BASE_DIR / "log_kendaraan_terhitung.csv"    # format log utama untuk Excel sesuai field Bapenda
CAPTURE_INDEX_FILE = BASE_DIR / "_capture_index.csv"       # index internal capture -> ID log, tidak dipakai sebagai log utama
CAPTURE_EXCEL_FILE = BASE_DIR / "log_capture_kendaraan.xlsx" # Excel capture dengan gambar tertanam
CAPTURE_EXCEL_SHEET = "CAPTURE"
CAPTURE_EXCEL_FLUSH_SEC = 4.0                                # Excel ditulis ulang paling cepat tiap N detik (hemat disk)
CAPTURE_EXCEL_RETRY_SEC = 12.0                               # jeda coba ulang bila file Excel sedang dibuka/terkunci
CAPTURE_EXCEL_IMAGE_W = 320
CAPTURE_EXCEL_IMAGE_H = 180
SUMMARY_FILE = BASE_DIR / "ringkasan_hitungan.csv"           # ringkasan jumlah mobil & motor per sumber stream
NETWORK_LOG_FILE = BASE_DIR / "log_koneksi_stream.csv"       # riwayat sambung/putus stream, utk diagnosis pola putus
SUMMARY_INTERVAL_SEC = 60                                    # ringkasan berkala (hanya jika angka berubah)
CAPTURE_DIR = BASE_DIR / "capture"                           # capture/<id_cctv>/<kelas>/<tanggal>/HHMMSS_idN.jpg
# PENTING: sebelumnya hanya "motor" -> itu sebabnya mobil yang terhitung tidak pernah ter-capture.
CAPTURE_CLASSES = ("motor", "car")                           # kelas yang di-capture; kosongkan salah satu utk mematikannya
CAPTURE_FULL_FRAME = False                                   # True = simpan juga frame penuh + bounding box
CAPTURE_SCALE = 2.2                                          # pembesaran dasar crop
CAPTURE_MIN_LONG_SIDE = 640                                  # sisi terpanjang minimum setelah resize (px)
CAPTURE_UPSCALE_MAX = 3.5                                    # batas maksimum pembesaran
CAPTURE_JPEG_QUALITY = 97                                    # kualitas JPG capture (0-100)
CAPTURE_SHARPEN_AMOUNT = 0.65                                # sharpening ringan
CAPTURE_PAD_RATIO = 0.18                                     # ruang tambahan di sekitar kendaraan
REPORT_THUMB_W = 150                                         # lebar thumbnail HTML
REPORT_THUMB_H = 108                                         # tinggi thumbnail HTML
REPORT_DIR = BASE_DIR / "laporan"                            # laporan/laporan_<id_cctv>_<tanggal>.html

TRACKER_CFG = """tracker_type: bytetrack
track_high_thresh: 0.15
track_low_thresh: 0.05
new_track_thresh: 0.15
track_buffer: 90
match_thresh: 0.85
fuse_score: True
"""

LABEL = {"car": "Mobil", "motor": "Motor"}
LOG_JENIS = {"car": "MOBIL", "motor": "MOTOR"}
LOG_VENDOR = "BAPENDA"


# ==========================================
# 1. API & PEKERJA JARINGAN
# ==========================================
def login(session: requests.Session) -> str:
    res = session.post(
        f"{JASNITA_URL}/login",
        json={"email": JASNITA_USER, "password": JASNITA_PASS},
        timeout=TIMEOUT,
    )
    res.raise_for_status()
    token = res.json().get("token")
    if not token:
        raise RuntimeError("Login gagal: token kosong")
    return token


def get_stream_url(display_id: str) -> str:
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {login(session)}"
    res = session.post(f"{JASNITA_URL}/video-stream-url", json={"id": display_id}, timeout=TIMEOUT)
    res.raise_for_status()
    data = res.json()
    stream_token = data.get("token")
    if not stream_token:
        raise RuntimeError("Stream URL gagal: token kosong")
    print(f"[INFO-NETWORK] Token stream didapat. Masa aktif: {data.get('expires_in')} detik")
    return f"{JASNITA_URL}/video-stream?token={stream_token}"


class _StreamRefresh(Exception):
    """Bukan error: dipakai utk menutup & membuka ulang stream sebelum token 300 dtk kedaluwarsa."""


def _push_latest(q, frame):
    if q.full():
        try:
            q.get_nowait()
        except Exception:
            pass
    try:
        q.put_nowait(frame)
    except Exception:
        pass


def log_network_event(label, event, detail="", connected_since=None, disconnected_since=None):
    """Catat riwayat sambung/putus stream ke CSV, supaya pola putusnya (jam berapa, seberapa sering,
    berapa lama tiap kali putus) bisa dianalisis belakangan tanpa harus menonton terminal terus-menerus."""
    now = time.time()
    durasi_konek = f"{now - connected_since:.1f}" if connected_since else ""
    downtime = f"{now - disconnected_since:.1f}" if disconnected_since else ""
    append_csv(
        NETWORK_LOG_FILE,
        ["waktu", "sumber", "kejadian", "durasi_terhubung_detik", "downtime_sebelumnya_detik", "detail"],
        [fmt_time(now), label, event, durasi_konek, downtime, detail],
    )


def _set_capture_timeouts(cap):
    """Set timeout/buffer bila backend OpenCV mendukung property tersebut."""
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass
    for prop_name, value in (
        ("CAP_PROP_OPEN_TIMEOUT_MSEC", OPEN_TIMEOUT_MS),
        ("CAP_PROP_READ_TIMEOUT_MSEC", READ_TIMEOUT_MS),
    ):
        if hasattr(cv2, prop_name):
            try:
                cap.set(getattr(cv2, prop_name), value)
            except Exception:
                pass


def _open_capture_once(url):
    """Buka stream dengan timeout melalui constructor jika tersedia; fallback ke set()."""
    params = []
    if hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC"):
        params += [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, OPEN_TIMEOUT_MS]
    if hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
        params += [cv2.CAP_PROP_READ_TIMEOUT_MSEC, READ_TIMEOUT_MS]

    last_error = None
    # Coba FFmpeg dulu karena stream Jasnita/HTTP biasanya paling konsisten lewat FFmpeg.
    backends = [cv2.CAP_FFMPEG]
    if hasattr(cv2, "CAP_ANY") and cv2.CAP_ANY not in backends:
        backends.append(cv2.CAP_ANY)

    for api in backends:
        cap = None
        try:
            # Beberapa build OpenCV tidak menerima parameter constructor. Coba versi lengkap dulu.
            if params:
                try:
                    cap = cv2.VideoCapture(url, api, params)
                except (TypeError, cv2.error):
                    cap = cv2.VideoCapture(url, api)
            else:
                cap = cv2.VideoCapture(url, api)

            _set_capture_timeouts(cap)
            if cap.isOpened():
                return cap
            last_error = f"backend={api} tidak berhasil membuka URL"
        except Exception as exc:
            last_error = f"backend={api}: {exc}"
        finally:
            if cap is not None and not cap.isOpened():
                try:
                    cap.release()
                except Exception:
                    pass

    raise RuntimeError(last_error or "OpenCV tidak dapat membuka stream")


def _probe_http_stream(url):
    """Probe ringan untuk membedakan masalah token/API HTTP vs masalah decoder OpenCV.
    Hanya dipanggil setelah pembukaan OpenCV gagal, jadi tidak menambah beban pada koneksi normal.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return ""
    try:
        with requests.get(
            url,
            stream=True,
            timeout=STREAM_HTTP_PROBE_TIMEOUT,
            headers={"User-Agent": STREAM_USER_AGENT},
            allow_redirects=True,
        ) as res:
            ctype = (res.headers.get("Content-Type") or "").split(";", 1)[0]
            return f"HTTP {res.status_code}, content-type={ctype or '-'}, final_url={res.url[:120]}"
    except requests.RequestException as exc:
        return f"probe HTTP gagal: {exc}"


def open_stream_with_retries(url):
    """Buka stream beberapa kali memakai URL/token yang sama sebelum menyerah."""
    last_detail = ""
    for attempt in range(1, STREAM_OPEN_ATTEMPTS + 1):
        cap = None
        try:
            cap = _open_capture_once(url)
            if cap is not None and cap.isOpened():
                return cap, ""
        except Exception as exc:
            last_detail = str(exc)
        finally:
            if cap is not None and not cap.isOpened():
                try:
                    cap.release()
                except Exception:
                    pass

        if attempt < STREAM_OPEN_ATTEMPTS:
            delay = min(STREAM_OPEN_BACKOFF_MAX, STREAM_OPEN_DELAY_SEC * (2 ** (attempt - 1)))
            print(f"[WARN-NETWORK] Open stream gagal (attempt {attempt}/{STREAM_OPEN_ATTEMPTS}) -> retry {delay:.1f}s")
            time.sleep(delay)

    probe = _probe_http_stream(url)
    if probe:
        last_detail = f"{last_detail}; {probe}" if last_detail else probe
    return None, last_detail or "OpenCV gagal membuka stream"


def stream_worker(source, frame_queue):
    kind, value = source
    label = describe_source(source)["sumber"]
    failures = 0
    token_url = None
    token_obtained_at = 0.0
    disconnected_at = None
    connected_once = False

    while True:
        cap = None
        opened_at = 0.0
        try:
            # Untuk Jasnita, satu token dipakai ulang untuk beberapa percobaan open.
            # Token baru hanya diminta setelah retry token yang sama benar-benar gagal.
            if kind == "jasnita":
                token_expired = token_url is None or (time.time() - token_obtained_at) >= (TOKEN_REFRESH_SEC - 15)
                if token_expired:
                    token_url = get_stream_url(value)
                    token_obtained_at = time.time()
            else:
                token_url = value
                token_obtained_at = time.time()

            cap, detail = open_stream_with_retries(token_url)
            if cap is None:
                failures += 1
                # Open failure belum berarti stream sebelumnya putus. Jangan mengisi downtime di sini
                # karena pada startup memang belum pernah connected.
                print(f"[WARN-NETWORK] Gagal membuka stream: {detail} (siklus {failures})")

                # Bila token Jasnita sudah beberapa kali gagal, paksa refresh token sebelum backoff panjang.
                if kind == "jasnita" and failures >= STREAM_TOKEN_RETRIES:
                    print("[WARN-NETWORK] Token/endpoint gagal dibuka beberapa kali -> minta token baru.")
                    token_url = None
                    token_obtained_at = 0.0
                    failures = 0
                    wait = STREAM_RETRY_DELAY_SEC
                else:
                    wait = min(STREAM_OPEN_BACKOFF_MAX, STREAM_RETRY_DELAY_SEC * max(1, failures))

                log_network_event(label, "gagal_buka", detail=detail)
                time.sleep(wait)
                continue

            failures = 0
            opened_at = time.time()
            connected_once = True
            log_network_event(label, "terhubung", disconnected_since=disconnected_at)
            disconnected_at = None
            print("[INFO-NETWORK] Stream berhasil dibuka.")

            while True:
                # Refresh token hanya setelah stream baru berhasil dibuka; bila refresh gagal,
                # stream lama tidak langsung dibuang sebelum ada kesempatan retry.
                if kind == "jasnita" and time.time() - token_obtained_at >= TOKEN_REFRESH_SEC:
                    raise _StreamRefresh()

                ok, frame = cap.read()
                if not ok:
                    raise RuntimeError("Stream terputus / frame tidak terbaca")
                failures = 0
                _push_latest(frame_queue, frame)

        except _StreamRefresh:
            disconnected_at = time.time() if connected_once else None
            log_network_event(label, "refresh_terjadwal", connected_since=opened_at)
            print("[INFO-NETWORK] Refresh token terjadwal -> membuka koneksi baru ...")
            # Paksa token baru pada iterasi berikutnya. Tidak melakukan sleep panjang.
            token_url = None
            token_obtained_at = 0.0
        except Exception as e:
            failures += 1
            disconnected_at = time.time() if connected_once else None
            log_network_event(label, "terputus", detail=str(e), connected_since=opened_at if opened_at else None)
            wait = min(15.0, max(1.0, 2.0 * failures))
            print(f"[WARN-NETWORK] {e} (reconnect {failures}) - ulang dalam {wait:.1f}s")
            time.sleep(wait)
        finally:
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass


def inference_worker(frame_queue, result_queue, tracker_cfg_path):
    """
    PROSES TERPISAH: menjalankan YOLO + ByteTrack. Sengaja dipisah dari proses tampilan (run()) supaya
    jendela cv2.imshow tidak pernah menunggu YOLO -> tidak "Not Responding" walau deteksi berat/banyak objek.
    Hasil deteksi dikirim sebagai data polos (bukan objek Ultralytics) agar bisa lewat multiprocessing.Queue.
    """
    from ultralytics import YOLO
    print(f"[INFO] Memuat model {MODEL_NAME} ...")
    model = YOLO(MODEL_NAME)
    print("[INFO] Model siap. Deteksi berjalan di proses terpisah dari tampilan.")
    while True:
        try:
            raw = frame_queue.get(timeout=5.0)
        except Empty:
            continue
        # Cap waktu diambil SEBELUM inferensi: durasi YOLO bervariasi (banyak/sedikit objek), jadi waktu
        # terima hasil di GUI tidak cocok utk menghitung kecepatan/gerak -- terutama di FPS rendah.
        t_frame = time.time()
        raw = cv2.resize(raw, (FRAME_W, FRAME_H))
        results = model.track(raw, persist=True, classes=TARGET_CLASSES, tracker=tracker_cfg_path,
                              imgsz=IMGSZ, conf=DET_CONF, max_det=MAX_DET, verbose=False)
        boxes = results[0].boxes
        if boxes is not None and boxes.id is not None:
            payload = {
                "xyxy": boxes.xyxy.cpu().numpy(),
                "ids": boxes.id.int().cpu().numpy(),
                "cls": boxes.cls.int().cpu().numpy(),
                "conf": boxes.conf.cpu().numpy(),
            }
        else:
            payload = None
        _push_latest(result_queue, (raw, payload, t_frame))


UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def parse_stream_input(text):
    """Return ("jasnita", display_id) atau ("direct", url); None jika tidak valid."""
    text = (text or "").strip().strip('"').strip("'")
    if not text:
        return None
    parsed = urlparse(text)
    qid = (parse_qs(parsed.query).get("id") or [""])[0]
    if UUID_RE.fullmatch(qid):
        return ("jasnita", qid)
    if UUID_RE.fullmatch(text):
        return ("jasnita", text)
    if parsed.scheme in ("rtsp", "rtmp", "http", "https") and parsed.netloc:
        if "jastrak.id" in parsed.netloc:
            return None  # halaman panel Jasnita tanpa parameter id
        return ("direct", text)
    return None


def ask_stream_source():
    """URL dari argumen command line, atau ditanyakan saat program mulai."""
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    text = args[0] if args else None
    while True:
        if text is None:
            try:
                text = input(f"\nMasukkan URL stream CCTV\n(Enter = default: {DEFAULT_STREAM_URL})\n> ")
            except EOFError:
                print("Tidak ada input. Jalankan dari terminal atau beri URL sebagai argumen.")
                sys.exit(1)
            if not text.strip():
                text = DEFAULT_STREAM_URL
        source = parse_stream_input(text)
        if source:
            return source
        print("[ERROR] URL tidak valid. Contoh: https://panel.jastrak.id/dashboard/video-stream?id=<UUID>")
        text = None


def grab_frame(frame_queue):
    """Ambil satu frame dari stream (menunggu sampai ada)."""
    while True:
        try:
            frame = frame_queue.get(timeout=5.0)
        except Empty:
            print("[INFO] Menunggu frame dari stream ...")
            continue
        return cv2.resize(frame, (FRAME_W, FRAME_H))


# ==========================================
# 2. GEOMETRI & STATE TRACK
# ==========================================
def to_poly(pts):
    return np.array(pts, np.int32).reshape((-1, 1, 2))


def inside(poly, pt):
    return cv2.pointPolygonTest(poly, (float(pt[0]), float(pt[1])), False) >= 0


def segment_hits(poly, p0, p1, samples=12):
    """True jika ruas p0->p1 melewati poligon (menangani kendaraan yang 'melompati' zona tipis)."""
    for t in np.linspace(0.0, 1.0, samples):
        if inside(poly, (p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t)):
            return True
    return False


def touches(poly, prev_pt, pt):
    """Kontak/gerak melalui POLYGON (dipakai untuk kompatibilitas fungsi lama)."""
    return inside(poly, pt) or (prev_pt is not None and segment_hits(poly, prev_pt, pt))


def bbox_anchor_points(box):
    """Titik jangkar pada badan kendaraan, terutama bagian bawah."""
    x1, y1, x2, y2 = [float(v) for v in box]
    w = max(1.0, x2 - x1)
    h = max(1.0, y2 - y1)
    xm = (x1 + x2) / 2.0
    return [
        (xm, y2),
        (x1 + 0.25 * w, y2),
        (x2 - 0.25 * w, y2),
        (x1, y2),
        (x2, y2),
        (xm, y1 + 0.55 * h),
        (xm, y1 + 0.35 * h),
        (x1 + 0.20 * w, y1 + 0.60 * h),
        (x2 - 0.20 * w, y1 + 0.60 * h),
    ]


def bbox_edges(box):
    """Empat sisi bounding box sebagai ruas garis."""
    x1, y1, x2, y2 = [float(v) for v in box]
    return [
        ((x1, y1), (x2, y1)),
        ((x2, y1), (x2, y2)),
        ((x2, y2), (x1, y2)),
        ((x1, y2), (x1, y1)),
    ]


def point_segment_distance(p, a, b):
    """Jarak titik ke ruas garis."""
    p = np.asarray(p, dtype=float)
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    ab = b - a
    den = float(np.dot(ab, ab))
    if den <= 1e-9:
        return float(np.linalg.norm(p - a))
    t = float(np.dot(p - a, ab) / den)
    t = max(0.0, min(1.0, t))
    q = a + t * ab
    return float(np.linalg.norm(p - q))


def orientation(a, b, c):
    return ((float(b[0]) - float(a[0])) * (float(c[1]) - float(a[1]))
            - (float(b[1]) - float(a[1])) * (float(c[0]) - float(a[0])))


def on_segment(a, b, p, eps=1e-6):
    return (min(a[0], b[0]) - eps <= p[0] <= max(a[0], b[0]) + eps
            and min(a[1], b[1]) - eps <= p[1] <= max(a[1], b[1]) + eps)


def segments_intersect(a, b, c, d, eps=1e-6):
    """Intersection ruas garis 2D, termasuk kasus garis saling menyentuh."""
    o1, o2 = orientation(a, b, c), orientation(a, b, d)
    o3, o4 = orientation(c, d, a), orientation(c, d, b)
    if ((o1 > eps and o2 < -eps) or (o1 < -eps and o2 > eps)) and ((o3 > eps and o4 < -eps) or (o3 < -eps and o4 > eps)):
        return True
    if abs(o1) <= eps and on_segment(a, b, c):
        return True
    if abs(o2) <= eps and on_segment(a, b, d):
        return True
    if abs(o3) <= eps and on_segment(c, d, a):
        return True
    if abs(o4) <= eps and on_segment(c, d, b):
        return True
    return False


def poly_edges(poly):
    pts = np.asarray(poly).reshape(-1, 2).astype(float)
    if len(pts) < 2:
        return []
    return [(tuple(pts[i]), tuple(pts[(i + 1) % len(pts)])) for i in range(len(pts))]


def point_near_poly_boundary(poly, pt, tolerance=LINE_TOUCH_TOLERANCE_PX):
    """True hanya jika titik dekat GARIS batas polygon; tidak menganggap seluruh area sebagai hit."""
    return any(point_segment_distance(pt, a, b) <= tolerance for a, b in poly_edges(poly))


def segment_hits_poly_boundary(poly, p0, p1, samples=LINE_CROSS_SAMPLES):
    """True jika gerakan titik menyentuh/menyeberangi GARIS polygon."""
    edges = poly_edges(poly)
    if not edges:
        return False
    if any(point_near_poly_boundary(poly, p, LINE_TOUCH_TOLERANCE_PX) for p in (p0, p1)):
        return True
    if any(segments_intersect(p0, p1, a, b) for a, b in edges):
        return True
    # Fallback untuk video dengan gerak cepat / bounding box yang bergeser besar.
    for t in np.linspace(0.0, 1.0, max(2, int(samples))):
        p = (p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t)
        if point_near_poly_boundary(poly, p, LINE_TOUCH_TOLERANCE_PX):
            return True
    return False


def bbox_overlaps_polygon(poly, box, prev_box=None):
    """Deteksi bahwa BADAN bounding box menyentuh/beririsan area polygon (untuk INISIALISASI)."""
    edges = poly_edges(poly)
    x1, y1, x2, y2 = [float(v) for v in box]
    corners = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
    if any(inside(poly, p) for p in corners):
        return True
    poly_pts = np.asarray(poly).reshape(-1, 2)
    if any(x1 <= float(px) <= x2 and y1 <= float(py) <= y2 for px, py in poly_pts):
        return True
    box_edges = bbox_edges(box)
    if any(segments_intersect(a, b, c, d) for a, b in box_edges for c, d in edges):
        return True
    # Jika box bergerak menyeberangi ROI antara dua hasil deteksi, tetap anggap kontak terjadi.
    if prev_box is not None:
        prev_edges = bbox_edges(prev_box)
        for (a0, a1), (b0, b1) in zip(prev_edges, box_edges):
            if any(segment_hits_poly_boundary(poly, p0, p1) for p0, p1 in ((a0, a1), (b0, b1))):
                return True
        prev_c = bbox_anchor_points(prev_box)
        cur_c = bbox_anchor_points(box)
        if any(segments_intersect(p0, p1, e0, e1) for p0, p1 in zip(prev_c, cur_c) for e0, e1 in edges):
            return True
    return False


def vehicle_touches_count_line(poly, box, prev_box=None, wheels=None, prev_wheels=None):
    """Counting AKTIF hanya ketika RODA atau BADAN kendaraan menyentuh garis ROI.

    Berbeda dari `inside()`: kendaraan yang sudah berada di dalam polygon tetapi tidak menyentuh
    garis tidak dihitung. Gerakan antar-frame yang menyeberangi garis juga terdeteksi.
    """
    # 1) Roda/titik bawah: paling kuat untuk mobil.
    wheels = wheels or wheel_points(float(box[0]), float(box[2]), float(box[3]))
    if any(point_near_poly_boundary(poly, p) for p in wheels):
        return True
    if prev_wheels is not None:
        for p0, p1 in zip(prev_wheels, wheels):
            if segment_hits_poly_boundary(poly, p0, p1):
                return True

    # 2) Seluruh badan/bounding box: juga berlaku untuk motor, mobil, bus, truk.
    edges = poly_edges(poly)
    if any(segments_intersect(a, b, c, d) for a, b in bbox_edges(box) for c, d in edges):
        return True

    # 3) Bila bbox melewati garis di antara dua frame, tangkap lintasannya.
    if prev_box is not None:
        prev_edges = bbox_edges(prev_box)
        cur_edges = bbox_edges(box)
        for (p0a, p0b), (p1a, p1b) in zip(prev_edges, cur_edges):
            if any(segment_hits_poly_boundary(poly, q0, q1) for q0, q1 in ((p0a, p1a), (p0b, p1b))):
                return True
    return False


def touches_bbox(poly, box, prev_box=None):
    """Kontak badan kendaraan dengan area polygon, untuk inisialisasi yellow.
    Return (hit, anchor).
    """
    cur_pts = bbox_anchor_points(box)
    hit = bbox_overlaps_polygon(poly, box, prev_box)
    if not hit:
        return False, None
    # Pilih anchor yang benar-benar berada di dalam area; fallback ke bottom-center.
    for p in cur_pts:
        if inside(poly, p):
            return True, p
    return True, cur_pts[0]


def wheel_points(x1, x2, y2):
    """Tiga titik perkiraan roda kiri/tengah/kanan pada garis bawah bounding box."""
    w = x2 - x1
    return [(x1 + WHEEL_INSET * w, y2), ((x1 + x2) / 2.0, y2), (x2 - WHEEL_INSET * w, y2)]


def touches_any(poly, prev_pts, pts):
    # Kompatibilitas: fungsi lama sekarang memakai GARIS batas polygon.
    return any(segment_hits_poly_boundary(poly, prev_pts[i] if prev_pts else p, p)
               for i, p in enumerate(pts))


def compute_entry_dir(from_pts, to_pts, fallback=None):
    """Arah masuk = vektor satuan dari pusat area 'from' ke pusat area 'to'.
    Jika kedua pusat terlalu berdekatan (area saling menimpa), pakai fallback (default: ke bawah layar)."""
    v = np.mean(np.array(to_pts, float), axis=0) - np.mean(np.array(from_pts, float), axis=0)
    n = float(np.linalg.norm(v))
    if n >= MIN_ENTRY_VECTOR_PX:
        return v / n
    return fallback if fallback is not None else np.array([0.0, 1.0])


class TrackState:
    def __init__(self, now):
        self.frames = 0
        self.last_seen = now
        self.last_pt = None
        self.last_wheels = None
        self.last_box = None
        self.last_group = None
        self.yellow_pt = None      # titik pertama/bukti terbaik menyentuh area kuning
        self.yellow_hits = 0
        self.initialized = False    # TIDAK PERNAH True sebelum objek menyentuh area KUNING
        self.counted = False
        self.votes = Counter()       # jumlah observasi kelas, untuk diagnosis
        self.class_scores = Counter() # voting berbobot confidence YOLO
        self.class_obs = Counter()    # jumlah observasi yang lolos MIN_CLASS_CONF
        self.confirmed_group = None   # kelas stabil yang dipakai untuk counting
        self.hist = deque(maxlen=64)  # riwayat (waktu, x, y) titik kaki, untuk deteksi parkir & arah gerak
        self.parked = False           # True = objek diam/parkir -> diabaikan
        self.was_parked = False       # pernah ditandai parkir
        self.park_anchor = None
        self.outside_seen = {"motor": False, "car": False}  # sudah pernah terlihat DI LUAR area counting kelasnya
        self.yellow_foot_t = None     # waktu pertama TITIK KAKI menyentuh area kuning (inisialisasi sah)
        self.yellow_foot_pt = None    # posisi kaki saat itu (acuan jarak/arah tempuh)
        self.target_first_t = {"motor": None, "car": None}  # waktu pertama kaki menyentuh hijau / merah
        self.reverse = {"motor": False, "car": False}       # True = menyentuh hijau/merah SEBELUM kuning (arah balik)
        self.max_travel = 0.0         # jarak terjauh dari titik kontak kuning (px)
        self.max_progress = {"motor": -1e9, "car": -1e9}    # kemajuan terbaik mendekati area counting (px)
        self.snap = {}                # kelas -> (frame, bbox, waktu) saat PERTAMA menyentuh area counting (setelah kuning)
        self.last_bw = 1.0
        self.origin_pt = None         # posisi kaki saat pertama terlihat
        self.origin_t = None
        self.max_fwd = {"motor": -1e9, "car": -1e9}   # kemajuan terjauh searah kuning -> hijau/merah sejak titik acuan (px)
        self.init_by_motion = False   # True = diinisialisasi lewat badan di kuning + gerak maju
        self.counted_group = None
        self.counted_t = None
        self.ready_frames = 0         # jumlah observasi berurutan yang memenuhi syarat hitung
        # Kunci lintas per kelas: (titik kaki, frame, bbox) saat kendaraan PERTAMA menyentuh/menyeberangi garis
        # hijau/merah. Di FPS rendah kendaraan sering sudah melewati garis pada observasi berikutnya, jadi
        # konfirmasi tidak lagi mensyaratkan bbox MASIH menyentuh garis -- cukup tidak mundur dari titik ini.
        self.cross = {"motor": None, "car": None}
        self.excluded = False         # True = diberi TANDA X MERAH oleh operator -> tidak pernah dihitung
        self.mark = None              # dict tanda X milik track ini (lihat find_exclusion_mark)


def ground_contact(poly, wheels, prev_pt, pt, box=None):
    """Titik kaki saat MASUK area (perkiraan), atau None bila kaki/roda tidak menyentuh area.

    Lintasan antar-frame diperiksa lebih dulu: di FPS rendah kendaraan bisa melompat jauh ke dalam/melewati area
    dalam satu langkah, dan titik masuk pada lintasan jauh lebih akurat daripada posisi kaki sekarang (yang
    membuat jarak tempuh sejak kuning terlihat ~0 sehingga kendaraan yang sah gagal dihitung).
    """
    if prev_pt is not None:
        for t in np.linspace(0.0, 1.0, max(2, LINE_CROSS_SAMPLES)):
            p = (prev_pt[0] + (pt[0] - prev_pt[0]) * t, prev_pt[1] + (pt[1] - prev_pt[1]) * t)
            if inside(poly, p):
                return p
    if any(inside(poly, w) or point_near_poly_boundary(poly, w) for w in wheels):
        return pt
    if box is not None:
        x1, y1, x2, y2 = [float(v) for v in box]
        band = (x1, y2 - FOOT_BAND_FRAC * max(1.0, y2 - y1), x2, y2)
        if bbox_overlaps_polygon(poly, band):
            return pt
    return None


def ground_touch(poly, wheels, prev_pt, pt, box=None):
    """Kaki/roda menyentuh area: titik roda, lintasan antar-frame, atau pita bawah bbox (FOOT_BAND_FRAC)."""
    return ground_contact(poly, wheels, prev_pt, pt, box) is not None


def update_zone_order(st, wheels, prev_pt, pt, now, yellow_roi, green_roi, red_roi, box=None):
    """Catat URUTAN sentuh zona oleh kaki.

    Kuning dulu lalu hijau/merah  -> arah benar (boleh dihitung).
    Hijau/merah dulu lalu kuning  -> arah balik: st.reverse[kelas] = True (permanen, tidak dihitung).
    Sentuh bersamaan pada frame yang sama dianggap arah benar; kemajuan arah diperiksa di approach_progress().
    """
    if st.yellow_foot_t is None:
        contact = ground_contact(yellow_roi, wheels, prev_pt, pt, box)
        if contact is not None:
            st.yellow_foot_t = now
            st.yellow_foot_pt = contact
    for g_name, g_roi in (("motor", green_roi), ("car", red_roi)):
        if st.target_first_t[g_name] is None and ground_touch(g_roi, wheels, prev_pt, pt, box):
            st.target_first_t[g_name] = now
            if st.yellow_foot_t is None:          # menyentuh hijau/merah sebelum pernah menyentuh kuning
                st.reverse[g_name] = True


def approach_progress(st, pt, target_roi):
    """Seberapa jauh kendaraan MENDEKAT ke area counting dibanding saat pertama menyentuh kuning (px).
    Tidak bergantung pada garis lurus pusat-ke-pusat: jalur melengkung/diagonal tetap sah.
    Positif = mendekat, negatif = menjauh (arah balik)."""
    if st.yellow_foot_pt is None:
        return None
    d0 = -cv2.pointPolygonTest(target_roi, (float(st.yellow_foot_pt[0]), float(st.yellow_foot_pt[1])), True)
    d1 = -cv2.pointPolygonTest(target_roi, (float(pt[0]), float(pt[1])), True)
    return d0 - d1


def update_motion_state(st, pt, box, now):
    """Catat posisi, lalu tandai/lepas status PARKIR."""
    st.hist.append((now, float(pt[0]), float(pt[1])))
    bw = max(1.0, float(box[2]) - float(box[0]))
    if not st.parked:
        win = [h for h in st.hist if now - h[0] <= PARK_WINDOW_SEC]
        if len(win) >= PARK_MIN_SAMPLES and now - win[0][0] >= PARK_WINDOW_SEC * 0.8:
            xs = np.array([h[1] for h in win])
            ys = np.array([h[2] for h in win])
            cx, cy = float(xs.mean()), float(ys.mean())
            radius = float(np.percentile(np.hypot(xs - cx, ys - cy), PARK_RADIUS_PERCENTILE))
            if radius <= max(PARK_MIN_RADIUS_PX, PARK_RADIUS_RATIO * bw):
                st.parked = True
                st.was_parked = True
                st.park_anchor = (cx, cy)
    elif st.park_anchor is not None:
        d = float(np.hypot(pt[0] - st.park_anchor[0], pt[1] - st.park_anchor[1]))
        if d > max(PARK_RELEASE_PX, PARK_RELEASE_RATIO * bw):
            st.parked = False                      # mulai berjalan lagi
            st.hist.clear()
            st.hist.append((now, float(pt[0]), float(pt[1])))
            if PARKED_CAN_RESUME_COUNT:
                st.was_parked = False


def moving_enough(st, now, box):
    """True jika kendaraan BERGERAK nyata (bukan jitter bbox kendaraan diam)."""
    bw = max(1.0, float(box[2]) - float(box[0]))
    recent = [h for h in st.hist if now - h[0] <= MOVE_WINDOW_SEC]
    if len(recent) < 2:
        recent = list(st.hist)[-2:]
    if len(recent) < 2:
        return False
    dist = float(np.hypot(recent[-1][1] - recent[0][1], recent[-1][2] - recent[0][2]))
    return dist >= max(MOVE_MIN_PX, MOVE_RATIO * bw)


def counting_group(st):
    """Kelas untuk counting: kelas yang sudah dikonfirmasi; bila belum (FPS rendah = sedikit observasi), pakai skor
    berbobot confidence setelah >= MIN_TRACK_FRAMES frame, lalu suara terbanyak sebagai cadangan terakhir."""
    if st.confirmed_group is not None:
        return st.confirmed_group
    if st.frames >= MIN_TRACK_FRAMES:
        if st.class_scores:
            return st.class_scores.most_common(1)[0][0]
        if st.votes:
            return st.votes.most_common(1)[0][0]
    return None


def vehicle_reaches_target(poly, box, prev_box, wheels, prev_wheels):
    """Kendaraan menyentuh/menyeberangi garis area counting, atau sudah berada di dalamnya."""
    if vehicle_touches_count_line(poly, box, prev_box=prev_box, wheels=wheels, prev_wheels=prev_wheels):
        return True
    return any(inside(poly, w) for w in wheels)


def update_cross_latch(st, pt, box, prev_box, wheels, raw, green_roi, red_roi, entry_dirs):
    """Kunci lintas garis hijau (motor) / merah (mobil), dipanggil SEBELUM should_count dan sebelum st.last_* diperbarui.

    Kunci dipasang saat kendaraan menyentuh/menyeberangi garis atau sudah di dalam area. Kunci dilepas bila
    kendaraan, tanpa menyentuh area lagi, MUNDUR (berlawanan arah kuning -> hijau/merah) melewati toleransi:
    itu tanda bbox sempat melonjak ke garis, bukan kendaraan yang benar-benar melintas.
    """
    bw = max(1.0, float(box[2]) - float(box[0]))
    tol = max(CROSS_RETREAT_PX, CROSS_RETREAT_RATIO * bw)
    for g_name, g_roi in (("motor", green_roi), ("car", red_roi)):
        if vehicle_reaches_target(g_roi, box, prev_box, wheels, st.last_wheels):
            if st.cross[g_name] is None:
                st.cross[g_name] = (pt, raw, tuple(float(v) for v in box))
            continue
        latch = st.cross[g_name]
        if latch is None:
            continue
        d = entry_dirs[g_name]
        lp = latch[0]
        if (pt[0] - lp[0]) * float(d[0]) + (pt[1] - lp[1]) * float(d[1]) < -tol:
            st.cross[g_name] = None


def should_count(st, pt, box, prev_box, wheels, now, green_roi, red_roi, entry_dirs):
    """Kelas kendaraan bila SAH dihitung sekarang, selain itu None. Dipakai run() dan pengujian.
    Syarat 'menyentuh garis' dibaca dari kunci lintas (update_cross_latch harus dipanggil lebih dulu)."""
    cur_group = counting_group(st)
    if (st.excluded or not st.initialized or st.counted or cur_group is None or st.parked or st.was_parked
            or st.reverse[cur_group] or not st.outside_seen[cur_group] or st.yellow_foot_pt is None):
        return None
    target_roi = green_roi if cur_group == "motor" else red_roi
    if st.cross[cur_group] is None:
        return None
    bw = max(1.0, float(box[2]) - float(box[0]))
    thr = max(MIN_TRAVEL_PX, TRAVEL_RATIO * bw)
    if not forward_ok(st, pt, target_roi, entry_dirs[cur_group], thr):
        return None                                   # tidak maju searah kuning -> hijau/merah
    if not moving_enough(st, now, box):
        return None
    return cur_group


def forward_ok(st, pt, target_roi, direction, thr):
    """Maju searah kuning -> counting: proyeksi perpindahan (sejak kontak kuning) pada vektor masuk >= thr,
    ATAU sudah mendekat ke area counting sejauh >= thr (jalur diagonal/melengkung). Mundur/menjauh = False."""
    dx, dy = pt[0] - st.yellow_foot_pt[0], pt[1] - st.yellow_foot_pt[1]
    if dx * float(direction[0]) + dy * float(direction[1]) >= thr:
        return True
    prog = approach_progress(st, pt, target_roi)
    return prog is not None and prog >= thr


def note_target_touch(st, prev_first, raw, box, now):
    """Simpan foto+bbox saat kaki PERTAMA menyentuh hijau/merah (dipakai sapuan akhir & log)."""
    for g_name in ("motor", "car"):
        if prev_first[g_name] is None and st.target_first_t[g_name] is not None:
            st.snap[g_name] = (raw, tuple(float(v) for v in box), now)


def update_trajectory_stats(st, pt, box, green_roi, red_roi, entry_dirs, now=None):
    """Catat bukti perjalanan: titik awal, jarak terjauh, kemajuan searah kuning -> counting, dan mendekati area."""
    st.last_bw = max(1.0, float(box[2]) - float(box[0]))
    if st.origin_pt is None:
        st.origin_pt = (float(pt[0]), float(pt[1]))
        st.origin_t = now
    base = st.yellow_foot_pt if st.yellow_foot_pt is not None else st.origin_pt
    dx, dy = pt[0] - base[0], pt[1] - base[1]
    for g_name in ("motor", "car"):
        proj = dx * float(entry_dirs[g_name][0]) + dy * float(entry_dirs[g_name][1])
        if proj > st.max_fwd[g_name]:
            st.max_fwd[g_name] = proj
    if st.yellow_foot_pt is None:
        return
    st.max_travel = max(st.max_travel, float(np.hypot(pt[0] - st.yellow_foot_pt[0], pt[1] - st.yellow_foot_pt[1])))
    for g_name, g_roi in (("motor", green_roi), ("car", red_roi)):
        p = approach_progress(st, pt, g_roi)
        if p is not None and p > st.max_progress[g_name]:
            st.max_progress[g_name] = p


def maybe_init_by_motion(st, g_hint, box):
    """Inisialisasi lewat BADAN di kuning + gerak maju (untuk kendaraan yang baru terlihat setelah keluar dari
    bayangan/halangan, sehingga kakinya tidak pernah tercatat di dalam kuning).

    Syarat: badan (bbox) pernah menyentuh kuning, tidak parkir, dan sudah maju searah kuning -> counting minimal
    max(INIT_FWD_PX, INIT_FWD_RATIO x lebar). Kendaraan yang bergerak MUNDUR (arah balik) atau hanya jitter tidak lolos.
    Bila lolos, tanda 'arah balik' akibat urutan sentuh kaki dicabut karena gerak nyata membuktikan arahnya.
    """
    if (st.initialized or st.yellow_foot_t is not None or st.yellow_pt is None
            or st.origin_pt is None or st.parked):
        return False
    g = g_hint if g_hint in ("motor", "car") else "motor"
    bw = max(1.0, float(box[2]) - float(box[0]))
    if st.max_fwd[g] < max(INIT_FWD_PX, INIT_FWD_RATIO * bw):
        return False
    st.yellow_foot_t = st.origin_t if st.origin_t is not None else time.time()
    st.yellow_foot_pt = st.origin_pt
    st.init_by_motion = True
    st.outside_seen[g] = True
    st.reverse[g] = False
    return True


def _pos_at(st, t):
    """Perkiraan posisi kaki track pada waktu t (sampel terdekat, atau ekstrapolasi singkat dari kecepatan)."""
    h = st.hist
    if not h:
        return None
    best = min(h, key=lambda smp: abs(smp[0] - t))
    if abs(best[0] - t) <= 0.35:
        return (best[1], best[2])
    last = h[-1]
    if t > last[0] and len(h) >= 2 and (t - last[0]) <= 1.5:
        prev = h[-2]
        dt = last[0] - prev[0]
        if dt > 1e-3:
            vx, vy = (last[1] - prev[1]) / dt, (last[2] - prev[2]) / dt
            return (last[1] + vx * (t - last[0]), last[2] + vy * (t - last[0]))
    return None


def is_duplicate_count(st, pt, box, g, t_c, tracks, lost):
    """True bila hitungan ini kemungkinan kendaraan yang SAMA dengan yang baru terhitung (ID ganda / ID berganti)."""
    bw = max(1.0, float(box[2]) - float(box[0]))
    limit = max(DUP_MIN_PX, DUP_RATIO * bw)
    for other in list(tracks.values()) + list(lost.values()):
        if (other is st or not other.counted or other.counted_group != g or other.counted_t is None
                or abs(t_c - other.counted_t) > DUP_WINDOW_SEC):
            continue
        pos = _pos_at(other, t_c)
        if pos is not None and float(np.hypot(pt[0] - pos[0], pt[1] - pos[1])) <= limit:
            return True
    return False


def missed_crossing_group(st, tid, counted_ids):
    """Sapuan akhir: kelas bila track ini JELAS melintas (kuning -> area counting) tetapi belum terhitung."""
    if (not MISSED_FLUSH or st.excluded or st.counted or tid in counted_ids or not st.initialized or st.parked):
        return None
    g = counting_group(st) or st.last_group
    if g not in ("motor", "car"):
        return None
    if st.reverse[g] or st.target_first_t[g] is None or g not in st.snap or not st.outside_seen[g]:
        return None
    if st.was_parked and not PARKED_CAN_RESUME_COUNT:
        return None
    thr = max(FLUSH_MIN_TRAVEL_PX, FLUSH_TRAVEL_RATIO * st.last_bw)
    approached = st.max_progress[g] >= FLUSH_MIN_PROGRESS_PX and st.max_travel >= thr
    advanced = st.max_fwd[g] >= thr
    if not (approached or advanced):
        return None
    return g


def why_not(st, pt, box, prev_box, wheels, now, green_roi, red_roi, entry_dirs):
    """Alasan singkat (untuk label debug) kenapa kendaraan ini belum/tidak terhitung."""
    if st.excluded:
        return "DIKECUALIKAN(X)"
    if st.counted:
        return "TERHITUNG"
    if not st.initialized:
        if st.yellow_pt is None:
            return "belum-sentuh-kuning"
        if st.parked:
            return "PARKIR(belum-init)"
        return "badan-di-kuning,tunggu-gerak-maju"
    g = counting_group(st)
    if g is None:
        return "kelas-belum-pasti"
    if st.parked:
        return "PARKIR"
    if st.was_parked:
        return "pernah-parkir"
    if st.reverse[g]:
        return "ARAH-BALIK"
    if not st.outside_seen[g]:
        return "belum-di-luar-area"
    target_roi = green_roi if g == "motor" else red_roi
    if st.cross[g] is None:
        return "menuju-area"
    bw = max(1.0, float(box[2]) - float(box[0]))
    if not forward_ok(st, pt, target_roi, entry_dirs[g], max(MIN_TRAVEL_PX, TRAVEL_RATIO * bw)):
        return "belum-maju/menjauh"
    if not moving_enough(st, now, box):
        return "diam"
    return "siap-hitung"


def diag_miss(tid, st):
    """Cetak alasan track yang menyentuh area counting tetapi tidak terhitung."""
    if st.excluded or st.counted or not st.initialized:
        return
    g = st.confirmed_group or st.last_group or "motor"
    if st.target_first_t.get(g) is None:
        return
    reasons = []
    if st.reverse[g]:
        reasons.append("arah-balik (menyentuh hijau/merah sebelum kuning)")
    if st.was_parked:
        reasons.append("sempat-diam/parkir")
    if not st.outside_seen[g]:
        reasons.append("tak-pernah-terlihat-di-luar-area-counting")
    if counting_group(st) is None:
        reasons.append("kelas-belum-pasti")
    if not reasons:
        reasons.append("gerak/jarak-tempuh/arah-mendekat tidak lolos")
    print(f"[DIAG] #{tid} {g} tidak terhitung: " + ", ".join(reasons))


def find_relink(pool, pt, group, now):
    """Cari track lama yang paling mungkin menjadi ID baru (ByteTrack sering mengganti ID di FPS rendah).

    pool = track yang hilang (lost) + track yang tidak muncul di frame ini. Jarak dihitung ke posisi terakhir
    ATAU posisi prediksi (posisi terakhir + kecepatan). Track yang sudah terhitung / parkir tidak disambung
    agar tidak 'menularkan' statusnya ke kendaraan lain yang kebetulan berdekatan.
    """
    best_id, best_score = None, float(RELINK_DIST)
    for old_id, st in pool.items():
        if st.last_pt is None or now - st.last_seen > RELINK_TIME or st.counted or st.parked:
            continue
        d = float(np.hypot(pt[0] - st.last_pt[0], pt[1] - st.last_pt[1]))
        if len(st.hist) >= 2:
            (t0, x0, y0), (t1, x1, y1) = st.hist[-2], st.hist[-1]
            if t1 - t0 > 1e-3:
                dt = min(max(0.0, now - st.last_seen), 1.5)
                px = x1 + (x1 - x0) / (t1 - t0) * dt
                py = y1 + (y1 - y0) / (t1 - t0) * dt
                d = min(d, float(np.hypot(pt[0] - px, pt[1] - py)))
        allow = min(float(RELINK_DIST), RELINK_BASE_PX + RELINK_SPEED_PX_S * max(0.0, now - st.last_seen))
        if d > allow:
            continue
        class_penalty = 0.0 if st.last_group == group else min(25.0, RELINK_DIST * 0.20)
        score = d + class_penalty
        if score < best_score:
            best_id, best_score = old_id, score
    return best_id


def box_iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 1e-9 else 0.0


def find_exclusion_mark(marks, tid, box, now, allow_iou):
    """Tanda X milik deteksi ini: ID tracker yang sama, ATAU (hanya untuk ID yang benar-benar baru = ID berganti)
    bbox menumpuk posisi tanda X yang pemiliknya tidak terlihat di frame ini. ID lama yang sudah dilacak tidak
    pernah mengambil tanda X lewat tumpukan, supaya kendaraan lain yang lewat di depan kendaraan bertanda X tidak
    ikut dikecualikan."""
    for m in marks:
        if m["tid"] == tid:
            return m
    if not allow_iou:
        return None
    best, best_iou = None, EXCLUDE_IOU
    for m in marks:
        if m["t"] >= now:
            continue
        iou = box_iou(box, m["box"])
        if iou >= best_iou:
            best, best_iou = m, iou
    return best


def drop_exclusion_mark(m, marks, tracks, lost):
    if m in marks:
        marks.remove(m)
    for s in list(tracks.values()) + list(lost.values()):
        if s.mark is m:
            s.excluded, s.mark = False, None


def toggle_exclusion(click, frame_dets, marks, tracks, lost, now):
    """Klik kiri: beri/hapus tanda X pada kendaraan terkecil yang memuat titik klik."""
    cx, cy = click
    hits = [(tid, box) for tid, box in frame_dets if box[0] <= cx <= box[2] and box[1] <= cy <= box[3]]
    if hits:
        tid, box = min(hits, key=lambda h: (h[1][2] - h[1][0]) * (h[1][3] - h[1][1]))
        st = tracks.get(tid)
        m = next((m for m in marks if m["tid"] == tid), None)
        if m is not None:
            drop_exclusion_mark(m, marks, tracks, lost)
            print(f"[INFO] Tanda X dihapus dari #{tid} -> kendaraan ini kembali boleh dihitung")
            return
        m = {"tid": tid, "box": box, "t": now,
             "parked": st is None or st.parked or st.was_parked}
        marks.append(m)
        if st is not None:
            st.excluded, st.mark = True, m
            if st.counted:
                print(f"[WARN] #{tid} diberi tanda X tetapi SUDAH terhitung sebelumnya (hitungan tidak dikurangi)")
        print(f"[INFO] #{tid} diberi TANDA X -> dikecualikan dari counting")
        return
    # Tidak mengenai deteksi: hapus tanda X yang posisinya diklik (kendaraan sedang tak terdeteksi).
    for m in list(marks):
        b = m["box"]
        if b[0] <= cx <= b[2] and b[1] <= cy <= b[3]:
            drop_exclusion_mark(m, marks, tracks, lost)
            print(f"[INFO] Tanda X (#{m['tid']}, tak terdeteksi) dihapus")
            return


def draw_excluded(vis, box, text):
    x1, y1, x2, y2 = [int(v) for v in box]
    cv2.rectangle(vis, (x1, y1), (x2, y2), COLOR_RED, 2)
    cv2.line(vis, (x1, y1), (x2, y2), COLOR_RED, 3)
    cv2.line(vis, (x1, y2), (x2, y1), COLOR_RED, 3)
    cv2.putText(vis, f"{text} X DIKECUALIKAN", (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_RED, 2)


# ==========================================
# 3. ROI: SIMPAN / MUAT / GAMBAR DI LAYAR
# ==========================================
def build_zones(zones):
    yellow, green, red = zones
    dir_motor = compute_entry_dir(yellow, green)
    dir_car = compute_entry_dir(yellow, red, fallback=dir_motor)
    return to_poly(yellow), to_poly(green), to_poly(red), {"motor": dir_motor, "car": dir_car}


def draw_zone(vis, pts, color):
    poly = to_poly(pts)
    overlay = vis.copy()
    cv2.fillPoly(overlay, [poly], color)
    cv2.addWeighted(overlay, 0.18, vis, 0.82, 0, vis)
    cv2.polylines(vis, [poly], True, color, 2)


def draw_overlay(frame, lines, x, y, w, alpha=0.55):
    h = 25 * len(lines) + 15
    overlay = frame.copy()
    cv2.rectangle(overlay, (x, y), (x + w, y + h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)
    for i, line in enumerate(lines):
        cv2.putText(frame, line, (x + 12, y + 28 + i * 25), cv2.FONT_HERSHEY_SIMPLEX,
                    0.52, (255, 255, 255), 1, cv2.LINE_AA)


def key_char(key):
    return chr(key).lower() if 0 <= key < 255 else ""


def draw_rois(frame_queue, initial=None):
    """
    Gambar area di atas snapshot stream, berurutan: kuning (inisialisasi), hijau (counting motor),
    merah (counting mobil). initial = list poligon tersimpan (2 atau 3 area).
    Return list 3 poligon, atau None jika batal.
    """
    n_zones = len(ROI_STEPS)
    frame = grab_frame(frame_queue)
    done = [[list(p) for p in z] for z in initial] if initial else []
    pts, cursor = [], [None]
    win = "Gambar ROI - CCTV Bapenda"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, FRAME_W, FRAME_H)

    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            if len(done) < n_zones:
                pts.append([x, y])
        elif event == cv2.EVENT_RBUTTONDOWN:
            if pts:
                pts.pop()
        elif event == cv2.EVENT_MOUSEMOVE:
            cursor[0] = (x, y)

    cv2.setMouseCallback(win, on_mouse)
    result = None
    while True:
        try:
            if cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
                break
        except cv2.error:
            break

        vis = frame.copy()
        for zone_pts, (_, color) in zip(done, ROI_STEPS):
            draw_zone(vis, zone_pts, color)

        if len(done) < n_zones:
            title, color = ROI_STEPS[len(done)]
            if pts:
                cv2.polylines(vis, [to_poly(pts)], False, color, 2)
                for p in pts:
                    cv2.circle(vis, tuple(p), 4, (255, 0, 255), -1)
                if cursor[0] is not None:
                    cv2.line(vis, tuple(pts[-1]), cursor[0], color, 1)
            lines = [
                f"GAMBAR {title}  ({len(done) + 1}/{n_zones})",
                "Klik kiri: tambah titik | Klik kanan/Backspace: undo",
                "ENTER: selesai (min 3 titik) | C: ulang | F: frame baru | Q: batal",
            ]
        else:
            lines = [
                "ROI LENGKAP (kuning + hijau + merah)",
                "ENTER: mulai | R: ulang semua | M: ulang area merah saja",
                "Q / Esc: batal",
            ]
        draw_overlay(vis, lines, 10, 10, 610)
        cv2.imshow(win, vis)

        key = cv2.waitKey(20) & 0xFF
        ch = key_char(key)
        if key == 27 or ch == "q":
            break
        if len(done) == n_zones:
            if key in (13, 10, 32):
                result = done
                break
            if ch == "r":
                done.clear()
                pts.clear()
            elif ch == "m":
                done.pop()
                pts.clear()
        else:
            if key in (13, 10, 32) and len(pts) >= 3:
                done.append(list(pts))
                pts.clear()
            elif key == 8 and pts:
                pts.pop()
            elif ch == "c":
                pts.clear()
        if ch == "f":
            frame = grab_frame(frame_queue)

    try:
        cv2.destroyWindow(win)
    except cv2.error:
        pass
    return result


# ==========================================
# 4. LOG & AKURASI
# ==========================================
def fmt_time(t):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t))


def describe_source(source):
    """Info sumber untuk CSV. URL langsung dibersihkan dari user:password dan query/token."""
    kind, value = source
    if kind == "jasnita":
        label = value                                  # id CCTV (display id)
    else:
        parsed = urlparse(value)
        host = parsed.hostname or ""
        if parsed.port:
            host += f":{parsed.port}"
        label = f"{parsed.scheme}://{host}{parsed.path}"
    return {"tipe": kind, "sumber": label, "sesi": fmt_time(time.time())}


def append_csv(path, header, row):
    """Tambah satu baris; tulis header jika file baru. Tidak menghentikan program jika file terkunci (Excel)."""
    try:
        is_new = (not path.exists()) or path.stat().st_size == 0
        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter=CSV_DELIMITER)
            if is_new:
                writer.writerow(header)
            writer.writerow(row)
    except OSError as e:
        print(f"[WARN] Gagal menulis {path.name}: {e} (tutup file jika sedang dibuka di Excel)")


def write_jpg(path, img, quality=CAPTURE_JPEG_QUALITY):
    try:
        quality = max(1, min(100, int(quality)))
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ok:
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(buf.tobytes())
        return True
    except OSError as e:
        print(f"[WARN] Gagal menyimpan gambar {path.name}: {e}")
        return False


def enhance_capture_image(img):
    """Perbesar crop CCTV dan beri sharpening ringan tanpa menambah detail palsu."""
    if img is None or img.size == 0:
        return img

    h, w = img.shape[:2]
    long_side = max(h, w)
    if long_side <= 0:
        return img

    requested_scale = max(1.0, float(CAPTURE_SCALE))
    min_side_scale = float(CAPTURE_MIN_LONG_SIDE) / float(long_side)
    scale = min(float(CAPTURE_UPSCALE_MAX), max(requested_scale, min_side_scale))

    if scale > 1.01:
        nw = max(1, int(round(w * scale)))
        nh = max(1, int(round(h * scale)))
        img = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_CUBIC)

    amount = max(0.0, min(1.0, float(CAPTURE_SHARPEN_AMOUNT)))
    if amount > 0.0:
        blurred = cv2.GaussianBlur(img, (0, 0), sigmaX=1.1)
        img = cv2.addWeighted(img, 1.0 + amount, blurred, -amount, 0)

    return img

def safe_slug(text):
    """Ubah id CCTV / URL menjadi nama folder yang aman di semua OS."""
    text = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", "", text or "")   # buang skema (rtsp://, https://, ...)
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_")
    return text[:80] or "unknown"


def ensure_event_log_schema():
    """Pastikan log utama memakai format 14 kolom yang diminta.

    Jika ada CSV lama dari versi sebelumnya, file lama dibackup otomatis agar tidak tercampur
    dengan format baru. Log baru tetap bernama log_kendaraan_terhitung.csv.
    """
    expected = [
        "ID", "NOP", "CCTV_ID", "NAMA_OP", "ALAMAT_OP", "WILAYAH_PAJAK",
        "WAKTU_MASUK", "JENIS_KEND", "PLAT_NO", "WAKTU_KELUAR",
        "DIRECTION", "LOG", "IMAGE_URL", "VENDOR"
    ]
    if not EVENT_LOG_FILE.exists() or EVENT_LOG_FILE.stat().st_size == 0:
        return

    try:
        with open(EVENT_LOG_FILE, newline="", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter=CSV_DELIMITER)
            current = next(reader, [])
    except (OSError, StopIteration):
        return

    if current == expected:
        return

    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = EVENT_LOG_FILE.with_name(f"{EVENT_LOG_FILE.stem}_legacy_{stamp}{EVENT_LOG_FILE.suffix}")
    try:
        EVENT_LOG_FILE.rename(backup)
        print(f"[INFO] Format log lama ditemukan. Backup: {backup.name}")
    except OSError as e:
        raise RuntimeError(
            f"Format {EVENT_LOG_FILE.name} lama tidak sesuai dan tidak bisa dibackup: {e}. "
            "Tutup file CSV jika sedang dibuka di Excel."
        ) from e

def _next_event_id(ctx):
    """Generate nomor ID log berurutan. Nilai terakhir dibaca sekali per sesi writer."""
    if "_next_log_id" not in ctx:
        last_id = 0
        if EVENT_LOG_FILE.exists():
            try:
                with open(EVENT_LOG_FILE, newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f, delimiter=CSV_DELIMITER)
                    for r in reader:
                        try:
                            last_id = max(last_id, int(str(r.get("ID", "")).strip()))
                        except (TypeError, ValueError):
                            # Kompatibilitas dengan log lama: abaikan ID yang bukan numerik.
                            try:
                                last_id = max(last_id, int(str(r.get("id", "")).strip()))
                            except (TypeError, ValueError):
                                continue
            except OSError as e:
                print(f"[WARN] Gagal membaca nomor ID log: {e}")
        ctx["_next_log_id"] = last_id + 1
    event_id = int(ctx["_next_log_id"])
    ctx["_next_log_id"] = event_id + 1
    return event_id


def save_capture(raw, box, tid, group, now, ctx, log_id):
    """Simpan foto kendaraan yang terhitung dan kembalikan path relatifnya."""
    if group not in CAPTURE_CLASSES:
        return ""
    x1, y1, x2, y2 = [int(v) for v in box]
    box_w = max(1, x2 - x1)
    box_h = max(1, y2 - y1)
    pad = max(24, int(CAPTURE_PAD_RATIO * max(box_w, box_h)))
    crop = raw[max(0, y1 - pad):min(FRAME_H, y2 + pad), max(0, x1 - pad):min(FRAME_W, x2 + pad)]
    if crop.size == 0:
        return ""

    crop = enhance_capture_image(crop)

    lt = time.localtime(now)
    capture_cctv = safe_slug(ctx.get("CCTV_ID") or ctx.get("sumber") or "unknown")
    folder = CAPTURE_DIR / capture_cctv / group / time.strftime("%Y-%m-%d", lt)
    stem = f"{time.strftime('%H%M%S', lt)}_ID{log_id}_track{tid}"
    path = folder / f"{stem}.jpg"
    if not write_jpg(path, crop, CAPTURE_JPEG_QUALITY):
        return ""
    if CAPTURE_FULL_FRAME:
        full = raw.copy()
        cv2.rectangle(full, (x1, y1), (x2, y2), (0, 255, 0), 2)
        write_jpg(folder / f"{stem}_full.jpg", full, CAPTURE_JPEG_QUALITY)
    return path.relative_to(BASE_DIR).as_posix()



def _read_existing_capture_excel_rows():
    """Bangun ulang daftar data Excel dari log CSV + index capture yang sudah ada."""
    rows = []
    if not CAPTURE_INDEX_FILE.exists():
        return rows

    nops = {}
    if EVENT_LOG_FILE.exists():
        try:
            with open(EVENT_LOG_FILE, newline="", encoding="utf-8") as f:
                for r in csv.DictReader(f, delimiter=CSV_DELIMITER):
                    rid = str(r.get("ID", "")).strip()
                    if rid:
                        nops[rid] = {
                            "NOP": r.get("NOP", ""),
                            "CCTV_ID": r.get("CCTV_ID", ""),
                        }
        except OSError as e:
            print(f"[WARN] Gagal membaca {EVENT_LOG_FILE.name} untuk Excel: {e}")

    try:
        with open(CAPTURE_INDEX_FILE, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f, delimiter=CSV_DELIMITER):
                rid = str(r.get("ID", "")).strip()
                image_path = (r.get("FILE_GAMBAR", "") or "").strip()
                if not rid or not image_path:
                    continue
                image_file = BASE_DIR / image_path
                if not image_file.exists() or not image_file.is_file():
                    continue
                meta = nops.get(rid, {})
                rows.append({
                    "ID": rid,
                    "NOP": meta.get("NOP", ""),
                    "CCTV_ID": r.get("CCTV_ID", "") or meta.get("CCTV_ID", ""),
                    "image_path": image_path,
                })
    except OSError as e:
        print(f"[WARN] Gagal membaca {CAPTURE_INDEX_FILE.name} untuk Excel: {e}")
    return rows


def _excel_image_dims(row):
    """Ukuran asli gambar (di-cache di baris agar tidak dibaca ulang tiap penulisan Excel)."""
    dims = row.get("dims")
    if dims is None:
        img = cv2.imread(str(BASE_DIR / row["image_path"]))
        dims = (img.shape[1], img.shape[0]) if img is not None else (CAPTURE_EXCEL_IMAGE_W, CAPTURE_EXCEL_IMAGE_H)
        row["dims"] = dims
    return dims


def _write_capture_workbook(rows, tmp_path):
    """Bangun workbook (ID | NOP | CCTV_ID | IMAGE_DATA) ke file sementara memakai XlsxWriter."""
    import xlsxwriter
    workbook = xlsxwriter.Workbook(str(tmp_path))
    try:
        worksheet = workbook.add_worksheet(CAPTURE_EXCEL_SHEET)
        header_fmt = workbook.add_format({"bold": True, "font_color": "white", "bg_color": "#1F4E78",
                                          "align": "center", "valign": "vcenter", "border": 1})
        text_fmt = workbook.add_format({"align": "center", "valign": "vcenter", "border": 1})
        worksheet.set_column("A:A", 12)
        worksheet.set_column("B:B", 24)
        worksheet.set_column("C:C", 20)
        worksheet.set_column("D:D", 46)
        worksheet.set_row(0, 24)
        worksheet.freeze_panes(1, 0)
        worksheet.autofilter(0, 0, max(1, len(rows)), 3)
        for col, value in enumerate(["ID", "NOP", "CCTV_ID", "IMAGE_DATA"]):
            worksheet.write(0, col, value, header_fmt)

        for row_idx, row in enumerate(rows, start=1):
            worksheet.set_row(row_idx, CAPTURE_EXCEL_IMAGE_H * 0.75)
            worksheet.write(row_idx, 0, row["ID"], text_fmt)
            worksheet.write(row_idx, 1, row["NOP"], text_fmt)
            worksheet.write(row_idx, 2, row["CCTV_ID"], text_fmt)
            img_path = BASE_DIR / row["image_path"]
            if not img_path.exists() or not img_path.is_file():
                worksheet.write(row_idx, 3, "[capture tidak ditemukan]", text_fmt)
                continue
            w, h = _excel_image_dims(row)
            scale = max(0.05, min(1.0, CAPTURE_EXCEL_IMAGE_W / max(1, w), CAPTURE_EXCEL_IMAGE_H / max(1, h)))
            worksheet.write_blank(row_idx, 3, None, text_fmt)
            worksheet.insert_image(row_idx, 3, str(img_path), {
                "x_scale": scale, "y_scale": scale, "x_offset": 3, "y_offset": 3,
                "description": f"Capture kendaraan ID {row['ID']}",
            })
        worksheet.write_comment(0, 3, "Gambar capture kendaraan tertanam di sel/kolom ini.")
    finally:
        workbook.close()


def _excel_is_locked(path):
    """True jika file sedang dibuka program lain (Excel menguncinya di Windows)."""
    if not path.exists():
        return False
    try:
        with open(path, "r+b"):
            return False
    except OSError:
        return True


def flush_capture_excel(ctx, force=False, final=False):
    """Tulis log_capture_kendaraan.xlsx bila ada capture baru. Dipanggil dari thread writer.

    - Ditulis paling cepat tiap CAPTURE_EXCEL_FLUSH_SEC (rebuild penuh itu berat bila dilakukan per kendaraan).
    - File sedang dibuka di Excel -> ditunda, dicoba lagi otomatis; data tidak hilang karena disimpan di memori.
    - Saat program berhenti (final) dan file masih terkunci -> disimpan ke file cadangan bertanda waktu.
    """
    rows = ctx.get("_capture_excel_rows")
    if not rows or not ctx.get("_excel_dirty"):
        return
    now = time.time()
    interval = CAPTURE_EXCEL_RETRY_SEC if ctx.get("_excel_lock_warned") else CAPTURE_EXCEL_FLUSH_SEC
    if not force and now - ctx.get("_excel_last_try", 0.0) < interval:
        return
    ctx["_excel_last_try"] = now

    try:
        import xlsxwriter  # noqa: F401
    except ImportError:
        if not ctx.get("_excel_missing_warned"):
            print("[WARN] Modul XlsxWriter belum terpasang -> Excel capture TIDAK ditulis. "
                  "Pasang dengan: python -m pip install XlsxWriter")
            ctx["_excel_missing_warned"] = True
        return

    target = CAPTURE_EXCEL_FILE
    if _excel_is_locked(target):
        if final:
            target = target.with_name(f"{target.stem}_{time.strftime('%Y%m%d_%H%M%S')}.xlsx")
        else:
            if not ctx.get("_excel_lock_warned"):
                print(f"[WARN] {target.name} sedang dibuka (Excel). Capture baru ditahan di memori dan "
                      f"akan otomatis ditulis begitu file ditutup.")
                ctx["_excel_lock_warned"] = True
            return

    tmp_path = target.with_name(target.stem + "_tmp.xlsx")
    try:
        _write_capture_workbook(rows, tmp_path)
        os.replace(str(tmp_path), str(target))        # atomik: Excel tidak pernah melihat file setengah jadi
    except Exception as e:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        if not ctx.get("_excel_lock_warned"):
            print(f"[WARN] Gagal menulis {target.name}: {e} (akan dicoba lagi)")
            ctx["_excel_lock_warned"] = True
        return
    ctx["_excel_dirty"] = False
    ctx["_excel_lock_warned"] = False
    print(f"[INFO] {target.name} diperbarui ({len(rows)} capture)")


def append_capture_to_excel(log_id, ctx, image_path):
    """Daftarkan capture baru untuk log_capture_kendaraan.xlsx (format: ID | NOP | CCTV_ID | IMAGE_DATA)."""
    if not image_path:
        return
    if not (BASE_DIR / image_path).is_file():
        print(f"[WARN] Capture untuk Excel tidak ditemukan: {image_path}")
        return

    # Cache per sesi: isi awal dari CSV + index capture (riwayat), lalu ditambah capture baru.
    cache = ctx.get("_capture_excel_rows")
    if cache is None:
        cache = _read_existing_capture_excel_rows()
        ctx["_capture_excel_rows"] = cache
    if not any(str(r.get("ID")) == str(log_id) for r in cache):
        cache.append({
            "ID": str(log_id),
            "NOP": str(ctx.get("NOP", "")),
            "CCTV_ID": str(ctx.get("CCTV_ID", "")),
            "image_path": image_path,
        })
    ctx["_excel_dirty"] = True
    flush_capture_excel(ctx)


def log_event(raw, box, tid, group, now, ctx, counts):
    """Tulis log utama dengan format kolom persis sesuai kebutuhan integrasi Bapenda."""
    log_id = _next_event_id(ctx)
    image_path = save_capture(raw, box, tid, group, now, ctx, log_id)
    waktu = fmt_time(now)

    row = [
        log_id,
        ctx.get("NOP", ""),
        ctx.get("CCTV_ID", ""),
        ctx.get("NAMA_OP", ""),
        ctx.get("ALAMAT_OP", ""),
        "-",                       # WILAYAH_PAJAK
        waktu,                      # WAKTU_MASUK
        LOG_JENIS.get(group, "MOTOR"),
        "-",                       # PLAT_NO
        waktu,                      # WAKTU_KELUAR = WAKTU_MASUK
        "IN",                      # DIRECTION
        "SUKSES",                  # LOG
        "-",                       # IMAGE_URL
        LOG_VENDOR,
    ]
    append_csv(
        EVENT_LOG_FILE,
        [
            "ID", "NOP", "CCTV_ID", "NAMA_OP", "ALAMAT_OP", "WILAYAH_PAJAK",
            "WAKTU_MASUK", "JENIS_KEND", "PLAT_NO", "WAKTU_KELUAR",
            "DIRECTION", "LOG", "IMAGE_URL", "VENDOR"
        ],
        row,
    )

    # Index internal agar HTML report tetap dapat membuka capture walaupun IMAGE_URL pada
    # log utama memang harus selalu bernilai '-'.
    append_csv(
        CAPTURE_INDEX_FILE,
        ["ID", "CCTV_ID", "WAKTU_MASUK", "JENIS_KEND", "FILE_GAMBAR"],
        [log_id, ctx.get("CCTV_ID", ""), waktu, LOG_JENIS.get(group, "MOTOR"), image_path],
    )

    # Tambahan baru: simpan capture yang sama ke Excel sebagai gambar embedded.
    append_capture_to_excel(log_id, ctx, image_path)


def write_summary(ctx, counts, truth, now, note):
    """Simpan ringkasan hitungan jumlah kendaraan."""
    # Kolom tambahan lama dipertahankan kosong agar CSV lama tetap kompatibel.
    append_csv(
        SUMMARY_FILE,
        [
            "sesi_mulai", "waktu", "tipe_sumber", "id_cctv_atau_url",
            "jumlah_mobil", "jumlah_motor", "total", "manual_mobil", "manual_motor",
            "estimasi_lolos_mobil", "estimasi_lolos_motor", "akurasi_estimasi_persen",
            "stream_uptime_persen", "stream_putus_tak_terduga", "stream_refresh_terjadwal",
            "skor_keandalan_persen", "keterangan"
        ],
        [
            ctx["sesi"], fmt_time(now), ctx["tipe"], ctx["sumber"],
            counts["car"], counts["motor"], counts["car"] + counts["motor"],
            truth["car"], truth["motor"],
            "", "", "", "", "", "", "", note
        ],
    )


# ==========================================
# 4b. LAPORAN HTML (dashboard per ID CCTV)
# ==========================================
KELAS_LABEL = {"car": "Mobil", "motor": "Motor"}
KELAS_WARNA = {"car": "#2563eb", "motor": "#16a34a"}


def capture_file_exists(file_gambar):
    """Cek apakah file capture yang tercatat di CSV masih benar-benar ada di folder capture."""
    file_gambar = (file_gambar or "").strip()
    if not file_gambar:
        return False

    try:
        path = (BASE_DIR / file_gambar).resolve()
        capture_root = CAPTURE_DIR.resolve()
        # Pastikan file yang dicek memang berada di dalam folder capture.
        path.relative_to(capture_root)
        return path.is_file()
    except (OSError, ValueError):
        return False


def _read_capture_index():
    """Bangun map ID -> file capture dari index internal."""
    index = {}
    if not CAPTURE_INDEX_FILE.exists():
        return index
    try:
        with open(CAPTURE_INDEX_FILE, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f, delimiter=CSV_DELIMITER):
                rid = str(r.get("ID", "")).strip()
                if rid:
                    index[rid] = r.get("FILE_GAMBAR", "") or ""
    except OSError as e:
        print(f"[WARN] Gagal membaca {CAPTURE_INDEX_FILE.name}: {e}")
    return index


def read_events_for_report(cctv_id, day):
    """Baca log baru berbasis CCTV_ID atau log lama, lalu hanya tampilkan capture yang masih ada."""
    rows = []
    if not EVENT_LOG_FILE.exists():
        return rows

    capture_index = _read_capture_index()
    try:
        with open(EVENT_LOG_FILE, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=CSV_DELIMITER)
            headers = set(reader.fieldnames or [])
            is_new_format = "CCTV_ID" in headers and "WAKTU_MASUK" in headers

            for r in reader:
                if is_new_format:
                    cid = (r.get("CCTV_ID") or "").strip()
                    waktu = (r.get("WAKTU_MASUK") or "").strip()
                    jenis = (r.get("JENIS_KEND") or "").strip().upper()
                    log_id = str(r.get("ID", "")).strip()
                    if cid != cctv_id or not waktu.startswith(day):
                        continue
                    group = "car" if jenis == "MOBIL" else "motor" if jenis == "MOTOR" else ""
                    if not group:
                        continue
                    rel = capture_index.get(log_id, "")
                    if not capture_file_exists(rel):
                        continue
                    # Normalisasi field internal agar renderer lama tetap sederhana.
                    r["waktu"] = waktu
                    r["kelas"] = group
                    r["file_gambar"] = rel
                    r["track_id"] = log_id
                else:
                    # Kompatibilitas log versi sebelumnya.
                    if r.get("id_cctv_atau_url") != cctv_id or not r.get("waktu", "").startswith(day):
                        continue
                    if not capture_file_exists(r.get("file_gambar")):
                        continue
                rows.append(r)
    except OSError as e:
        print(f"[WARN] Gagal membaca {EVENT_LOG_FILE.name}: {e}")
        return rows

    seen, unique = set(), []
    for r in rows:
        key = r.get("ID") if "ID" in r else (r.get("track_id"), r.get("kelas"), r.get("waktu"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)
    unique.sort(key=lambda r: r.get("waktu", r.get("WAKTU_MASUK", "")), reverse=True)
    return unique


def list_known_cctv_ids(day=None):
    """Ambil CCTV_ID dari log baru atau id_cctv_atau_url dari log lama."""
    ids = []
    if not EVENT_LOG_FILE.exists():
        return ids
    seen = set()
    try:
        with open(EVENT_LOG_FILE, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=CSV_DELIMITER)
            headers = set(reader.fieldnames or [])
            is_new_format = "CCTV_ID" in headers
            for r in reader:
                if is_new_format:
                    cid = (r.get("CCTV_ID") or "").strip()
                    when = (r.get("WAKTU_MASUK") or "").strip()
                else:
                    cid = (r.get("id_cctv_atau_url") or "").strip()
                    when = (r.get("waktu") or "").strip()
                if not cid or cid in seen:
                    continue
                if day and not when.startswith(day):
                    continue
                seen.add(cid)
                ids.append(cid)
    except OSError as e:
        print(f"[WARN] Gagal membaca {EVENT_LOG_FILE.name}: {e}")
    return ids


def hourly_counts(rows):
    buckets = {h: {"car": 0, "motor": 0} for h in range(24)}
    for r in rows:
        try:
            h = int(r["waktu"][11:13])
        except (ValueError, IndexError, KeyError):
            continue
        k = r.get("kelas")
        if k in buckets.get(h, {}):
            buckets[h][k] += 1
    return buckets


def build_svg_chart(buckets, width=760, height=200):
    pad_l, pad_r, pad_t, pad_b = 34, 8, 10, 22
    max_v = max(1, max(max(b["car"], b["motor"]) for b in buckets.values()))
    step = max(1, -(-max_v // 4))  # ceil(max_v/4), min 1

    def x(h):
        return pad_l + h * (width - pad_l - pad_r) / 23.0

    def y(v):
        return height - pad_b - (v / max_v) * (height - pad_t - pad_b)

    def line(kelas, color):
        pts = " ".join(f"{x(h):.1f},{y(buckets[h][kelas]):.1f}" for h in range(24))
        return f'<polyline fill="none" stroke="{color}" stroke-width="2.5" points="{pts}" />'

    grid, v = [], 0
    while v <= max_v:
        grid.append(f'<line x1="{pad_l}" y1="{y(v):.1f}" x2="{width - pad_r}" y2="{y(v):.1f}" '
                    f'stroke="#e5e7eb" stroke-width="1"/>')
        grid.append(f'<text x="2" y="{y(v) + 4:.1f}" font-size="10" fill="#6b7280">{v}</text>')
        v += step
    labels = "".join(
        f'<text x="{x(h):.1f}" y="{height - 6}" font-size="10" fill="#6b7280" text-anchor="middle">{h:02d}</text>'
        for h in range(0, 24, 2)
    )
    return (f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
            f'xmlns="http://www.w3.org/2000/svg">' + "".join(grid) + labels +
            line("car", KELAS_WARNA["car"]) + line("motor", KELAS_WARNA["motor"]) + "</svg>")


def render_report_html(cctv_id, day, rows):
    total = {"car": sum(1 for r in rows if r["kelas"] == "car"),
             "motor": sum(1 for r in rows if r["kelas"] == "motor")}
    buckets = hourly_counts(rows)
    busiest = max(buckets.items(), key=lambda kv: kv[1]["car"] + kv[1]["motor"])
    n_hours_active = sum(1 for b in buckets.values() if b["car"] or b["motor"]) or 1
    avg_motor_per_jam = total["motor"] / n_hours_active
    avg_mobil_per_jam = total["car"] / n_hours_active
    chart = build_svg_chart(buckets)
    def cell_img(r):
        rel = (r.get("file_gambar") or "").strip()
        if rel and capture_file_exists(rel):
            src = html.escape(f"../{rel}", quote=True)
            return (f'<a class="capture-link" href="{src}" '
                    f'onclick="openCapture(event, this.href)" title="Klik untuk memperbesar">'
                    f'<img src="{src}" alt="capture kendaraan" loading="lazy" decoding="async" draggable="false"></a>')
        return '<div class="no-img">-</div>'


    def cell_row(r):
        kelas = r.get("kelas", "")
        badge = KELAS_LABEL.get(kelas, kelas)
        color = KELAS_WARNA.get(kelas, "#6b7280")
        waktu = html.escape(r.get("waktu", "")[11:19])
        tid = html.escape(str(r.get("track_id", "")))
        return (f'<tr><td class="thumb">{cell_img(r)}</td>'
                f'<td>{waktu}</td>'
                f'<td><span class="badge" style="background:{color}1a;color:{color}">{html.escape(badge)}</span></td>'
                f'<td class="muted">#{tid}</td></tr>')

    rows_html = "".join(cell_row(r) for r in rows) or (
        '<tr><td colspan="4" class="muted center">Belum ada kendaraan terhitung pada tanggal ini.</td></tr>')

    return f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Laporan Traffic Counting - {html.escape(cctv_id)} - {day}</title>
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
         background: #f3f4f6; color: #111827; }}
  .wrap {{ max-width: 1080px; margin: 0 auto; padding: 24px 20px 60px; }}
  header {{ margin-bottom: 20px; }}
  header h1 {{ font-size: 20px; margin: 0 0 4px; }}
  header .sub {{ color: #6b7280; font-size: 13px; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
           gap: 14px; margin-bottom: 22px; }}
  .card {{ background: #fff; border-radius: 12px; padding: 16px; box-shadow: 0 1px 2px rgba(0,0,0,.06); }}
  .card .label {{ font-size: 12px; color: #6b7280; margin-bottom: 6px; }}
  .card .value {{ font-size: 26px; font-weight: 700; }}
  .card.mobil .value {{ color: {KELAS_WARNA["car"]}; }}
  .card.motor .value {{ color: {KELAS_WARNA["motor"]}; }}
  .panel {{ background: #fff; border-radius: 12px; padding: 18px; box-shadow: 0 1px 2px rgba(0,0,0,.06);
           margin-bottom: 22px; }}
  .panel h2 {{ font-size: 14px; margin: 0 0 12px; color: #374151; }}
  .legend {{ display: flex; gap: 16px; font-size: 12px; color: #374151; margin-top: 6px; }}
  .legend span::before {{ content: ""; display: inline-block; width: 10px; height: 10px; border-radius: 50%;
                         margin-right: 5px; vertical-align: -1px; }}
  .legend .l-mobil::before {{ background: {KELAS_WARNA["car"]}; }}
  .legend .l-motor::before {{ background: {KELAS_WARNA["motor"]}; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ text-align: left; padding: 8px 10px; background: #f9fafb; color: #6b7280;
       font-weight: 600; border-bottom: 1px solid #e5e7eb; }}
  td {{ padding: 8px 10px; border-bottom: 1px solid #f3f4f6; vertical-align: middle; }}
  tr:hover td {{ background: #f9fafb; }}
  td.thumb {{ width: {REPORT_THUMB_W + 14}px; }}
  .capture-link {{ display: inline-flex; width: {REPORT_THUMB_W}px; height: {REPORT_THUMB_H}px; align-items: center; justify-content: center;
                  border-radius: 10px; overflow: hidden; background: #111827; cursor: zoom-in;
                  box-shadow: 0 1px 3px rgba(0,0,0,.12); text-decoration: none; }}
  td.thumb img {{ width: {REPORT_THUMB_W}px; height: {REPORT_THUMB_H}px; object-fit: contain; display: block;
                 cursor: zoom-in; }}
  .capture-link:hover {{ box-shadow: 0 0 0 2px #2563eb55; transform: translateY(-1px); }}
  .no-img {{ width: {REPORT_THUMB_W}px; height: {REPORT_THUMB_H}px; border-radius: 10px; background: #f3f4f6; color: #9ca3af;
            display: flex; align-items: center; justify-content: center; font-size: 12px; }}

  .image-modal {{ position: fixed; inset: 0; z-index: 9999; display: none; padding: 24px;
                  background: rgba(0,0,0,.78); align-items: center; justify-content: center; cursor: zoom-out; }}
  .image-modal.show {{ display: flex; }}
  .image-modal-content {{ position: relative; max-width: 96vw; max-height: 94vh; display: flex;
                          align-items: center; justify-content: center; cursor: default; }}
  .image-modal-content img {{ max-width: 96vw; max-height: 94vh; width: auto; height: auto;
                              object-fit: contain; border-radius: 8px; box-shadow: 0 8px 40px rgba(0,0,0,.45);
                              background: #111827; display: block; }}
  .image-modal-close {{ position: fixed; top: 16px; right: 20px; width: 42px; height: 42px;
                        border: 0; border-radius: 50%; background: rgba(255,255,255,.92); color: #111827;
                        font-size: 28px; line-height: 42px; text-align: center; cursor: pointer;
                        box-shadow: 0 2px 10px rgba(0,0,0,.2); }}
  .image-modal-hint {{ position: fixed; left: 50%; bottom: 16px; transform: translateX(-50%);
                       color: #fff; font-size: 12px; background: rgba(0,0,0,.42); padding: 6px 10px;
                       border-radius: 999px; }}
  body.modal-open {{ overflow: hidden; }}
  .badge {{ padding: 3px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; }}
  .muted {{ color: #6b7280; }}
  .center {{ text-align: center; padding: 24px 0; }}
  .detail {{ font-size: 13px; color: #374151; line-height: 1.9; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Laporan Traffic Counting</h1>
    <div class="sub">ID CCTV: <strong>{html.escape(cctv_id)}</strong> &middot; Tanggal: {day}
      &middot; Dibuat: {fmt_time(time.time())}</div>
  </header>

  <div class="cards">
    <div class="card mobil"><div class="label">Mobil Hari Ini</div><div class="value">{total["car"]}</div></div>
    <div class="card motor"><div class="label">Motor Hari Ini</div><div class="value">{total["motor"]}</div></div>
    <div class="card"><div class="label">Total Kendaraan</div><div class="value">{total["car"] + total["motor"]}</div></div>
  </div>

  <div class="panel">
    <h2>Kendaraan per Jam</h2>
    {chart}
    <div class="legend"><span class="l-mobil">Mobil</span><span class="l-motor">Motor</span></div>
    <div class="detail" style="margin-top:14px">
      Jam tersibuk: {busiest[0]:02d}:00 - {busiest[0]:02d}:59
      ({busiest[1]["car"] + busiest[1]["motor"]} kendaraan)<br>
      Rata-rata motor per jam aktif: {avg_motor_per_jam:.1f}<br>
      Rata-rata mobil per jam aktif: {avg_mobil_per_jam:.1f}
    </div>
  </div>

  <div class="panel">
    <h2>Aktivitas Hari Ini ({len(rows)} kendaraan, capture terbaru di atas, tanpa duplikat)</h2>
    <table>
      <thead><tr><th>Capture</th><th>Waktu</th><th>Jenis</th><th>ID Track</th></tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>
</div>

<div id="captureModal" class="image-modal" onclick="closeCapture(event)" aria-hidden="true">
  <button class="image-modal-close" type="button" onclick="closeCapture()" aria-label="Tutup">&times;</button>
  <div class="image-modal-content">
    <img id="captureModalImg" src="" alt="Capture kendaraan diperbesar">
  </div>
  <div class="image-modal-hint">Klik di luar gambar atau tekan Esc untuk menutup</div>
</div>

<script>
function openCapture(event, src) {{
  if (event) event.preventDefault();
  const modal = document.getElementById('captureModal');
  const img = document.getElementById('captureModalImg');
  img.src = src;
  modal.classList.add('show');
  modal.setAttribute('aria-hidden', 'false');
  document.body.classList.add('modal-open');
}}

function closeCapture(event) {{
  const modal = document.getElementById('captureModal');
  if (event && event.target !== modal) return;
  modal.classList.remove('show');
  modal.setAttribute('aria-hidden', 'true');
  document.body.classList.remove('modal-open');
  document.getElementById('captureModalImg').src = '';
}}

document.addEventListener('keydown', function(event) {{
  if (event.key === 'Escape') closeCapture();
}});
</script>
</body>
</html>"""


def generate_html_report(cctv_id, day=None):
    """Buat/timpa 1 file laporan.html untuk satu ID CCTV pada satu tanggal. Return path file."""
    day = day or time.strftime("%Y-%m-%d")
    rows = read_events_for_report(cctv_id, day)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"laporan_{safe_slug(cctv_id)}_{day.replace('-', '')}.html"
    path.write_text(render_report_html(cctv_id, day, rows), encoding="utf-8")
    return path


def accuracy(auto, truth):
    if truth <= 0:
        return None
    return 100.0 * max(0.0, 1.0 - abs(auto - truth) / truth)


# ==========================================
# 5. PROSES UTAMA
# ==========================================
def writer_worker(q, ctx):
    """
    THREAD TERPISAH dari GUI: menjalankan semua operasi disk yang berat/lambat -- simpan foto capture,
    tulis CSV, buat laporan HTML -- supaya loop tampilan (run()) tidak pernah menunggu disk. Ini yang
    sebelumnya jadi penyebab jendela freeze tepat saat ada kendaraan yang baru terhitung: log_event()
    dulu dipanggil langsung di thread GUI. Sentinel None dipakai utk menghentikan thread ini dgn rapi.
    """
    while True:
        try:
            item = q.get(timeout=2.0)
        except Empty:
            # Antrean kosong: manfaatkan untuk menyinkronkan Excel yang tertunda (mis. baru ditutup dari Excel).
            try:
                flush_capture_excel(ctx)
            except Exception as e:
                print(f"[WARN] Sinkron Excel gagal: {e}")
            continue
        try:
            if item is None:
                flush_capture_excel(ctx, force=True, final=True)
                return
            kind = item[0]
            if kind == "log_event":
                _, raw, box, tid, group, now, counts_snapshot = item
                log_event(raw, box, tid, group, now, ctx, counts_snapshot)
            elif kind == "summary":
                _, counts_snapshot, truth_snapshot, now, note = item
                write_summary(ctx, counts_snapshot, truth_snapshot, now, note)
            elif kind == "report":
                _, day = item
                generate_html_report(ctx["CCTV_ID"], day)
        except Exception as e:
            # Jangan sampai thread ini mati gara-gara 1 penulisan gagal (mis. file lagi dibuka di Excel);
            # cukup catat, sisanya tetap lanjut -- konsisten dgn append_csv/write_jpg yg juga toleran begitu.
            print(f"[WARN] Penulis background gagal ({item[0] if item else '?'}): {e}")
        finally:
            q.task_done()


def run(frame_queue, counts, truth, session):
    ctx = session["ctx"]
    # --- Gambar / konfirmasi ROI di layar ---
    print("[INFO] Gambar ulang semua area (kuning, hijau, merah) ...")
    roi = draw_rois(frame_queue)
    if roi is None:
        print("[INFO] Pengaturan ROI dibatalkan.")
        return
    yellow_roi, green_roi, red_roi, entry_dirs = build_zones(roi)

    tracker_path = Path(__file__).with_name("bytetrack_traffic.yaml")
    tracker_path.write_text(TRACKER_CFG)

    # Semua penulisan disk (capture foto, CSV, laporan HTML) dikerjakan thread terpisah, BUKAN di GUI loop --
    # ini yang bikin jendela tidak lagi freeze tepat saat kendaraan baru terhitung.
    write_queue = Queue()
    writer_thread = threading.Thread(target=writer_worker, args=(write_queue, ctx), daemon=True)
    writer_thread.start()

    # YOLO berjalan di proses terpisah (inference_worker) supaya jendela tampilan di bawah ini
    # tidak pernah menunggu proses deteksi yang berat -> tidak "Not Responding".
    result_queue = mp.Queue(maxsize=1)
    infer_proc = mp.Process(target=inference_worker, args=(frame_queue, result_queue, str(tracker_path)),
                             daemon=True)
    infer_proc.start()

    tracks, lost = {}, {}
    counted_ids = set()   # ID yang sudah terhitung (tidak akan dihitung lagi)
    total_init = 0
    fps, prev_t = 0.0, time.time()
    last_summary, last_written = time.time(), (0, 0)
    debug = False

    current_day = time.strftime("%Y-%m-%d")

    win = "CCTV Bapenda - AI Traffic Counting v5"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, FRAME_W, FRAME_H)
    excl_marks = []   # tanda X merah aktif: {"tid", "box", "t", "parked"} -- TIDAK direset saat ganti hari / edit ROI
    clicks = []

    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            clicks.append((x, y))   # diproses di loop utama (state track tidak disentuh dari callback)

    cv2.setMouseCallback(win, on_mouse)
    print("[INFO] Menunggu model YOLO siap di proses terpisah ...")
    print("[INFO] Berjalan. q=keluar, d=debug, r=edit ROI, z=+motor manual, x=+mobil manual, "
          "klik kiri=tanda X (kecualikan), c=hapus semua X")
    session["counting"] = True

    try:
        while True:
            try:
                raw, payload, t_frame = result_queue.get(timeout=5.0)
            except Empty:
                # Tetap proses tombol & pompa jendela walau belum ada hasil deteksi baru,
                # supaya jendela tetap dianggap "responding" oleh Windows.
                key_char(cv2.waitKey(30) & 0xFF)
                continue

            # Waktu frame (bukan waktu terima hasil) -> kecepatan, deteksi parkir, relink konsisten di FPS rendah.
            now = t_frame
            fps = 0.9 * fps + 0.1 * (1.0 / max(now - prev_t, 1e-3))
            prev_t = now

            today = time.strftime("%Y-%m-%d", time.localtime(now))
            if today != current_day:
                prev_day = current_day
                write_queue.put(("summary", dict(counts), dict(truth), now, "ganti_hari"))
                write_queue.put(("report", prev_day))
                log_network_event(ctx["sumber"], "ganti_hari",
                                   detail=f"reset counter dari {prev_day} ke {today}")
                counts["car"] = counts["motor"] = 0
                truth["car"] = truth["motor"] = 0
                total_init = 0
                tracks.clear()
                lost.clear()
                counted_ids.clear()
                last_written = (0, 0)
                current_day = today
                print(f"[INFO] Tanggal berganti ke {today} -> semua hitungan (mobil/motor) direset ke 0.")

            vis = raw.copy()
            cv2.polylines(vis, [yellow_roi], True, COLOR_YELLOW, 2)
            cv2.polylines(vis, [green_roi], True, COLOR_GREEN, 2)
            cv2.polylines(vis, [red_roi], True, COLOR_RED, 2)

            seen = set()
            frame_dets = []   # (tid, bbox) semua deteksi frame ini -> sasaran klik tanda X
            if payload is not None:
                xyxy = payload["xyxy"]
                ids = payload["ids"].tolist()
                clss = payload["cls"].tolist()
                confs = payload["conf"].tolist()
                frame_ids = set(ids)

                # Segarkan dulu tanda X yang pemiliknya terlihat di frame ini, supaya tanda tsb tidak 'dicuri'
                # deteksi lain lewat tumpukan bbox (find_exclusion_mark hanya memakai tanda yang tidak terlihat).
                box_by_tid = {t: tuple(float(v) for v in b) for b, t in zip(xyxy, ids)}
                for m in excl_marks:
                    if m["tid"] in box_by_tid:
                        m["box"], m["t"] = box_by_tid[m["tid"]], now

                for box, tid, cls_id, conf in zip(xyxy, ids, clss, confs):
                    group = "motor" if cls_id == 3 else "car"
                    x1, y1, x2, y2 = box
                    pt = ((float(x1) + float(x2)) / 2.0, float(y2))  # titik kaki = bidang tanah
                    seen.add(tid)
                    box_t = box_by_tid[tid]
                    frame_dets.append((tid, box_t))

                    # TANDA X: dicek di SETIAP frame, termasuk deteksi yang belum/tidak punya track.
                    is_new_id = tid not in tracks and tid not in lost
                    mark = find_exclusion_mark(excl_marks, tid, box_t, now, allow_iou=is_new_id)
                    if mark is not None:
                        mark["tid"], mark["box"], mark["t"] = tid, box_t, now

                    st = tracks.get(tid)

                    # Kendaraan baru HANYA mulai dibuat ketika badan kendaraan menyentuh
                    # area KUNING. Namun sebelum menolak objek di luar kuning, coba relink dulu:
                    # bila ini sebenarnya kendaraan lama yang baru mendapat ID berbeda setelah keluar
                    # dari kuning, track harus tetap dilanjutkan sampai zona counting.
                    yellow_hit_new, yellow_anchor_new = touches_bbox(yellow_roi, box)
                    if st is None:
                        st = lost.pop(tid, None)                       # ID lama muncul kembali
                        if st is None:
                            # ID baru: sambung ke track lama yang sudah hilang ATAU yang tidak muncul di frame ini
                            # (ByteTrack mengganti ID tepat saat track lama menghilang).
                            pool = dict(lost)
                            for k, v in tracks.items():
                                if k not in frame_ids and v.last_seen < now:
                                    pool[k] = v
                            old = find_relink(pool, pt, group, now)
                            if old is not None:
                                st = lost.pop(old, None)
                                if st is None:
                                    st = tracks.pop(old, None)

                        # Belum punya track lama dan belum menyentuh kuning -> jangan buat state baru.
                        if st is None and not yellow_hit_new:
                            if mark is not None:
                                draw_excluded(vis, box_t, f"#{tid}")
                            continue

                        if st is None:
                            st = TrackState(now)
                        tracks[tid] = st
                        if tid in counted_ids:
                            st.counted = True          # ID yang sudah pernah terhitung tidak dihitung lagi
                        elif st.counted:
                            counted_ids.add(tid)       # state hasil relink yang sudah terhitung

                    # Track bertanda X (termasuk hasil relink ke ID baru) membawa tandanya ke ID sekarang.
                    if mark is None and st.excluded and st.mark is not None:
                        mark = st.mark
                        mark["tid"], mark["box"], mark["t"] = tid, box_t, now
                        if mark not in excl_marks:
                            excl_marks.append(mark)
                    if mark is not None:
                        st.excluded, st.mark = True, mark
                        mark["parked"] = st.parked or st.was_parked

                    st.frames += 1
                    # Voting kelas diperkuat: observasi confidence rendah tidak ikut menentukan
                    # identitas, sedangkan observasi yang lolos diberi bobot sesuai confidence YOLO.
                    st.votes[group] += 1
                    if float(conf) >= MIN_CLASS_CONF:
                        st.class_obs[group] += 1
                        st.class_scores[group] += float(conf)
                    st.last_group = group
                    st.last_conf = float(conf)
                    prev_pt = st.last_pt
                    prev_box = st.last_box

                    # --- Inisialisasi (kuning) ---
                    # Bounding box tetap dipakai untuk MEMBUAT track, tetapi inisialisasi SAH dan urutan arah
                    # memakai TITIK KAKI/RODA (bidang tanah). Bbox motor yang tinggi dapat menyentuh kuning
                    # padahal kendaraannya masih di hijau -> itu penyebab arah balik ikut terhitung.
                    yellow_hit, yellow_anchor = touches_bbox(yellow_roi, box, prev_box)
                    if yellow_hit:
                        st.yellow_hits += 1
                        if st.yellow_pt is None:
                            st.yellow_pt = yellow_anchor if yellow_anchor is not None else pt
                    wheels = wheel_points(float(x1), float(x2), float(y2))
                    prev_first = dict(st.target_first_t)
                    update_zone_order(st, wheels, prev_pt, pt, now, yellow_roi, green_roi, red_roi, box)
                    note_target_touch(st, prev_first, raw, box, now)
                    update_trajectory_stats(st, pt, box, green_roi, red_roi, entry_dirs, now)
                    # Kendaraan yang baru terlihat setelah keluar dari bayangan (kaki tak pernah di kuning) sah bila
                    # badannya menyentuh kuning dan ia bergerak MAJU searah kuning -> hijau/merah.
                    maybe_init_by_motion(st, st.confirmed_group or group, box)
                    if (not st.initialized and st.yellow_foot_t is not None
                            and st.frames >= MIN_TRACK_FRAMES):
                        st.initialized = True
                        total_init += 1

                    # --- Counting: INDIKATOR HANYA GARIS ROI ---
                    # Motor: badan kendaraan menyentuh/menyeberangi GARIS HIJAU.
                    # Mobil/bus/truk: roda ATAU badan kendaraan menyentuh/menyeberangi GARIS MERAH.
                    # Tentukan kelas kendaraan secara temporal + confidence-weighted.
                    # Ini mengurangi kasus 1-2 frame motor terbaca sebagai mobil (atau sebaliknya).
                    valid_class_obs = sum(st.class_obs.values())
                    ranked_classes = st.class_scores.most_common()
                    if valid_class_obs >= MIN_CLASS_CONFIRM_FRAMES and ranked_classes:
                        best_group, best_score = ranked_classes[0]
                        second_score = ranked_classes[1][1] if len(ranked_classes) > 1 else 0.0
                        margin_ok = (second_score <= 0.0 or
                                     best_score >= second_score * (1.0 + CLASS_SCORE_MARGIN))
                        if margin_ok:
                            st.confirmed_group = best_group

                    # Posisi/gerak: tandai PARKIR bila diam, catat apakah sudah pernah di LUAR area counting.
                    update_motion_state(st, pt, box, now)
                    for g_name, g_roi in (("motor", green_roi), ("car", red_roi)):
                        if not inside(g_roi, pt) and not point_near_poly_boundary(g_roi, pt):
                            st.outside_seen[g_name] = True

                    # Syarat hitung (lihat should_count): sudah inisialisasi di kuning, kaki lebih dulu kuning baru
                    # hijau/merah, pernah di luar area counting, tidak parkir, bergerak nyata, dan MENDEKAT.
                    update_cross_latch(st, pt, box, prev_box, wheels, raw, green_roi, red_roi, entry_dirs)
                    if tid not in counted_ids:
                        cur_group = should_count(st, pt, box, prev_box, wheels, now, green_roi, red_roi, entry_dirs)
                        st.ready_frames = st.ready_frames + 1 if cur_group is not None else 0
                        if cur_group is not None and st.ready_frames < COUNT_CONFIRM_FRAMES:
                            cur_group = None                 # tunggu konfirmasi di observasi berikutnya
                        if cur_group is not None:
                            st.counted = True
                            st.counted_group, st.counted_t = cur_group, now
                            counted_ids.add(tid)
                            if is_duplicate_count(st, pt, box, cur_group, now, tracks, lost):
                                print(f"[INFO] #{tid} {cur_group} dilewati: duplikat kendaraan yang baru terhitung")
                            else:
                                counts[cur_group] += 1
                                # Foto diambil dari saat kendaraan menyentuh garis (kunci lintas), bukan dari
                                # observasi konfirmasi yang di FPS rendah bisa sudah jauh melewati area.
                                _, raw_c, box_c = st.cross[cur_group]
                                write_queue.put(("log_event", raw_c, box_c, tid, cur_group, now, dict(counts)))

                    st.last_pt = pt
                    st.last_wheels = wheels
                    st.last_box = tuple(float(v) for v in box)
                    st.last_seen = now

                    if st.excluded:
                        st.mark["parked"] = st.parked or st.was_parked
                        draw_excluded(vis, box_t, f"#{tid}")
                        continue

                    display_group = st.confirmed_group or group
                    wrong_way = st.reverse[display_group] and not st.counted
                    if (st.initialized and not st.parked and not wrong_way) or debug:
                        color = (COLOR_GREEN if st.counted else (COLOR_YELLOW if st.initialized else (160, 160, 160)))
                        label_extra = ""
                        if st.parked:
                            color, label_extra = (255, 128, 0), " PARKIR"       # hanya tampil saat debug 'd'
                        elif wrong_way:
                            color, label_extra = (128, 0, 255), " ARAH BALIK"   # hanya tampil saat debug 'd'
                        cv2.rectangle(vis, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
                        cv2.putText(vis, f"#{tid} {LABEL[display_group]} {conf:.2f}{label_extra}", (int(x1), int(y1) - 5),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                        if debug:
                            reason = why_not(st, pt, box, prev_box, wheels, now, green_roi, red_roi, entry_dirs)
                            cv2.putText(vis, reason, (int(x1), int(y2) + 14),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
                        for wp in (wheels if group == "car" else [pt]):
                            cv2.circle(vis, (int(wp[0]), int(wp[1])), 4, (255, 0, 255), -1)
                        # Marker kecil kontak garis target saat debug/track sudah diinisialisasi.
                        target_roi = green_roi if display_group == "motor" else red_roi
                        for bp in bbox_anchor_points(box)[:5]:
                            if point_near_poly_boundary(target_roi, bp):
                                cv2.circle(vis, (int(bp[0]), int(bp[1])), 5, (0, 165, 255), -1)

            # Track yang tidak terlihat -> pindah ke 'lost' (untuk relink) atau dibuang
            for tid in list(tracks):
                st = tracks[tid]
                if tid not in seen and now - st.last_seen > LOST_AFTER:
                    del tracks[tid]
                    if st.yellow_pt is not None or st.initialized:
                        lost[tid] = st
            for tid in list(lost):
                st = lost[tid]
                if now - st.last_seen > RELINK_TIME:
                    # Track yang terlalu lama hilang dibuang dari daftar relink -> sapuan akhir dulu.
                    g_flush = missed_crossing_group(st, tid, counted_ids)
                    if g_flush is not None:
                        raw_s, box_s, t_s = st.snap[g_flush]
                        st.counted = True
                        st.counted_group, st.counted_t = g_flush, t_s
                        counted_ids.add(tid)
                        foot_s = ((box_s[0] + box_s[2]) / 2.0, box_s[3])
                        if is_duplicate_count(st, foot_s, box_s, g_flush, t_s, tracks, lost):
                            print(f"[INFO] #{tid} {g_flush} sapuan akhir dilewati: duplikat kendaraan yang sudah terhitung")
                        else:
                            counts[g_flush] += 1
                            write_queue.put(("log_event", raw_s, box_s, tid, g_flush, t_s, dict(counts)))
                            print(f"[INFO] #{tid} {g_flush} terhitung lewat SAPUAN AKHIR (melintas tapi lolos gerbang per-frame)")
                    elif DIAG_LOG:
                        diag_miss(tid, st)
                    del lost[tid]

            # Tanda X: proses klik operator, lalu buang tanda yang pemiliknya sudah lama tak terlihat.
            while clicks:
                toggle_exclusion(clicks.pop(0), frame_dets, excl_marks, tracks, lost, now)
            excl_marks[:] = [m for m in excl_marks
                             if now - m["t"] <= (EXCLUDE_KEEP_PARKED_SEC if m["parked"] else EXCLUDE_KEEP_SEC)]
            excluded_n = sum(1 for m in excl_marks if m["t"] >= now)

            pending = sum(1 for t in seen if t in tracks and tracks[t].initialized and not tracks[t].excluded
                          and not tracks[t].counted and not tracks[t].parked and not tracks[t].was_parked
                          and not tracks[t].reverse.get(tracks[t].confirmed_group, False))
            parked_n = sum(1 for t in seen if t in tracks and tracks[t].parked)
            lines = [
                "--- TRAFFIC ANALYTICS ---",
                f"Mobil (Car)       : {counts['car']}",
                f"Motorcycle        : {counts['motor']}",
                f"Total Vehicle     : {counts['car'] + counts['motor']}",
                "-------------------------",
                f"Lewat zona kuning : {total_init}",
                f"Sedang transit    : {pending}",
                f"Parkir (diabaikan): {parked_n}",
                f"Tanda X (dikecual): {excluded_n}",
                f"FPS               : {fps:.1f}",
]
            if truth["car"] or truth["motor"]:
                ac, am = accuracy(counts["car"], truth["car"]), accuracy(counts["motor"], truth["motor"])
                lines += [
                    "--- vs HITUNGAN MANUAL ---",
                    f"Manual Mobil/Motor: {truth['car']}/{truth['motor']}",
                    f"Akurasi Mobil     : {'n/a' if ac is None else f'{ac:.1f}%'}",
                    f"Akurasi Motor     : {'n/a' if am is None else f'{am:.1f}%'}",
                ]
            if now - last_summary >= SUMMARY_INTERVAL_SEC:
                last_summary = now
                current = (counts["car"], counts["motor"])
                if current != last_written:
                    write_queue.put(("summary", dict(counts), dict(truth), now, "berkala"))
                    write_queue.put(("report", current_day))
                    last_written = current
            draw_overlay(vis, lines, FRAME_W - 320, 10, 310)
            cv2.imshow(win, vis)

            key = cv2.waitKey(1) & 0xFF
            ch = key_char(key)
            if ch == "q":
                break
            elif ch == "d":
                debug = not debug
            elif ch == "z":
                truth["motor"] += 1
            elif ch == "x":
                truth["car"] += 1
            elif ch == "c":
                for m in list(excl_marks):
                    drop_exclusion_mark(m, excl_marks, tracks, lost)
                print("[INFO] Semua tanda X dihapus")
            elif ch == "r":
                new_roi = draw_rois(frame_queue, roi)
                if new_roi is not None:
                    roi = new_roi
                    yellow_roi, green_roi, red_roi, entry_dirs = build_zones(roi)
                    tracks.clear()
                    lost.clear()
                prev_t = time.time()
    finally:
        # Tunggu semua tulisan yg masih di antrean selesai dulu, baru tutup thread-nya dgn rapi.
        write_queue.join()
        write_queue.put(None)
        writer_thread.join(timeout=5)
        # Ringkasan akhir ditulis LANGSUNG (bukan lewat antrean) -- satu-satunya penulisan blocking yg
        # tersisa, sengaja, karena hanya terjadi sekali saat program benar-benar berhenti, bukan saat
        # kendaraan lewat, jadi tidak lagi menyebabkan freeze.
        write_summary(ctx, counts, truth, time.time(), "akhir")
        report_path = generate_html_report(ctx["CCTV_ID"], current_day)
        print(f"[HASIL] Mobil={counts['car']} Motor={counts['motor']} | "
              f"ringkasan: {SUMMARY_FILE.name} | laporan: {report_path}")
        infer_proc.terminate()
        infer_proc.join()




def ask_log_metadata():
    """Minta metadata lokasi/objek sekali di awal sesi counting."""
    fields = [
        ("NOP", "Masukkan NOP"),
        ("CCTV_ID", "Masukkan CCTV_ID"),
        ("NAMA_OP", "Masukkan NAMA_OP"),
        ("ALAMAT_OP", "Masukkan ALAMAT_OP"),
    ]
    data = {}
    for key, prompt in fields:
        while True:
            try:
                value = input(f"{prompt}: ").strip()
            except EOFError:
                print("[ERROR] Input metadata tidak tersedia.")
                sys.exit(1)
            if value:
                data[key] = value
                break
            print(f"[ERROR] {key} wajib diisi.")
    print(
        f"[INFO] Metadata log: NOP={data['NOP']} | CCTV_ID={data['CCTV_ID']} | "
        f"NAMA_OP={data['NAMA_OP']} | ALAMAT_OP={data['ALAMAT_OP']}"
    )
    return data


def ensure_excel_dependency():
    """XlsxWriter dibutuhkan untuk log_capture_kendaraan.xlsx. Coba pasang otomatis bila belum ada."""
    try:
        import xlsxwriter  # noqa: F401
        return True
    except ImportError:
        pass
    print("[INFO] XlsxWriter belum terpasang -> mencoba memasang otomatis (untuk log_capture_kendaraan.xlsx) ...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "XlsxWriter"])
        import importlib
        importlib.invalidate_caches()
        import xlsxwriter  # noqa: F401
        print("[INFO] XlsxWriter berhasil dipasang.")
        return True
    except Exception as e:
        print(f"[WARN] Gagal memasang XlsxWriter otomatis ({e}). Pasang manual: python -m pip install XlsxWriter")
        return False


def main():
    if "--report" in sys.argv:
        cli_report()
        return
    source = ask_stream_source()
    if source[0] == "jasnita" and not (JASNITA_USER and JASNITA_PASS):
        print("Kredensial JASNITA_USER / JASNITA_PASS belum diisi.")
        sys.exit(1)
    print(f"[INFO] Sumber stream: {'Jasnita display ' if source[0] == 'jasnita' else ''}{source[1]}")

    ensure_event_log_schema()
    ensure_excel_dependency()
    metadata = ask_log_metadata()
    counts = {"car": 0, "motor": 0}
    truth = {"car": 0, "motor": 0}
    ctx = describe_source(source)
    ctx.update(metadata)
    session = {"ctx": ctx, "counting": False}

    frame_queue = mp.Queue(maxsize=1)
    proc = mp.Process(target=stream_worker, args=(source, frame_queue), daemon=True)
    proc.start()
    try:
        run(frame_queue, counts, truth, session)
    except KeyboardInterrupt:
        print("[INFO] Dihentikan (Ctrl+C).")
    finally:
        # Ringkasan akhir & laporan HTML sudah ditulis di dalam run() sendiri (lihat finally di sana),
        # supaya urutannya benar: tunggu antrean writer kosong dulu baru tulis angka final.
        proc.terminate()
        proc.join()
        cv2.destroyAllWindows()


def cli_report():
    """python traffic_counter_v5.py --report ["<id_cctv>"]  -- buat laporan tanpa membuka kamera."""
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    cctv_arg = args[0].strip().strip('"').strip("'") if args else None
    ids = [cctv_arg] if cctv_arg else list_known_cctv_ids(day=time.strftime("%Y-%m-%d"))
    if not ids:
        print(f"[INFO] Tidak ada data hari ini di {EVENT_LOG_FILE.name}. "
              f"Jalankan dulu counting-nya, atau sebutkan ID CCTV secara manual.")
        return
    for cid in ids:
        path = generate_html_report(cid)
        print(f"[INFO] Laporan dibuat: {path}")


if __name__ == "__main__":
    mp.freeze_support()
    main()
